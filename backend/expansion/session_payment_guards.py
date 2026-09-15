"""Backstops for accrued-fee quotes, immutable credits and their real receipts."""

QUOTE_FROZEN_FIELDS = (
    "id", "session_id", "site_id", "created_by_id", "owner_customer_id", "request_id",
    "session_state_hash", "credit_snapshot_hash", "gross_fee", "credited_amount", "amount",
    "quoted_at", "paid_through", "expires_at", "billing_basis",
)
CREDIT_FROZEN_FIELDS = ("id", "session_id", "quote_id", "amount", "paid_through", "created_at")

_QUOTE_CHANGE = " OR ".join(f"NEW.{key} IS NOT OLD.{key}" for key in QUOTE_FROZEN_FIELDS)
_QUOTE_CHANGE += " OR (OLD.receipt_id IS NOT NULL AND NEW.receipt_id IS NOT OLD.receipt_id) OR (OLD.credit_id IS NOT NULL AND NEW.credit_id IS NOT OLD.credit_id)"
_CREDIT_CHANGE = " OR ".join(f"NEW.{key} IS NOT OLD.{key}" for key in CREDIT_FROZEN_FIELDS)
_CREDIT_CHANGE += " OR (OLD.receipt_id IS NOT NULL AND NEW.receipt_id IS NOT OLD.receipt_id)"

_QUOTE_SOURCE = """EXISTS (SELECT 1 FROM parking_sessions s JOIN parking_slots slot ON slot.id=s.parking_slot_id
    JOIN zones z ON z.id=slot.zone_id WHERE s.id=NEW.session_id AND s.status='active'
    AND s.billing_policy_version IN ('entry-v1','prepaid-window-v1') AND z.site_id=NEW.site_id
    AND NEW.owner_customer_id IS (SELECT g.customer_id FROM portal_session_grants g WHERE g.parking_session_id=s.id)
    AND NEW.credited_amount=COALESCE((SELECT SUM(c.amount) FROM session_fee_credits c WHERE c.session_id=s.id AND c.receipt_id IS NOT NULL),0))"""
_CREDIT_SOURCE = """EXISTS (SELECT 1 FROM session_fee_quotes q JOIN parking_sessions s ON s.id=q.session_id
    JOIN online_payment_links l ON l.session_quote_id=q.id WHERE q.id=NEW.quote_id AND s.id=NEW.session_id
    AND s.status='active' AND q.status IN ('pending','expired') AND NEW.amount=q.amount AND NEW.paid_through=q.paid_through
    AND q.credited_amount=COALESCE((SELECT SUM(c.amount) FROM session_fee_credits c WHERE c.session_id=s.id AND c.receipt_id IS NOT NULL),0)
    AND EXISTS (SELECT 1 FROM online_payment_inbox i JOIN online_payment_processing p ON p.id=i.id
        WHERE i.link_id=l.id AND p.status='received' AND i.amount=q.amount AND i.currency='VND'
        AND i.receiver_digest=l.receiver_digest AND i.payment_link_id=l.payment_link_id
        AND i.received_at<q.expires_at AND i.verification_issue IS NULL))"""
_CREDIT_RECEIPT = """EXISTS (SELECT 1 FROM payments p WHERE p.id=NEW.receipt_id AND p.source_type='session_credit'
    AND p.source_id=NEW.id AND p.kind='receipt' AND p.amount=NEW.amount AND p.method='transfer'
    AND p.collected_by_id IS NULL AND p.shift_id IS NULL)"""
_QUOTE_FULFILLED = """EXISTS (SELECT 1 FROM session_fee_credits c WHERE c.id=NEW.credit_id AND c.quote_id=NEW.id
    AND c.session_id=NEW.session_id AND c.amount=NEW.amount AND c.paid_through=NEW.paid_through
    AND c.receipt_id=NEW.receipt_id)"""
_PAYMENT_SOURCE = """EXISTS (SELECT 1 FROM session_fee_credits c JOIN session_fee_quotes q ON q.id=c.quote_id
    JOIN parking_sessions s ON s.id=c.session_id WHERE c.id=NEW.source_id AND c.amount=NEW.amount
    AND q.session_id=s.id AND s.status='active' AND q.status IN ('pending','expired')
    AND q.site_id IS NEW.site_id AND NEW.method='transfer' AND NEW.collected_by_id IS NULL AND NEW.shift_id IS NULL)"""
_REFUND_CLOSED = """EXISTS (SELECT 1 FROM session_fee_credits c JOIN parking_sessions s ON s.id=c.session_id
    WHERE c.id=NEW.source_id AND s.status='completed')"""
_SESSION_OUTSTANDING = """EXISTS (SELECT 1 FROM session_fee_quotes q JOIN online_payment_links l ON l.session_quote_id=q.id
    WHERE q.session_id=OLD.id AND (l.state IN ('creating','unknown','ready','review') OR EXISTS (
        SELECT 1 FROM online_payment_inbox i JOIN online_payment_processing p ON p.id=i.id
        WHERE i.link_id=l.id AND p.status='received')))"""

SESSION_PAYMENT_SQLITE_GUARDS = {
    "trg_session_fee_quote_frozen": f"CREATE TRIGGER IF NOT EXISTS trg_session_fee_quote_frozen BEFORE UPDATE ON session_fee_quotes WHEN {_QUOTE_CHANGE} BEGIN SELECT RAISE(ABORT,'session fee quote snapshot immutable'); END",
    "trg_session_fee_quote_source": f"CREATE TRIGGER IF NOT EXISTS trg_session_fee_quote_source BEFORE INSERT ON session_fee_quotes WHEN NEW.status!='pending' OR NEW.credit_id IS NOT NULL OR NEW.receipt_id IS NOT NULL OR NOT {_QUOTE_SOURCE} BEGIN SELECT RAISE(ABORT,'session fee quote source invalid'); END",
    "trg_session_fee_quote_delete": "CREATE TRIGGER IF NOT EXISTS trg_session_fee_quote_delete BEFORE DELETE ON session_fee_quotes BEGIN SELECT RAISE(ABORT,'session fee quote must be retained'); END",
    "trg_session_fee_quote_replace": "CREATE TRIGGER IF NOT EXISTS trg_session_fee_quote_replace BEFORE INSERT ON session_fee_quotes WHEN EXISTS (SELECT 1 FROM session_fee_quotes WHERE id=NEW.id OR (created_by_id=NEW.created_by_id AND session_id=NEW.session_id AND request_id=NEW.request_id) OR (status='pending' AND NEW.status='pending' AND session_id=NEW.session_id)) BEGIN SELECT RAISE(ABORT,'session fee quote cannot be replaced'); END",
    "trg_session_fee_quote_terminal": "CREATE TRIGGER IF NOT EXISTS trg_session_fee_quote_terminal BEFORE UPDATE ON session_fee_quotes WHEN (OLD.status='fulfilled' AND NEW.status!='fulfilled') OR (OLD.status='cancelled' AND NEW.status NOT IN ('cancelled','review')) OR (OLD.status='review' AND NEW.status!='review') BEGIN SELECT RAISE(ABORT,'session fee quote terminal'); END",
    "trg_session_fee_quote_fulfilled": f"CREATE TRIGGER IF NOT EXISTS trg_session_fee_quote_fulfilled BEFORE UPDATE ON session_fee_quotes WHEN NEW.status='fulfilled' AND NOT {_QUOTE_FULFILLED} BEGIN SELECT RAISE(ABORT,'session fee quote credit mismatch'); END",
    "trg_session_fee_credit_source": f"CREATE TRIGGER IF NOT EXISTS trg_session_fee_credit_source BEFORE INSERT ON session_fee_credits WHEN NEW.receipt_id IS NOT NULL OR NOT {_CREDIT_SOURCE} BEGIN SELECT RAISE(ABORT,'session fee credit source invalid'); END",
    "trg_session_fee_credit_frozen": f"CREATE TRIGGER IF NOT EXISTS trg_session_fee_credit_frozen BEFORE UPDATE ON session_fee_credits WHEN {_CREDIT_CHANGE} BEGIN SELECT RAISE(ABORT,'session fee credit immutable'); END",
    "trg_session_fee_credit_receipt": f"CREATE TRIGGER IF NOT EXISTS trg_session_fee_credit_receipt BEFORE UPDATE ON session_fee_credits WHEN NEW.receipt_id IS NOT NULL AND NOT {_CREDIT_RECEIPT} BEGIN SELECT RAISE(ABORT,'session fee credit receipt invalid'); END",
    "trg_session_fee_credit_delete": "CREATE TRIGGER IF NOT EXISTS trg_session_fee_credit_delete BEFORE DELETE ON session_fee_credits BEGIN SELECT RAISE(ABORT,'session fee credit must be retained'); END",
    "trg_session_fee_credit_replace": "CREATE TRIGGER IF NOT EXISTS trg_session_fee_credit_replace BEFORE INSERT ON session_fee_credits WHEN EXISTS (SELECT 1 FROM session_fee_credits WHERE id=NEW.id OR quote_id=NEW.quote_id OR (receipt_id IS NOT NULL AND receipt_id=NEW.receipt_id)) BEGIN SELECT RAISE(ABORT,'session fee credit cannot be replaced'); END",
    "trg_session_fee_payment_source": f"CREATE TRIGGER IF NOT EXISTS trg_session_fee_payment_source BEFORE INSERT ON payments WHEN NEW.source_type='session_credit' AND ((NEW.kind='receipt' AND NOT {_PAYMENT_SOURCE}) OR (NEW.kind='refund' AND NOT {_REFUND_CLOSED})) BEGIN SELECT RAISE(ABORT,'session credit payment source invalid'); END",
    "trg_session_fee_session_delete": "CREATE TRIGGER IF NOT EXISTS trg_session_fee_session_delete BEFORE DELETE ON parking_sessions WHEN EXISTS (SELECT 1 FROM session_fee_quotes WHERE session_id=OLD.id) BEGIN SELECT RAISE(ABORT,'session fee history must be retained'); END",
    "trg_session_fee_session_cancel": f"CREATE TRIGGER IF NOT EXISTS trg_session_fee_session_cancel BEFORE UPDATE OF status ON parking_sessions WHEN NEW.status='cancelled' AND (EXISTS (SELECT 1 FROM session_fee_credits WHERE session_id=OLD.id) OR {_SESSION_OUTSTANDING}) BEGIN SELECT RAISE(ABORT,'session has online funds or outstanding link'); END",
}


def _pg(fragment):
    return fragment.replace(" IS NOT ", " IS DISTINCT FROM ").replace(" IS NEW.", " IS NOT DISTINCT FROM NEW.").replace(
        "NEW.owner_customer_id IS (", "NEW.owner_customer_id IS NOT DISTINCT FROM (").replace(
        "NEW.billing_basis IS DISTINCT FROM OLD.billing_basis", "NEW.billing_basis::text IS DISTINCT FROM OLD.billing_basis::text")


SESSION_PAYMENT_POSTGRES_GUARD_SQL = f"""
CREATE OR REPLACE FUNCTION session_payment_guard() RETURNS trigger AS $$
BEGIN
    IF TG_TABLE_NAME='payments' THEN
        IF NEW.source_type='session_credit' AND ((NEW.kind='receipt' AND NOT {_pg(_PAYMENT_SOURCE)})
            OR (NEW.kind='refund' AND NOT {_pg(_REFUND_CLOSED)})) THEN
            RAISE EXCEPTION 'session credit payment source invalid' USING ERRCODE='23514';
        END IF;
    ELSIF TG_TABLE_NAME='parking_sessions' THEN
        IF TG_OP='DELETE' AND EXISTS (SELECT 1 FROM session_fee_quotes WHERE session_id=OLD.id) THEN
            RAISE EXCEPTION 'session fee history must be retained' USING ERRCODE='23514';
        ELSIF TG_OP='UPDATE' AND NEW.status='cancelled' AND (EXISTS (SELECT 1 FROM session_fee_credits WHERE session_id=OLD.id)
            OR {_SESSION_OUTSTANDING}) THEN
            RAISE EXCEPTION 'session has online funds or outstanding link' USING ERRCODE='23514';
        END IF;
    ELSIF TG_TABLE_NAME='session_fee_quotes' THEN
        IF TG_OP='DELETE' THEN RAISE EXCEPTION 'session fee quote must be retained' USING ERRCODE='23514'; END IF;
        IF TG_OP='INSERT' AND (NEW.status!='pending' OR NEW.credit_id IS NOT NULL OR NEW.receipt_id IS NOT NULL OR NOT {_pg(_QUOTE_SOURCE)}) THEN
            RAISE EXCEPTION 'session fee quote source invalid' USING ERRCODE='23514';
        END IF;
        IF TG_OP='UPDATE' AND ({_pg(_QUOTE_CHANGE)}) THEN
            RAISE EXCEPTION 'session fee quote snapshot immutable' USING ERRCODE='23514';
        END IF;
        IF TG_OP='UPDATE' AND ((OLD.status='fulfilled' AND NEW.status!='fulfilled') OR
            (OLD.status='cancelled' AND NEW.status NOT IN ('cancelled','review')) OR (OLD.status='review' AND NEW.status!='review')) THEN
            RAISE EXCEPTION 'session fee quote terminal' USING ERRCODE='23514';
        END IF;
        IF NEW.status='fulfilled' AND NOT {_pg(_QUOTE_FULFILLED)} THEN
            RAISE EXCEPTION 'session fee quote credit mismatch' USING ERRCODE='23514';
        END IF;
    ELSE
        IF TG_OP='DELETE' THEN RAISE EXCEPTION 'session fee credit must be retained' USING ERRCODE='23514'; END IF;
        IF TG_OP='INSERT' AND (NEW.receipt_id IS NOT NULL OR NOT {_pg(_CREDIT_SOURCE)}) THEN
            RAISE EXCEPTION 'session fee credit source invalid' USING ERRCODE='23514';
        END IF;
        IF TG_OP='UPDATE' AND ({_pg(_CREDIT_CHANGE)}) THEN
            RAISE EXCEPTION 'session fee credit immutable' USING ERRCODE='23514';
        END IF;
        IF NEW.receipt_id IS NOT NULL AND NOT {_pg(_CREDIT_RECEIPT)} THEN
            RAISE EXCEPTION 'session fee credit receipt invalid' USING ERRCODE='23514';
        END IF;
    END IF;
    IF TG_OP='DELETE' THEN RETURN OLD; END IF;
    RETURN NEW;
END; $$ LANGUAGE plpgsql;
CREATE TRIGGER trg_session_fee_quote_guard BEFORE INSERT OR UPDATE OR DELETE ON session_fee_quotes FOR EACH ROW EXECUTE FUNCTION session_payment_guard();
CREATE TRIGGER trg_session_fee_credit_guard BEFORE INSERT OR UPDATE OR DELETE ON session_fee_credits FOR EACH ROW EXECUTE FUNCTION session_payment_guard();
CREATE TRIGGER trg_session_fee_payment_source BEFORE INSERT ON payments FOR EACH ROW EXECUTE FUNCTION session_payment_guard();
CREATE TRIGGER trg_session_fee_session_guard BEFORE UPDATE OR DELETE ON parking_sessions FOR EACH ROW EXECUTE FUNCTION session_payment_guard();
"""
