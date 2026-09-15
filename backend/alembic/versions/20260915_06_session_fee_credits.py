"""Verified parking-fee credits and release consumed reservation capacity."""
from alembic import op

revision = "20260915_06"
down_revision = "20260915_05"
branch_labels = None
depends_on = None

UPGRADE_SQL = ('\n'
 'CREATE TABLE session_fee_quotes (\n'
 '\tid VARCHAR(36) NOT NULL, \n'
 '\tsession_id VARCHAR(36) NOT NULL, \n'
 '\tsite_id INTEGER NOT NULL, \n'
 '\tcreated_by_id INTEGER NOT NULL, \n'
 '\towner_customer_id INTEGER, \n'
 '\trequest_id VARCHAR(64) NOT NULL, \n'
 '\tsession_state_hash VARCHAR(64) NOT NULL, \n'
 '\tcredit_snapshot_hash VARCHAR(64) NOT NULL, \n'
 '\tgross_fee BIGINT NOT NULL, \n'
 '\tcredited_amount BIGINT NOT NULL, \n'
 '\tamount BIGINT NOT NULL, \n'
 '\tquoted_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, \n'
 '\tpaid_through TIMESTAMP WITHOUT TIME ZONE NOT NULL, \n'
 '\texpires_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, \n'
 '\tbilling_basis JSON NOT NULL, \n'
 '\tstatus VARCHAR(12) NOT NULL, \n'
 '\treview_reason VARCHAR(100), \n'
 '\tcredit_id VARCHAR(36), \n'
 '\treceipt_id VARCHAR(36), \n'
 '\tPRIMARY KEY (id), \n'
 '\tCONSTRAINT uq_session_fee_quote_request UNIQUE (created_by_id, session_id, request_id), \n'
 '\tCONSTRAINT ck_session_fee_quote_status CHECK (status IN '
 "('pending','fulfilled','cancelled','expired','review')), \n"
 '\tCONSTRAINT ck_session_fee_quote_money CHECK (gross_fee>0 AND gross_fee<=9007199254740991 AND '
 'credited_amount>=0 AND amount>0 AND amount=gross_fee-credited_amount), \n'
 '\tCONSTRAINT ck_session_fee_quote_time CHECK (expires_at>quoted_at AND paid_through>=quoted_at), \n'
 "\tCONSTRAINT ck_session_fee_quote_fulfilled CHECK (status!='fulfilled' OR (credit_id IS NOT NULL AND "
 'receipt_id IS NOT NULL)), \n'
 '\tFOREIGN KEY(session_id) REFERENCES parking_sessions (id), \n'
 '\tFOREIGN KEY(site_id) REFERENCES parking_sites (id), \n'
 '\tFOREIGN KEY(created_by_id) REFERENCES users (id), \n'
 '\tFOREIGN KEY(owner_customer_id) REFERENCES customers (id), \n'
 '\tUNIQUE (credit_id), \n'
 '\tUNIQUE (receipt_id)\n'
 ')\n'
 '\n',
 'CREATE INDEX ix_session_fee_quotes_session_id ON session_fee_quotes (session_id)',
 'CREATE INDEX ix_session_fee_quotes_site_id ON session_fee_quotes (site_id)',
 "CREATE UNIQUE INDEX uq_session_fee_pending ON session_fee_quotes (session_id) WHERE status='pending'",
 '\n'
 'CREATE TABLE session_fee_credits (\n'
 '\tid VARCHAR(36) NOT NULL, \n'
 '\tsession_id VARCHAR(36) NOT NULL, \n'
 '\tquote_id VARCHAR(36) NOT NULL, \n'
 '\tamount BIGINT NOT NULL, \n'
 '\tpaid_through TIMESTAMP WITHOUT TIME ZONE NOT NULL, \n'
 '\tcreated_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, \n'
 '\treceipt_id VARCHAR(36), \n'
 '\tPRIMARY KEY (id), \n'
 '\tCONSTRAINT ck_session_fee_credit_money CHECK (amount>0 AND amount<=9007199254740991), \n'
 '\tFOREIGN KEY(session_id) REFERENCES parking_sessions (id), \n'
 '\tUNIQUE (quote_id), \n'
 '\tFOREIGN KEY(quote_id) REFERENCES session_fee_quotes (id), \n'
 '\tUNIQUE (receipt_id)\n'
 ')\n'
 '\n',
 'CREATE INDEX ix_session_fee_credits_session_id ON session_fee_credits (session_id)',
 'ALTER TABLE online_payment_links ALTER COLUMN order_id DROP NOT NULL',
 'ALTER TABLE online_payment_links ADD COLUMN session_quote_id VARCHAR(36) REFERENCES session_fee_quotes(id)',
 'CREATE UNIQUE INDEX uq_online_payment_links_session_quote_id ON online_payment_links(session_quote_id)',
 'ALTER TABLE online_payment_links ADD CONSTRAINT ck_online_link_target CHECK ((order_id IS NOT NULL AND '
 'session_quote_id IS NULL) OR (order_id IS NULL AND session_quote_id IS NOT NULL))',
 'ALTER TABLE payments DROP CONSTRAINT ck_payment_source',
 "ALTER TABLE payments ADD CONSTRAINT ck_payment_source CHECK (source_type IN ('parking_session', "
 "'monthly_pass', 'portal_order', 'session_credit'))",
 'DROP TRIGGER trg_parking_sessions_checkout_confirmation_guard ON parking_sessions',
 '\n'
 'CREATE OR REPLACE FUNCTION parking_checkout_confirmation_guard() RETURNS trigger AS $$\n'
 'DECLARE balance_due bigint;\n'
 'BEGIN\n'
 '    SELECT NEW.parking_fee - COALESCE(SUM(amount), 0) INTO balance_due\n'
 '        FROM session_fee_credits WHERE session_id=NEW.id AND receipt_id IS NOT NULL;\n'
 "    IF TG_OP = 'INSERT' THEN\n"
 '        IF NEW.checkout_quote_hash IS NOT NULL OR NEW.checkout_payment_method IS NOT NULL THEN\n'
 "            RAISE EXCEPTION 'checkout confirmation requires completion' USING ERRCODE = '23514';\n"
 '        END IF;\n'
 '    ELSIF ROW(NEW.checkout_quote_hash, NEW.checkout_payment_method) IS DISTINCT FROM\n'
 '          ROW(OLD.checkout_quote_hash, OLD.checkout_payment_method) AND NOT (\n'
 "              OLD.status IS NOT DISTINCT FROM 'checking_out' AND NEW.status IS NOT DISTINCT FROM "
 "'completed'\n"
 '              AND OLD.checkout_quote_hash IS NULL AND OLD.checkout_payment_method IS NULL) THEN\n'
 "        RAISE EXCEPTION 'checkout confirmation invalid or immutable' USING ERRCODE = '23514';\n"
 '    END IF;\n'
 '    IF (NEW.checkout_quote_hash IS NULL AND NEW.checkout_payment_method IS NOT NULL) OR\n'
 '       (NEW.checkout_quote_hash IS NOT NULL AND (\n'
 "           length(NEW.checkout_quote_hash) != 64 OR NEW.checkout_quote_hash !~ '^[0-9a-f]{64}$'\n"
 "           OR NEW.status IS DISTINCT FROM 'completed'\n"
 '           OR NEW.staff_out_id IS NULL OR NEW.parking_fee IS NULL OR NEW.parking_fee < 0 OR balance_due < '
 '0\n'
 '           OR (balance_due = 0 AND NEW.checkout_payment_method IS NOT NULL)\n'
 "           OR (balance_due > 0 AND COALESCE(NEW.checkout_payment_method, '') NOT IN ('cash', "
 "'transfer')))) THEN\n"
 "        RAISE EXCEPTION 'checkout confirmation invalid or immutable' USING ERRCODE = '23514';\n"
 '    END IF;\n'
 '    RETURN NEW;\n'
 'END; $$ LANGUAGE plpgsql;\n'
 'CREATE TRIGGER trg_parking_sessions_checkout_confirmation_guard BEFORE INSERT OR UPDATE ON '
 'parking_sessions\n'
 'FOR EACH ROW EXECUTE FUNCTION parking_checkout_confirmation_guard();\n',
 'DROP TRIGGER trg_payment_guard ON payments',
 '\n'
 'CREATE OR REPLACE FUNCTION parking_payment_guard() RETURNS trigger AS $$\n'
 'DECLARE original payments%ROWTYPE; active_shift cash_shifts%ROWTYPE; refunded numeric; source_amount '
 'bigint;\n'
 'BEGIN\n'
 "    IF TG_OP <> 'INSERT' THEN RAISE EXCEPTION 'payment is immutable' USING ERRCODE = '23514'; END IF;\n"
 "    IF NEW.kind = 'receipt' THEN\n"
 "        IF NEW.source_type = 'parking_session' THEN\n"
 '            SELECT parking_fee - COALESCE((SELECT SUM(c.amount) FROM session_fee_credits c WHERE '
 'c.session_id=s.id AND c.receipt_id IS NOT NULL), 0)\n'
 '                INTO source_amount FROM parking_sessions s WHERE s.id = NEW.source_id AND s.status = '
 "'completed' FOR UPDATE;\n"
 "        ELSIF NEW.source_type = 'session_credit' THEN\n"
 '            SELECT amount INTO source_amount FROM session_fee_credits WHERE id = NEW.source_id FOR '
 'UPDATE;\n'
 "        ELSIF NEW.source_type = 'portal_order' THEN\n"
 '            SELECT amount INTO source_amount FROM portal_orders WHERE id = NEW.source_id AND product_kind '
 "IN ('hourly','daily') FOR UPDATE;\n"
 '        ELSE\n'
 '            SELECT price INTO source_amount FROM monthly_passes WHERE id::text = NEW.source_id FOR '
 'UPDATE;\n'
 '        END IF;\n'
 "        IF NOT FOUND OR source_amount IS DISTINCT FROM NEW.amount THEN RAISE EXCEPTION 'payment source or "
 "amount invalid' USING ERRCODE = '23514'; END IF;\n"
 '    END IF;\n'
 "    IF NEW.kind = 'refund' THEN\n"
 '        SELECT * INTO original FROM payments WHERE id = NEW.original_payment_id FOR UPDATE;\n'
 "        IF NOT FOUND OR original.kind <> 'receipt' OR original.source_type <> NEW.source_type OR "
 'original.source_id <> NEW.source_id OR NEW.created_at < original.created_at THEN\n'
 "            RAISE EXCEPTION 'refund original payment invalid' USING ERRCODE = '23514';\n"
 '        END IF;\n'
 '        SELECT COALESCE(SUM(amount), 0) INTO refunded FROM payments WHERE original_payment_id = '
 "NEW.original_payment_id AND kind = 'refund';\n"
 "        IF NEW.amount + refunded > original.amount THEN RAISE EXCEPTION 'refund exceeds original payment' "
 "USING ERRCODE = '23514'; END IF;\n"
 '    END IF;\n'
 '    IF NEW.shift_id IS NOT NULL THEN\n'
 '        SELECT * INTO active_shift FROM cash_shifts WHERE id = NEW.shift_id FOR UPDATE;\n'
 "        IF NOT FOUND OR active_shift.status <> 'open' OR active_shift.staff_id IS DISTINCT FROM "
 'NEW.collected_by_id OR NEW.created_at < active_shift.opened_at THEN\n'
 "            RAISE EXCEPTION 'payment requires own open shift' USING ERRCODE = '23514';\n"
 '        END IF;\n'
 '    END IF;\n'
 '    RETURN NEW;\n'
 'END; $$ LANGUAGE plpgsql;\n'
 'CREATE TRIGGER trg_payment_guard BEFORE INSERT OR UPDATE OR DELETE ON payments FOR EACH ROW EXECUTE '
 'FUNCTION parking_payment_guard();\n',
 'DROP TRIGGER trg_cash_shift_site_immutable ON cash_shifts',
 'DROP TRIGGER trg_payment_site_guard ON payments',
 '\n'
 'CREATE OR REPLACE FUNCTION parking_cash_shift_site_guard() RETURNS trigger AS $$\n'
 'BEGIN\n'
 "    IF NEW.site_id IS DISTINCT FROM OLD.site_id THEN RAISE EXCEPTION 'cash shift site is immutable' USING "
 "ERRCODE='23514'; END IF;\n"
 '    RETURN NEW;\n'
 'END; $$ LANGUAGE plpgsql;\n'
 'CREATE TRIGGER trg_cash_shift_site_immutable BEFORE UPDATE OF site_id ON cash_shifts FOR EACH ROW EXECUTE '
 'FUNCTION parking_cash_shift_site_guard();\n'
 'CREATE OR REPLACE FUNCTION parking_payment_site_guard() RETURNS trigger AS $$\n'
 'DECLARE expected_site integer; shift_site integer;\n'
 'BEGIN\n'
 "    IF NEW.kind='refund' THEN\n"
 '        SELECT site_id INTO expected_site FROM payments WHERE id=NEW.original_payment_id;\n'
 "        IF NEW.site_id IS DISTINCT FROM expected_site THEN RAISE EXCEPTION 'payment site mismatch' USING "
 "ERRCODE='23514'; END IF;\n"
 '    ELSIF NEW.site_id IS NOT NULL THEN\n'
 "        IF NEW.source_type='monthly_pass' THEN\n"
 '            SELECT o.site_id INTO expected_site FROM monthly_passes p JOIN portal_orders o ON '
 "p.renewal_key='portal:' || o.id WHERE p.id::text=NEW.source_id;\n"
 "        ELSIF NEW.source_type='portal_order' THEN\n"
 '            SELECT site_id INTO expected_site FROM portal_orders WHERE id=NEW.source_id;\n'
 "        ELSIF NEW.source_type='session_credit' THEN\n"
 '            SELECT q.site_id INTO expected_site FROM session_fee_credits c JOIN session_fee_quotes q ON '
 'q.id=c.quote_id WHERE c.id=NEW.source_id;\n'
 '        ELSE\n'
 '            SELECT z.site_id INTO expected_site FROM parking_sessions p JOIN parking_slots s ON '
 's.id=p.parking_slot_id JOIN zones z ON z.id=s.zone_id WHERE p.id=NEW.source_id;\n'
 '        END IF;\n'
 "        IF NEW.site_id IS DISTINCT FROM expected_site THEN RAISE EXCEPTION 'payment site mismatch' USING "
 "ERRCODE='23514'; END IF;\n"
 '    END IF;\n'
 '    IF NEW.shift_id IS NOT NULL THEN\n'
 '        SELECT site_id INTO shift_site FROM cash_shifts WHERE id=NEW.shift_id;\n'
 '        IF shift_site IS NOT NULL AND shift_site IS DISTINCT FROM NEW.site_id THEN RAISE EXCEPTION '
 "'payment shift site mismatch' USING ERRCODE='23514'; END IF;\n"
 '    END IF;\n'
 '    RETURN NEW;\n'
 'END; $$ LANGUAGE plpgsql;\n'
 'CREATE TRIGGER trg_payment_site_guard BEFORE INSERT ON payments FOR EACH ROW EXECUTE FUNCTION '
 'parking_payment_site_guard();\n',
 'DROP TRIGGER trg_online_link_guard ON online_payment_links',
 'DROP TRIGGER trg_online_inbox_guard ON online_payment_inbox',
 'DROP TRIGGER trg_online_processing_guard ON online_payment_processing',
 'DROP TRIGGER trg_online_order_delete ON portal_orders',
 'DROP TRIGGER trg_online_review_guard ON online_payment_review_decisions',
 '\n'
 'CREATE OR REPLACE FUNCTION online_payment_guard() RETURNS trigger AS $$\n'
 'BEGIN\n'
 "    IF TG_TABLE_NAME='online_payment_inbox' THEN\n"
 "        RAISE EXCEPTION 'online payment evidence is immutable' USING ERRCODE='23514';\n"
 "    ELSIF TG_TABLE_NAME='online_payment_review_decisions' THEN\n"
 "        IF TG_OP!='INSERT' THEN RAISE EXCEPTION 'online review decision is immutable' USING "
 "ERRCODE='23514'; END IF;\n"
 '        IF NOT EXISTS (SELECT 1 FROM online_payment_inbox i JOIN online_payment_processing p ON p.id=i.id\n'
 "            WHERE i.id=NEW.inbox_id AND p.status='review' AND i.channel=NEW.channel AND "
 'i.reference=NEW.payment_reference\n'
 "            AND (NEW.action='note' OR (NEW.refund_amount=i.amount AND i.currency='VND'\n"
 '                AND (i.verification_issue IS NULL OR i.verification_issue NOT IN '
 "('account_mismatch','currency_mismatch'))\n"
 '                AND NOT EXISTS (SELECT 1 FROM online_payment_links l WHERE l.channel=i.channel AND '
 'l.settled_reference=i.reference)))) THEN\n'
 "            RAISE EXCEPTION 'online review source mismatch' USING ERRCODE='23514';\n"
 '        END IF;\n'
 "    ELSIF TG_TABLE_NAME='portal_orders' THEN\n"
 '        IF EXISTS (SELECT 1 FROM online_payment_links WHERE order_id=OLD.id) THEN\n'
 "            RAISE EXCEPTION 'online payment order must be retained' USING ERRCODE='23514';\n"
 '        END IF;\n'
 "    ELSIF TG_TABLE_NAME='online_payment_processing' THEN\n"
 "        IF TG_OP='DELETE' THEN RAISE EXCEPTION 'online processing must be retained' USING ERRCODE='23514'; "
 'END IF;\n'
 "        IF NEW.id IS DISTINCT FROM OLD.id OR (OLD.status!='received' AND\n"
 '            (NEW.status IS DISTINCT FROM OLD.status OR NEW.reason IS DISTINCT FROM OLD.reason OR\n'
 '             NEW.receipt_id IS DISTINCT FROM OLD.receipt_id OR NEW.processed_at IS DISTINCT FROM '
 'OLD.processed_at)) THEN\n'
 "            RAISE EXCEPTION 'online processing decision is final' USING ERRCODE='23514';\n"
 '        END IF;\n'
 "        IF NEW.status IN ('processed','duplicate') AND NOT EXISTS (SELECT 1 FROM online_payment_inbox i\n"
 '            JOIN online_payment_links l ON l.id=i.link_id WHERE i.id=NEW.id AND '
 'l.receipt_id=NEW.receipt_id\n'
 '            AND l.settled_reference=i.reference AND l.channel=i.channel AND l.id=i.order_code\n'
 '            AND l.amount=i.amount AND l.currency=i.currency AND l.receiver_digest=i.receiver_digest\n'
 '            AND l.payment_link_id=i.payment_link_id) THEN\n'
 "            RAISE EXCEPTION 'online processing receipt mismatch' USING ERRCODE='23514';\n"
 '        END IF;\n'
 '    ELSE\n'
 "        IF TG_OP='DELETE' THEN RAISE EXCEPTION 'online payment identity must be retained' USING "
 "ERRCODE='23514'; END IF;\n"
 "        IF TG_OP='UPDATE' AND (NEW.id IS DISTINCT FROM OLD.id OR NEW.order_id IS DISTINCT FROM "
 'OLD.order_id OR NEW.session_quote_id IS DISTINCT FROM OLD.session_quote_id OR NEW.site_id IS DISTINCT FROM '
 'OLD.site_id OR NEW.channel IS DISTINCT FROM OLD.channel OR NEW.receiver_digest IS DISTINCT FROM '
 'OLD.receiver_digest OR NEW.amount IS DISTINCT FROM OLD.amount OR NEW.currency IS DISTINCT FROM '
 'OLD.currency OR NEW.description IS DISTINCT FROM OLD.description OR NEW.return_url IS DISTINCT FROM '
 'OLD.return_url OR NEW.cancel_url IS DISTINCT FROM OLD.cancel_url OR NEW.expires_at IS DISTINCT FROM '
 'OLD.expires_at OR NEW.created_at IS DISTINCT FROM OLD.created_at OR (OLD.payment_link_id IS NOT NULL AND '
 'NEW.payment_link_id IS DISTINCT FROM OLD.payment_link_id) OR (OLD.settled_reference IS NOT NULL AND '
 'NEW.settled_reference IS DISTINCT FROM OLD.settled_reference) OR (OLD.receipt_id IS NOT NULL AND '
 'NEW.receipt_id IS DISTINCT FROM OLD.receipt_id)) THEN\n'
 "            RAISE EXCEPTION 'online payment identity is immutable' USING ERRCODE='23514';\n"
 '        END IF;\n'
 "        IF TG_OP='INSERT' AND NOT (EXISTS (SELECT 1 FROM portal_orders o WHERE o.id=NEW.order_id AND "
 "o.payment_mode='payos'\n"
 "    AND o.status='pending' AND o.site_id=NEW.site_id AND o.amount=NEW.amount AND NEW.currency='VND'\n"
 '    AND o.expires_at=NEW.expires_at) OR EXISTS (SELECT 1 FROM session_fee_quotes q WHERE '
 'q.id=NEW.session_quote_id\n'
 "    AND q.status='pending' AND q.site_id=NEW.site_id AND q.amount=NEW.amount AND NEW.currency='VND' AND "
 'q.expires_at=NEW.expires_at)) THEN\n'
 "            RAISE EXCEPTION 'online payment source mismatch' USING ERRCODE='23514';\n"
 '        END IF;\n'
 '        IF NEW.receipt_id IS NOT NULL AND (NEW.settled_reference IS NULL OR NOT (EXISTS (SELECT 1 FROM '
 'portal_orders o JOIN payments p ON p.id=o.receipt_id\n'
 "    WHERE o.id=NEW.order_id AND o.receipt_id=NEW.receipt_id AND o.status IN ('fulfilled','refunded')\n"
 "    AND p.kind='receipt' AND p.method='transfer' AND p.collected_by_id IS NULL AND p.amount=NEW.amount)\n"
 '    OR EXISTS (SELECT 1 FROM session_fee_quotes q JOIN session_fee_credits c ON c.id=q.credit_id\n'
 "        JOIN payments p ON p.id=c.receipt_id WHERE q.id=NEW.session_quote_id AND q.status='fulfilled'\n"
 '        AND q.receipt_id=NEW.receipt_id AND c.receipt_id=NEW.receipt_id AND c.quote_id=q.id\n'
 "        AND p.source_type='session_credit' AND p.source_id=c.id AND p.kind='receipt'\n"
 "        AND p.method='transfer' AND p.collected_by_id IS NULL AND p.amount=NEW.amount))) THEN\n"
 "            RAISE EXCEPTION 'online payment receipt mismatch' USING ERRCODE='23514';\n"
 '        END IF;\n'
 '    END IF;\n'
 "    IF TG_OP='DELETE' THEN RETURN OLD; END IF;\n"
 '    RETURN NEW;\n'
 'END; $$ LANGUAGE plpgsql;\n'
 'CREATE TRIGGER trg_online_link_guard BEFORE INSERT OR UPDATE OR DELETE ON online_payment_links FOR EACH '
 'ROW EXECUTE FUNCTION online_payment_guard();\n'
 'CREATE TRIGGER trg_online_inbox_guard BEFORE UPDATE OR DELETE ON online_payment_inbox FOR EACH ROW EXECUTE '
 'FUNCTION online_payment_guard();\n'
 'CREATE TRIGGER trg_online_processing_guard BEFORE UPDATE OR DELETE ON online_payment_processing FOR EACH '
 'ROW EXECUTE FUNCTION online_payment_guard();\n'
 'CREATE TRIGGER trg_online_order_delete BEFORE DELETE ON portal_orders FOR EACH ROW EXECUTE FUNCTION '
 'online_payment_guard();\n'
 'CREATE TRIGGER trg_online_review_guard BEFORE INSERT OR UPDATE OR DELETE ON '
 'online_payment_review_decisions FOR EACH ROW EXECUTE FUNCTION online_payment_guard();\n',
 'DROP TRIGGER trg_parking_reservations_guard ON parking_reservations',
 'DROP TRIGGER trg_guaranteed_allocations_guard ON guaranteed_allocations',
 'DROP TRIGGER trg_slot_commitment_guard ON parking_slots',
 'DROP TRIGGER trg_zone_site_immutable ON zones',
 '\n'
 'CREATE OR REPLACE FUNCTION parking_commitment_guard() RETURNS trigger AS $$\n'
 'DECLARE expected text;\n'
 'BEGIN\n'
 "    expected := CASE WHEN TG_TABLE_NAME='parking_reservations' THEN 'confirmed' ELSE 'active' END;\n"
 "    IF TG_OP='UPDATE' THEN\n"
 '        IF '
 'ROW(NEW.site_id,NEW.slot_id,NEW.customer_id,NEW.vehicle_id,NEW.start_at,NEW.end_at,NEW.request_id,NEW.created_by_id,NEW.created_at)\n'
 '           IS DISTINCT FROM '
 'ROW(OLD.site_id,OLD.slot_id,OLD.customer_id,OLD.vehicle_id,OLD.start_at,OLD.end_at,OLD.request_id,OLD.created_by_id,OLD.created_at)\n'
 '           OR (OLD.status<>expected AND NEW.status<>OLD.status) THEN\n'
 "            RAISE EXCEPTION 'reservation identity or state invalid' USING ERRCODE='23514';\n"
 '        END IF;\n'
 "        IF TG_TABLE_NAME='parking_reservations' THEN\n"
 '            IF NEW.arrival_deadline IS DISTINCT FROM OLD.arrival_deadline\n'
 "               OR (NEW.session_id IS DISTINCT FROM OLD.session_id AND (OLD.status<>'confirmed' OR "
 "NEW.status<>'arrived'))\n"
 "               OR (NEW.status='arrived' AND NOT EXISTS (SELECT 1 FROM parking_sessions s WHERE "
 's.id=NEW.session_id\n'
 '                   AND s.vehicle_id=NEW.vehicle_id AND s.parking_slot_id=NEW.slot_id\n'
 '                   AND s.check_in_time>=NEW.start_at AND s.check_in_time<NEW.arrival_deadline)) THEN\n'
 "                RAISE EXCEPTION 'reservation identity or state invalid' USING ERRCODE='23514';\n"
 '            END IF;\n'
 '        END IF;\n'
 '        RETURN NEW;\n'
 '    END IF;\n'
 '    PERFORM id FROM parking_slots WHERE id=NEW.slot_id FOR UPDATE;\n'
 '    IF NEW.status<>expected OR NOT EXISTS (SELECT 1 FROM parking_slots s JOIN zones z ON z.id=s.zone_id\n'
 '        JOIN vehicles v ON v.id=NEW.vehicle_id JOIN parking_sites p ON p.id=z.site_id\n'
 '        WHERE s.id=NEW.slot_id AND z.site_id=NEW.site_id AND v.customer_id=NEW.customer_id\n'
 '        AND s.vehicle_type_id=v.vehicle_type_id AND s.is_active AND z.is_active AND p.is_active AND NOT '
 's.is_occupied)\n'
 '        OR EXISTS (SELECT 1 FROM parking_reservations r WHERE r.slot_id=NEW.slot_id AND '
 "(r.status='confirmed' OR (r.status='arrived' AND EXISTS (SELECT 1 FROM parking_sessions committed_session "
 "WHERE committed_session.id=r.session_id AND committed_session.status IN ('active','checking_out'))))\n"
 '                   AND r.start_at<NEW.end_at AND r.end_at>NEW.start_at)\n'
 '        OR EXISTS (SELECT 1 FROM guaranteed_allocations a WHERE a.slot_id=NEW.slot_id AND '
 "a.status='active'\n"
 '                   AND a.start_at<NEW.end_at AND a.end_at>NEW.start_at AND NOT\n'
 "                   (TG_TABLE_NAME='parking_reservations' AND a.vehicle_id=NEW.vehicle_id AND "
 'a.start_at<=NEW.start_at AND a.end_at>=NEW.end_at)) THEN\n'
 "        RAISE EXCEPTION 'reservation capacity or source invalid' USING ERRCODE='23514';\n"
 '    END IF;\n'
 '    RETURN NEW;\n'
 'END; $$ LANGUAGE plpgsql;\n'
 'CREATE TRIGGER trg_parking_reservations_guard BEFORE INSERT OR UPDATE ON parking_reservations FOR EACH ROW '
 'EXECUTE FUNCTION parking_commitment_guard();\n'
 'CREATE TRIGGER trg_guaranteed_allocations_guard BEFORE INSERT OR UPDATE ON guaranteed_allocations FOR EACH '
 'ROW EXECUTE FUNCTION parking_commitment_guard();\n'
 'CREATE OR REPLACE FUNCTION parking_slot_commitment_guard() RETURNS trigger AS $$\n'
 'BEGIN\n'
 '    IF (NEW.zone_id IS DISTINCT FROM OLD.zone_id OR NEW.vehicle_type_id IS DISTINCT FROM '
 'OLD.vehicle_type_id OR NOT NEW.is_active)\n'
 "       AND (EXISTS (SELECT 1 FROM parking_reservations r WHERE r.slot_id=OLD.id AND (r.status='confirmed' "
 "OR (r.status='arrived' AND EXISTS (SELECT 1 FROM parking_sessions committed_session WHERE "
 "committed_session.id=r.session_id AND committed_session.status IN ('active','checking_out'))))\n"
 "                    AND r.end_at>CURRENT_TIMESTAMP AT TIME ZONE 'Asia/Ho_Chi_Minh')\n"
 '            OR EXISTS (SELECT 1 FROM guaranteed_allocations a WHERE a.slot_id=OLD.id AND '
 "a.status='active'\n"
 "                       AND a.end_at>CURRENT_TIMESTAMP AT TIME ZONE 'Asia/Ho_Chi_Minh')) THEN\n"
 "        RAISE EXCEPTION 'slot has parking commitments' USING ERRCODE='23514';\n"
 '    END IF;\n'
 '    RETURN NEW;\n'
 'END; $$ LANGUAGE plpgsql;\n'
 'CREATE TRIGGER trg_slot_commitment_guard BEFORE UPDATE ON parking_slots FOR EACH ROW EXECUTE FUNCTION '
 'parking_slot_commitment_guard();\n'
 'CREATE OR REPLACE FUNCTION parking_zone_site_guard() RETURNS trigger AS $$\n'
 'BEGIN\n'
 '    IF OLD.site_id IS NOT NULL AND NEW.site_id IS DISTINCT FROM OLD.site_id THEN\n'
 "        RAISE EXCEPTION 'zone site identity is immutable' USING ERRCODE='23514';\n"
 '    END IF;\n'
 '    RETURN NEW;\n'
 'END; $$ LANGUAGE plpgsql;\n'
 'CREATE TRIGGER trg_zone_site_immutable BEFORE UPDATE OF site_id ON zones FOR EACH ROW EXECUTE FUNCTION '
 'parking_zone_site_guard();\n',
 'DROP TRIGGER trg_zone_commitment_guard ON zones',
 '\n'
 'CREATE OR REPLACE FUNCTION parking_zone_commitment_guard() RETURNS trigger AS $$\n'
 'BEGIN\n'
 '    IF NOT NEW.is_active AND OLD.is_active AND (\n'
 '        EXISTS (SELECT 1 FROM parking_reservations r JOIN parking_slots s ON s.id=r.slot_id\n'
 "                WHERE s.zone_id=OLD.id AND (r.status='confirmed' OR (r.status='arrived' AND EXISTS (SELECT "
 '1 FROM parking_sessions committed_session WHERE committed_session.id=r.session_id AND '
 "committed_session.status IN ('active','checking_out'))))\n"
 "                AND r.end_at>CURRENT_TIMESTAMP AT TIME ZONE 'Asia/Ho_Chi_Minh')\n"
 '        OR EXISTS (SELECT 1 FROM guaranteed_allocations a JOIN parking_slots s ON s.id=a.slot_id\n'
 "                   WHERE s.zone_id=OLD.id AND a.status='active'\n"
 "                   AND a.end_at>CURRENT_TIMESTAMP AT TIME ZONE 'Asia/Ho_Chi_Minh')) THEN\n"
 "        RAISE EXCEPTION 'zone has parking commitments' USING ERRCODE='23514';\n"
 '    END IF;\n'
 '    RETURN NEW;\n'
 'END; $$ LANGUAGE plpgsql;\n'
 'CREATE TRIGGER trg_zone_commitment_guard BEFORE UPDATE OF is_active ON zones\n'
 'FOR EACH ROW EXECUTE FUNCTION parking_zone_commitment_guard();\n',
 'DROP TRIGGER trg_capacity_hold_insert ON parking_capacity_holds',
 'CREATE OR REPLACE FUNCTION trg_capacity_hold_insert_fn() RETURNS trigger AS $$\n'
 'BEGIN\n'
 '    PERFORM 1 FROM vehicles WHERE id=NEW.vehicle_id FOR NO KEY UPDATE; PERFORM 1 FROM vehicle_types WHERE '
 'id=(SELECT vehicle_type_id FROM vehicles WHERE id=NEW.vehicle_id) FOR SHARE; PERFORM 1 FROM parking_slots '
 'WHERE id=NEW.slot_id FOR UPDATE;\n'
 "    IF NEW.status!='held' OR NEW.reservation_id IS NOT NULL OR NOT EXISTS (SELECT 1 FROM portal_orders o "
 'JOIN parking_slots s ON s.id=o.slot_id JOIN zones z ON z.id=s.zone_id JOIN parking_sites p ON '
 'p.id=z.site_id JOIN vehicles v ON v.id=o.vehicle_id JOIN vehicle_types t ON t.id=v.vehicle_type_id WHERE '
 "o.id=NEW.order_id AND o.status='pending' AND o.product_kind IN ('hourly','daily') AND "
 'o.slot_id=NEW.slot_id AND o.site_id=NEW.site_id AND o.customer_id=NEW.customer_id AND '
 'o.vehicle_id=NEW.vehicle_id AND o.start_at=NEW.start_at AND o.end_at=NEW.end_at AND '
 'o.expires_at=NEW.expires_at AND v.customer_id=o.customer_id AND s.vehicle_type_id=v.vehicle_type_id AND '
 't.is_active IS TRUE AND s.is_active IS TRUE AND z.is_active IS TRUE AND p.is_active IS TRUE AND '
 's.is_occupied IS FALSE) OR EXISTS (SELECT 1 FROM parking_capacity_holds h WHERE h.slot_id=NEW.slot_id AND '
 "h.status='held' AND h.expires_at>(clock_timestamp() AT TIME ZONE 'Asia/Ho_Chi_Minh') AND "
 'h.start_at<NEW.end_at AND h.end_at>NEW.start_at) OR EXISTS (SELECT 1 FROM parking_sessions s WHERE '
 "s.parking_slot_id=NEW.slot_id AND s.status IN ('active','checking_out')) OR EXISTS (SELECT 1 FROM "
 "parking_reservations r WHERE r.slot_id=NEW.slot_id AND (r.status='confirmed' OR (r.status='arrived' AND "
 'EXISTS (SELECT 1 FROM parking_sessions committed_session WHERE committed_session.id=r.session_id AND '
 "committed_session.status IN ('active','checking_out')))) AND r.start_at<NEW.end_at AND "
 'r.end_at>NEW.start_at) OR EXISTS (SELECT 1 FROM guaranteed_allocations a WHERE a.slot_id=NEW.slot_id AND '
 "a.status='active' AND a.start_at<NEW.end_at AND a.end_at>NEW.start_at) THEN RAISE EXCEPTION 'capacity hold "
 "source or overlap invalid' USING ERRCODE='23514'; END IF;\n"
 '    RETURN NEW;\n'
 'END; $$ LANGUAGE plpgsql;\n'
 'CREATE TRIGGER trg_capacity_hold_insert BEFORE INSERT ON parking_capacity_holds FOR EACH ROW EXECUTE '
 'FUNCTION trg_capacity_hold_insert_fn();\n',
 '\n'
 'CREATE OR REPLACE FUNCTION session_payment_guard() RETURNS trigger AS $$\n'
 'BEGIN\n'
 "    IF TG_TABLE_NAME='payments' THEN\n"
 "        IF NEW.source_type='session_credit' AND ((NEW.kind='receipt' AND NOT EXISTS (SELECT 1 FROM "
 'session_fee_credits c JOIN session_fee_quotes q ON q.id=c.quote_id\n'
 '    JOIN parking_sessions s ON s.id=c.session_id WHERE c.id=NEW.source_id AND c.amount=NEW.amount\n'
 "    AND q.session_id=s.id AND s.status='active' AND q.status IN ('pending','expired')\n"
 "    AND q.site_id IS NOT DISTINCT FROM NEW.site_id AND NEW.method='transfer' AND NEW.collected_by_id IS "
 'NULL AND NEW.shift_id IS NULL))\n'
 "            OR (NEW.kind='refund' AND NOT EXISTS (SELECT 1 FROM session_fee_credits c JOIN "
 'parking_sessions s ON s.id=c.session_id\n'
 "    WHERE c.id=NEW.source_id AND s.status='completed'))) THEN\n"
 "            RAISE EXCEPTION 'session credit payment source invalid' USING ERRCODE='23514';\n"
 '        END IF;\n'
 "    ELSIF TG_TABLE_NAME='parking_sessions' THEN\n"
 "        IF TG_OP='DELETE' AND EXISTS (SELECT 1 FROM session_fee_quotes WHERE session_id=OLD.id) THEN\n"
 "            RAISE EXCEPTION 'session fee history must be retained' USING ERRCODE='23514';\n"
 "        ELSIF TG_OP='UPDATE' AND NEW.status='cancelled' AND (EXISTS (SELECT 1 FROM session_fee_credits "
 'WHERE session_id=OLD.id)\n'
 '            OR EXISTS (SELECT 1 FROM session_fee_quotes q JOIN online_payment_links l ON '
 'l.session_quote_id=q.id\n'
 "    WHERE q.session_id=OLD.id AND (l.state IN ('creating','unknown','ready','review') OR EXISTS (\n"
 '        SELECT 1 FROM online_payment_inbox i JOIN online_payment_processing p ON p.id=i.id\n'
 "        WHERE i.link_id=l.id AND p.status='received')))) THEN\n"
 "            RAISE EXCEPTION 'session has online funds or outstanding link' USING ERRCODE='23514';\n"
 '        END IF;\n'
 "    ELSIF TG_TABLE_NAME='session_fee_quotes' THEN\n"
 "        IF TG_OP='DELETE' THEN RAISE EXCEPTION 'session fee quote must be retained' USING ERRCODE='23514'; "
 'END IF;\n'
 "        IF TG_OP='INSERT' AND (NEW.status!='pending' OR NEW.credit_id IS NOT NULL OR NEW.receipt_id IS NOT "
 'NULL OR NOT EXISTS (SELECT 1 FROM parking_sessions s JOIN parking_slots slot ON slot.id=s.parking_slot_id\n'
 "    JOIN zones z ON z.id=slot.zone_id WHERE s.id=NEW.session_id AND s.status='active'\n"
 "    AND s.billing_policy_version IN ('entry-v1','prepaid-window-v1') AND z.site_id=NEW.site_id\n"
 '    AND NEW.owner_customer_id IS NOT DISTINCT FROM (SELECT g.customer_id FROM portal_session_grants g '
 'WHERE g.parking_session_id=s.id)\n'
 '    AND NEW.credited_amount=COALESCE((SELECT SUM(c.amount) FROM session_fee_credits c WHERE '
 'c.session_id=s.id AND c.receipt_id IS DISTINCT FROM NULL),0))) THEN\n'
 "            RAISE EXCEPTION 'session fee quote source invalid' USING ERRCODE='23514';\n"
 '        END IF;\n'
 "        IF TG_OP='UPDATE' AND (NEW.id IS DISTINCT FROM OLD.id OR NEW.session_id IS DISTINCT FROM "
 'OLD.session_id OR NEW.site_id IS DISTINCT FROM OLD.site_id OR NEW.created_by_id IS DISTINCT FROM '
 'OLD.created_by_id OR NEW.owner_customer_id IS DISTINCT FROM OLD.owner_customer_id OR NEW.request_id IS '
 'DISTINCT FROM OLD.request_id OR NEW.session_state_hash IS DISTINCT FROM OLD.session_state_hash OR '
 'NEW.credit_snapshot_hash IS DISTINCT FROM OLD.credit_snapshot_hash OR NEW.gross_fee IS DISTINCT FROM '
 'OLD.gross_fee OR NEW.credited_amount IS DISTINCT FROM OLD.credited_amount OR NEW.amount IS DISTINCT FROM '
 'OLD.amount OR NEW.quoted_at IS DISTINCT FROM OLD.quoted_at OR NEW.paid_through IS DISTINCT FROM '
 'OLD.paid_through OR NEW.expires_at IS DISTINCT FROM OLD.expires_at OR NEW.billing_basis::text IS DISTINCT '
 'FROM OLD.billing_basis::text OR (OLD.receipt_id IS DISTINCT FROM NULL AND NEW.receipt_id IS DISTINCT FROM '
 'OLD.receipt_id) OR (OLD.credit_id IS DISTINCT FROM NULL AND NEW.credit_id IS DISTINCT FROM OLD.credit_id)) '
 'THEN\n'
 "            RAISE EXCEPTION 'session fee quote snapshot immutable' USING ERRCODE='23514';\n"
 '        END IF;\n'
 "        IF TG_OP='UPDATE' AND ((OLD.status='fulfilled' AND NEW.status!='fulfilled') OR\n"
 "            (OLD.status='cancelled' AND NEW.status NOT IN ('cancelled','review')) OR (OLD.status='review' "
 "AND NEW.status!='review')) THEN\n"
 "            RAISE EXCEPTION 'session fee quote terminal' USING ERRCODE='23514';\n"
 '        END IF;\n'
 "        IF NEW.status='fulfilled' AND NOT EXISTS (SELECT 1 FROM session_fee_credits c WHERE "
 'c.id=NEW.credit_id AND c.quote_id=NEW.id\n'
 '    AND c.session_id=NEW.session_id AND c.amount=NEW.amount AND c.paid_through=NEW.paid_through\n'
 '    AND c.receipt_id=NEW.receipt_id) THEN\n'
 "            RAISE EXCEPTION 'session fee quote credit mismatch' USING ERRCODE='23514';\n"
 '        END IF;\n'
 '    ELSE\n'
 "        IF TG_OP='DELETE' THEN RAISE EXCEPTION 'session fee credit must be retained' USING "
 "ERRCODE='23514'; END IF;\n"
 "        IF TG_OP='INSERT' AND (NEW.receipt_id IS NOT NULL OR NOT EXISTS (SELECT 1 FROM session_fee_quotes "
 'q JOIN parking_sessions s ON s.id=q.session_id\n'
 '    JOIN online_payment_links l ON l.session_quote_id=q.id WHERE q.id=NEW.quote_id AND '
 's.id=NEW.session_id\n'
 "    AND s.status='active' AND q.status IN ('pending','expired') AND NEW.amount=q.amount AND "
 'NEW.paid_through=q.paid_through\n'
 '    AND q.credited_amount=COALESCE((SELECT SUM(c.amount) FROM session_fee_credits c WHERE '
 'c.session_id=s.id AND c.receipt_id IS DISTINCT FROM NULL),0)\n'
 '    AND EXISTS (SELECT 1 FROM online_payment_inbox i JOIN online_payment_processing p ON p.id=i.id\n'
 "        WHERE i.link_id=l.id AND p.status='received' AND i.amount=q.amount AND i.currency='VND'\n"
 '        AND i.receiver_digest=l.receiver_digest AND i.payment_link_id=l.payment_link_id\n'
 '        AND i.received_at<q.expires_at AND i.verification_issue IS NULL))) THEN\n'
 "            RAISE EXCEPTION 'session fee credit source invalid' USING ERRCODE='23514';\n"
 '        END IF;\n'
 "        IF TG_OP='UPDATE' AND (NEW.id IS DISTINCT FROM OLD.id OR NEW.session_id IS DISTINCT FROM "
 'OLD.session_id OR NEW.quote_id IS DISTINCT FROM OLD.quote_id OR NEW.amount IS DISTINCT FROM OLD.amount OR '
 'NEW.paid_through IS DISTINCT FROM OLD.paid_through OR NEW.created_at IS DISTINCT FROM OLD.created_at OR '
 '(OLD.receipt_id IS DISTINCT FROM NULL AND NEW.receipt_id IS DISTINCT FROM OLD.receipt_id)) THEN\n'
 "            RAISE EXCEPTION 'session fee credit immutable' USING ERRCODE='23514';\n"
 '        END IF;\n'
 '        IF NEW.receipt_id IS NOT NULL AND NOT EXISTS (SELECT 1 FROM payments p WHERE p.id=NEW.receipt_id '
 "AND p.source_type='session_credit'\n"
 "    AND p.source_id=NEW.id AND p.kind='receipt' AND p.amount=NEW.amount AND p.method='transfer'\n"
 '    AND p.collected_by_id IS NULL AND p.shift_id IS NULL) THEN\n'
 "            RAISE EXCEPTION 'session fee credit receipt invalid' USING ERRCODE='23514';\n"
 '        END IF;\n'
 '    END IF;\n'
 "    IF TG_OP='DELETE' THEN RETURN OLD; END IF;\n"
 '    RETURN NEW;\n'
 'END; $$ LANGUAGE plpgsql;\n'
 'CREATE TRIGGER trg_session_fee_quote_guard BEFORE INSERT OR UPDATE OR DELETE ON session_fee_quotes FOR '
 'EACH ROW EXECUTE FUNCTION session_payment_guard();\n'
 'CREATE TRIGGER trg_session_fee_credit_guard BEFORE INSERT OR UPDATE OR DELETE ON session_fee_credits FOR '
 'EACH ROW EXECUTE FUNCTION session_payment_guard();\n'
 'CREATE TRIGGER trg_session_fee_payment_source BEFORE INSERT ON payments FOR EACH ROW EXECUTE FUNCTION '
 'session_payment_guard();\n'
 'CREATE TRIGGER trg_session_fee_session_guard BEFORE UPDATE OR DELETE ON parking_sessions FOR EACH ROW '
 'EXECUTE FUNCTION session_payment_guard();\n')


def upgrade():
    for sql in UPGRADE_SQL:
        op.execute(sql)


def downgrade():
    raise RuntimeError("Keep credits and settlement history; use a compatible application or a forward migration.")
