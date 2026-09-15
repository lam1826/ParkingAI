"""Database retention backstops; transport verification remains an application duty."""

_FROZEN = ("id", "order_id", "session_quote_id", "site_id", "channel", "receiver_digest", "amount", "currency",
           "description", "return_url", "cancel_url", "expires_at", "created_at")
_SET_ONCE = ("payment_link_id", "settled_reference", "receipt_id")
_CHANGED_SQLITE = " OR ".join(f"NEW.{key} IS NOT OLD.{key}" for key in _FROZEN)
_CHANGED_SQLITE += " OR " + " OR ".join(f"(OLD.{key} IS NOT NULL AND NEW.{key} IS NOT OLD.{key})" for key in _SET_ONCE)

_LINK_SOURCE = """(EXISTS (SELECT 1 FROM portal_orders o WHERE o.id=NEW.order_id AND o.payment_mode='payos'
    AND o.status='pending' AND o.site_id=NEW.site_id AND o.amount=NEW.amount AND NEW.currency='VND'
    AND o.expires_at=NEW.expires_at) OR EXISTS (SELECT 1 FROM session_fee_quotes q WHERE q.id=NEW.session_quote_id
    AND q.status='pending' AND q.site_id=NEW.site_id AND q.amount=NEW.amount AND NEW.currency='VND' AND q.expires_at=NEW.expires_at))"""
_LINK_RECEIPT = """(EXISTS (SELECT 1 FROM portal_orders o JOIN payments p ON p.id=o.receipt_id
    WHERE o.id=NEW.order_id AND o.receipt_id=NEW.receipt_id AND o.status IN ('fulfilled','refunded')
    AND p.kind='receipt' AND p.method='transfer' AND p.collected_by_id IS NULL AND p.amount=NEW.amount)
    OR EXISTS (SELECT 1 FROM session_fee_quotes q JOIN session_fee_credits c ON c.id=q.credit_id
        JOIN payments p ON p.id=c.receipt_id WHERE q.id=NEW.session_quote_id AND q.status='fulfilled'
        AND q.receipt_id=NEW.receipt_id AND c.receipt_id=NEW.receipt_id AND c.quote_id=q.id
        AND p.source_type='session_credit' AND p.source_id=c.id AND p.kind='receipt'
        AND p.method='transfer' AND p.collected_by_id IS NULL AND p.amount=NEW.amount))"""

ONLINE_PAYMENT_SQLITE_GUARDS = {
    "trg_online_link_frozen": f"CREATE TRIGGER IF NOT EXISTS trg_online_link_frozen BEFORE UPDATE ON online_payment_links WHEN {_CHANGED_SQLITE} BEGIN SELECT RAISE(ABORT,'online payment identity is immutable'); END",
    "trg_online_link_delete": "CREATE TRIGGER IF NOT EXISTS trg_online_link_delete BEFORE DELETE ON online_payment_links BEGIN SELECT RAISE(ABORT,'online payment identity must be retained'); END",
    "trg_online_link_replace": "CREATE TRIGGER IF NOT EXISTS trg_online_link_replace BEFORE INSERT ON online_payment_links WHEN EXISTS (SELECT 1 FROM online_payment_links WHERE id=NEW.id OR order_id=NEW.order_id OR session_quote_id=NEW.session_quote_id OR (payment_link_id IS NOT NULL AND payment_link_id=NEW.payment_link_id)) BEGIN SELECT RAISE(ABORT,'online payment identity cannot be replaced'); END",
    "trg_online_link_source": f"CREATE TRIGGER IF NOT EXISTS trg_online_link_source BEFORE INSERT ON online_payment_links WHEN NOT {_LINK_SOURCE} BEGIN SELECT RAISE(ABORT,'online payment source mismatch'); END",
    "trg_online_link_receipt": f"CREATE TRIGGER IF NOT EXISTS trg_online_link_receipt BEFORE UPDATE ON online_payment_links WHEN NEW.receipt_id IS NOT NULL AND (NEW.settled_reference IS NULL OR NOT {_LINK_RECEIPT}) BEGIN SELECT RAISE(ABORT,'online payment receipt mismatch'); END",
    "trg_online_inbox_update": "CREATE TRIGGER IF NOT EXISTS trg_online_inbox_update BEFORE UPDATE ON online_payment_inbox BEGIN SELECT RAISE(ABORT,'online payment evidence is immutable'); END",
    "trg_online_inbox_delete": "CREATE TRIGGER IF NOT EXISTS trg_online_inbox_delete BEFORE DELETE ON online_payment_inbox BEGIN SELECT RAISE(ABORT,'online payment evidence must be retained'); END",
    "trg_online_inbox_replace": "CREATE TRIGGER IF NOT EXISTS trg_online_inbox_replace BEFORE INSERT ON online_payment_inbox WHEN EXISTS (SELECT 1 FROM online_payment_inbox WHERE id=NEW.id OR (channel=NEW.channel AND reference=NEW.reference AND payload_digest=NEW.payload_digest)) BEGIN SELECT RAISE(ABORT,'online payment evidence cannot be replaced'); END",
    "trg_online_order_delete": "CREATE TRIGGER IF NOT EXISTS trg_online_order_delete BEFORE DELETE ON portal_orders WHEN EXISTS (SELECT 1 FROM online_payment_links WHERE order_id=OLD.id) BEGIN SELECT RAISE(ABORT,'online payment order must be retained'); END",
    "trg_online_order_replace": "CREATE TRIGGER IF NOT EXISTS trg_online_order_replace BEFORE INSERT ON portal_orders WHEN EXISTS (SELECT 1 FROM online_payment_links WHERE order_id=NEW.id) BEGIN SELECT RAISE(ABORT,'online payment order cannot be replaced'); END",
    "trg_online_processing_delete": "CREATE TRIGGER IF NOT EXISTS trg_online_processing_delete BEFORE DELETE ON online_payment_processing BEGIN SELECT RAISE(ABORT,'online payment processing must be retained'); END",
    "trg_online_processing_replace": "CREATE TRIGGER IF NOT EXISTS trg_online_processing_replace BEFORE INSERT ON online_payment_processing WHEN EXISTS (SELECT 1 FROM online_payment_processing WHERE id=NEW.id) BEGIN SELECT RAISE(ABORT,'online payment processing cannot be replaced'); END",
    "trg_online_processing_terminal": "CREATE TRIGGER IF NOT EXISTS trg_online_processing_terminal BEFORE UPDATE ON online_payment_processing WHEN NEW.id IS NOT OLD.id OR (OLD.status!='received' AND (NEW.status IS NOT OLD.status OR NEW.reason IS NOT OLD.reason OR NEW.receipt_id IS NOT OLD.receipt_id OR NEW.processed_at IS NOT OLD.processed_at)) BEGIN SELECT RAISE(ABORT,'online processing decision is final'); END",
    "trg_online_review_update": "CREATE TRIGGER IF NOT EXISTS trg_online_review_update BEFORE UPDATE ON online_payment_review_decisions BEGIN SELECT RAISE(ABORT,'online review decision is immutable'); END",
    "trg_online_review_delete": "CREATE TRIGGER IF NOT EXISTS trg_online_review_delete BEFORE DELETE ON online_payment_review_decisions BEGIN SELECT RAISE(ABORT,'online review decision must be retained'); END",
    "trg_online_review_replace": "CREATE TRIGGER IF NOT EXISTS trg_online_review_replace BEFORE INSERT ON online_payment_review_decisions WHEN EXISTS (SELECT 1 FROM online_payment_review_decisions WHERE id=NEW.id OR (inbox_id=NEW.inbox_id AND request_id=NEW.request_id) OR (action='confirmed_external_refund' AND NEW.action='confirmed_external_refund' AND channel=NEW.channel AND payment_reference=NEW.payment_reference)) BEGIN SELECT RAISE(ABORT,'online review decision cannot be replaced'); END",
    "trg_online_review_source": "CREATE TRIGGER IF NOT EXISTS trg_online_review_source BEFORE INSERT ON online_payment_review_decisions WHEN NOT EXISTS (SELECT 1 FROM online_payment_inbox i JOIN online_payment_processing p ON p.id=i.id WHERE i.id=NEW.inbox_id AND p.status='review' AND i.channel=NEW.channel AND i.reference=NEW.payment_reference AND (NEW.action='note' OR (NEW.refund_amount=i.amount AND i.currency='VND' AND (i.verification_issue IS NULL OR i.verification_issue NOT IN ('account_mismatch','currency_mismatch')) AND NOT EXISTS (SELECT 1 FROM online_payment_links l WHERE l.channel=i.channel AND l.settled_reference=i.reference)))) BEGIN SELECT RAISE(ABORT,'online review source mismatch'); END",
    "trg_online_inbox_integer": "CREATE TRIGGER IF NOT EXISTS trg_online_inbox_integer BEFORE INSERT ON online_payment_inbox WHEN typeof(NEW.amount)!='integer' OR typeof(NEW.order_code)!='integer' BEGIN SELECT RAISE(ABORT,'online evidence requires integer money and identity'); END",
    "trg_online_processing_receipt": "CREATE TRIGGER IF NOT EXISTS trg_online_processing_receipt BEFORE UPDATE ON online_payment_processing WHEN NEW.status IN ('processed','duplicate') AND NOT EXISTS (SELECT 1 FROM online_payment_inbox i JOIN online_payment_links l ON l.id=i.link_id WHERE i.id=NEW.id AND l.receipt_id=NEW.receipt_id AND l.settled_reference=i.reference AND l.channel=i.channel AND l.id=i.order_code AND l.amount=i.amount AND l.currency=i.currency AND l.receiver_digest=i.receiver_digest AND l.payment_link_id=i.payment_link_id) BEGIN SELECT RAISE(ABORT,'online processing receipt mismatch'); END",
}

_CHANGED_PG = " OR ".join(f"NEW.{key} IS DISTINCT FROM OLD.{key}" for key in _FROZEN)
_CHANGED_PG += " OR " + " OR ".join(f"(OLD.{key} IS NOT NULL AND NEW.{key} IS DISTINCT FROM OLD.{key})" for key in _SET_ONCE)
ONLINE_PAYMENT_POSTGRES_GUARD_SQL = f"""
CREATE OR REPLACE FUNCTION online_payment_guard() RETURNS trigger AS $$
BEGIN
    IF TG_TABLE_NAME='online_payment_inbox' THEN
        RAISE EXCEPTION 'online payment evidence is immutable' USING ERRCODE='23514';
    ELSIF TG_TABLE_NAME='online_payment_review_decisions' THEN
        IF TG_OP!='INSERT' THEN RAISE EXCEPTION 'online review decision is immutable' USING ERRCODE='23514'; END IF;
        IF NOT EXISTS (SELECT 1 FROM online_payment_inbox i JOIN online_payment_processing p ON p.id=i.id
            WHERE i.id=NEW.inbox_id AND p.status='review' AND i.channel=NEW.channel AND i.reference=NEW.payment_reference
            AND (NEW.action='note' OR (NEW.refund_amount=i.amount AND i.currency='VND'
                AND (i.verification_issue IS NULL OR i.verification_issue NOT IN ('account_mismatch','currency_mismatch'))
                AND NOT EXISTS (SELECT 1 FROM online_payment_links l WHERE l.channel=i.channel AND l.settled_reference=i.reference)))) THEN
            RAISE EXCEPTION 'online review source mismatch' USING ERRCODE='23514';
        END IF;
    ELSIF TG_TABLE_NAME='portal_orders' THEN
        IF EXISTS (SELECT 1 FROM online_payment_links WHERE order_id=OLD.id) THEN
            RAISE EXCEPTION 'online payment order must be retained' USING ERRCODE='23514';
        END IF;
    ELSIF TG_TABLE_NAME='online_payment_processing' THEN
        IF TG_OP='DELETE' THEN RAISE EXCEPTION 'online processing must be retained' USING ERRCODE='23514'; END IF;
        IF NEW.id IS DISTINCT FROM OLD.id OR (OLD.status!='received' AND
            (NEW.status IS DISTINCT FROM OLD.status OR NEW.reason IS DISTINCT FROM OLD.reason OR
             NEW.receipt_id IS DISTINCT FROM OLD.receipt_id OR NEW.processed_at IS DISTINCT FROM OLD.processed_at)) THEN
            RAISE EXCEPTION 'online processing decision is final' USING ERRCODE='23514';
        END IF;
        IF NEW.status IN ('processed','duplicate') AND NOT EXISTS (SELECT 1 FROM online_payment_inbox i
            JOIN online_payment_links l ON l.id=i.link_id WHERE i.id=NEW.id AND l.receipt_id=NEW.receipt_id
            AND l.settled_reference=i.reference AND l.channel=i.channel AND l.id=i.order_code
            AND l.amount=i.amount AND l.currency=i.currency AND l.receiver_digest=i.receiver_digest
            AND l.payment_link_id=i.payment_link_id) THEN
            RAISE EXCEPTION 'online processing receipt mismatch' USING ERRCODE='23514';
        END IF;
    ELSE
        IF TG_OP='DELETE' THEN RAISE EXCEPTION 'online payment identity must be retained' USING ERRCODE='23514'; END IF;
        IF TG_OP='UPDATE' AND ({_CHANGED_PG}) THEN
            RAISE EXCEPTION 'online payment identity is immutable' USING ERRCODE='23514';
        END IF;
        IF TG_OP='INSERT' AND NOT {_LINK_SOURCE} THEN
            RAISE EXCEPTION 'online payment source mismatch' USING ERRCODE='23514';
        END IF;
        IF NEW.receipt_id IS NOT NULL AND (NEW.settled_reference IS NULL OR NOT {_LINK_RECEIPT}) THEN
            RAISE EXCEPTION 'online payment receipt mismatch' USING ERRCODE='23514';
        END IF;
    END IF;
    IF TG_OP='DELETE' THEN RETURN OLD; END IF;
    RETURN NEW;
END; $$ LANGUAGE plpgsql;
CREATE TRIGGER trg_online_link_guard BEFORE INSERT OR UPDATE OR DELETE ON online_payment_links FOR EACH ROW EXECUTE FUNCTION online_payment_guard();
CREATE TRIGGER trg_online_inbox_guard BEFORE UPDATE OR DELETE ON online_payment_inbox FOR EACH ROW EXECUTE FUNCTION online_payment_guard();
CREATE TRIGGER trg_online_processing_guard BEFORE UPDATE OR DELETE ON online_payment_processing FOR EACH ROW EXECUTE FUNCTION online_payment_guard();
CREATE TRIGGER trg_online_order_delete BEFORE DELETE ON portal_orders FOR EACH ROW EXECUTE FUNCTION online_payment_guard();
CREATE TRIGGER trg_online_review_guard BEFORE INSERT OR UPDATE OR DELETE ON online_payment_review_decisions FOR EACH ROW EXECUTE FUNCTION online_payment_guard();
"""
