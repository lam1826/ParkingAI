"""Frozen additive online payments schema; no historical data rewritten."""
from alembic import op

revision = "20260915_04"
down_revision = "20260915_03"
branch_labels = None
depends_on = None

UPGRADE_SQL = ('ALTER TABLE portal_orders DROP CONSTRAINT ck_portal_order_mode',
 'ALTER TABLE portal_orders ADD CONSTRAINT ck_portal_order_mode CHECK(payment_mode IN '
 "('demo','manual','payos'))",
 '\n'
 'CREATE TABLE online_payment_links (\n'
 '\tid BIGSERIAL NOT NULL, \n'
 '\torder_id VARCHAR(36) NOT NULL, \n'
 '\tsite_id INTEGER NOT NULL, \n'
 '\tchannel VARCHAR(64) NOT NULL, \n'
 '\treceiver_digest VARCHAR(64) NOT NULL, \n'
 '\tamount BIGINT NOT NULL, \n'
 '\tcurrency VARCHAR(3) NOT NULL, \n'
 '\tdescription VARCHAR(9) NOT NULL, \n'
 '\treturn_url VARCHAR(2048) NOT NULL, \n'
 '\tcancel_url VARCHAR(2048) NOT NULL, \n'
 '\texpires_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, \n'
 '\tcreated_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, \n'
 '\tstate VARCHAR(12) NOT NULL, \n'
 '\tprovider_status VARCHAR(12), \n'
 '\tpayment_link_id VARCHAR(64), \n'
 '\tcheckout_url VARCHAR(2048), \n'
 '\tqr_code TEXT, \n'
 '\tsettled_reference VARCHAR(64), \n'
 '\treceipt_id VARCHAR(36), \n'
 '\treview_reason VARCHAR(100), \n'
 '\tlast_error VARCHAR(100), \n'
 '\toperation_token VARCHAR(36), \n'
 '\toperation_until TIMESTAMP WITHOUT TIME ZONE, \n'
 '\tlast_checked_at TIMESTAMP WITHOUT TIME ZONE, \n'
 '\tPRIMARY KEY (id), \n'
 '\tCONSTRAINT ck_online_link_code CHECK (id > 0 AND id <= 9007199254740991), \n'
 "\tCONSTRAINT ck_online_link_amount CHECK (amount > 0 AND amount <= 9007199254740991 AND currency='VND'), \n"
 '\tCONSTRAINT ck_online_link_state CHECK (state IN '
 "('creating','unknown','ready','paid','cancelled','expired','review')), \n"
 '\tUNIQUE (order_id), \n'
 '\tFOREIGN KEY(order_id) REFERENCES portal_orders (id), \n'
 '\tFOREIGN KEY(site_id) REFERENCES parking_sites (id), \n'
 '\tUNIQUE (payment_link_id), \n'
 '\tUNIQUE (receipt_id), \n'
 '\tFOREIGN KEY(receipt_id) REFERENCES payments (id)\n'
 ')\n'
 '\n',
 'CREATE INDEX ix_online_payment_links_channel ON online_payment_links (channel)',
 'CREATE INDEX ix_online_payment_links_site_id ON online_payment_links (site_id)',
 '\n'
 'CREATE TABLE online_payment_inbox (\n'
 '\tid VARCHAR(36) NOT NULL, \n'
 '\tlink_id BIGINT, \n'
 '\tsite_id INTEGER NOT NULL, \n'
 '\tchannel VARCHAR(64) NOT NULL, \n'
 '\tsource VARCHAR(12) NOT NULL, \n'
 '\torder_code BIGINT NOT NULL, \n'
 '\tpayment_link_id VARCHAR(64) NOT NULL, \n'
 '\treference VARCHAR(64) NOT NULL, \n'
 '\tamount BIGINT NOT NULL, \n'
 '\tcurrency VARCHAR(3) NOT NULL, \n'
 '\treceiver_digest VARCHAR(64) NOT NULL, \n'
 '\ttransaction_time VARCHAR(64) NOT NULL, \n'
 '\tpayload_digest VARCHAR(64) NOT NULL, \n'
 '\treceived_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, \n'
 '\tverification_issue VARCHAR(100), \n'
 '\tPRIMARY KEY (id), \n'
 '\tCONSTRAINT uq_online_inbox_evidence UNIQUE (channel, reference, payload_digest), \n'
 '\tCONSTRAINT ck_online_inbox_amount CHECK (amount > 0 AND amount <= 9007199254740991), \n'
 '\tCONSTRAINT ck_online_inbox_code CHECK (order_code > 0 AND order_code <= 9007199254740991), \n'
 "\tCONSTRAINT ck_online_inbox_source CHECK (source IN ('webhook','reconcile')), \n"
 '\tFOREIGN KEY(link_id) REFERENCES online_payment_links (id), \n'
 '\tFOREIGN KEY(site_id) REFERENCES parking_sites (id)\n'
 ')\n'
 '\n',
 'CREATE INDEX ix_online_payment_inbox_channel ON online_payment_inbox (channel)',
 'CREATE INDEX ix_online_payment_inbox_link_id ON online_payment_inbox (link_id)',
 'CREATE INDEX ix_online_payment_inbox_reference ON online_payment_inbox (reference)',
 'CREATE INDEX ix_online_payment_inbox_site_id ON online_payment_inbox (site_id)',
 '\n'
 'CREATE TABLE online_payment_processing (\n'
 '\tid VARCHAR(36) NOT NULL, \n'
 '\tstatus VARCHAR(12) NOT NULL, \n'
 '\treason VARCHAR(100), \n'
 '\tattempts INTEGER NOT NULL, \n'
 '\tnext_attempt_at TIMESTAMP WITHOUT TIME ZONE, \n'
 '\treceipt_id VARCHAR(36), \n'
 '\tprocessed_at TIMESTAMP WITHOUT TIME ZONE, \n'
 '\tPRIMARY KEY (id), \n'
 '\tCONSTRAINT ck_online_processing_status CHECK (status IN '
 "('received','processed','duplicate','review')), \n"
 '\tCONSTRAINT ck_online_processing_attempts CHECK (attempts >= 0), \n'
 "\tCONSTRAINT ck_online_processing_receipt CHECK ((status IN ('processed','duplicate') AND receipt_id IS "
 "NOT NULL) OR (status NOT IN ('processed','duplicate') AND receipt_id IS NULL)), \n"
 "\tCONSTRAINT ck_online_processing_time CHECK ((status='received' AND processed_at IS NULL) OR "
 "(status!='received' AND processed_at IS NOT NULL)), \n"
 '\tFOREIGN KEY(id) REFERENCES online_payment_inbox (id), \n'
 '\tFOREIGN KEY(receipt_id) REFERENCES payments (id)\n'
 ')\n'
 '\n',
 'CREATE INDEX ix_online_payment_processing_next_attempt_at ON online_payment_processing (next_attempt_at)',
 'CREATE INDEX ix_online_payment_processing_status ON online_payment_processing (status)',
 '\n'
 'CREATE TABLE online_payment_review_decisions (\n'
 '\tid VARCHAR(36) NOT NULL, \n'
 '\tinbox_id VARCHAR(36) NOT NULL, \n'
 '\tchannel VARCHAR(64) NOT NULL, \n'
 '\tpayment_reference VARCHAR(64) NOT NULL, \n'
 '\taction VARCHAR(32) NOT NULL, \n'
 '\trequest_id VARCHAR(64) NOT NULL, \n'
 '\treason VARCHAR(500) NOT NULL, \n'
 '\tactor_id INTEGER NOT NULL, \n'
 '\tactor_username VARCHAR(50) NOT NULL, \n'
 '\trefund_amount BIGINT, \n'
 '\texternal_reference VARCHAR(120), \n'
 '\tcreated_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, \n'
 '\tPRIMARY KEY (id), \n'
 '\tCONSTRAINT uq_online_review_request UNIQUE (inbox_id, request_id), \n'
 "\tCONSTRAINT ck_online_review_action CHECK (action IN ('note','confirmed_external_refund')), \n"
 '\tCONSTRAINT ck_online_review_reason CHECK (length(trim(reason)) BETWEEN 3 AND 500 AND actor_id>0), \n'
 "\tCONSTRAINT ck_online_review_refund CHECK ((action='note' AND refund_amount IS NULL AND "
 "external_reference IS NULL) OR (action='confirmed_external_refund' AND refund_amount>0 AND "
 'refund_amount<=9007199254740991 AND length(trim(external_reference)) BETWEEN 3 AND 120)), \n'
 '\tFOREIGN KEY(inbox_id) REFERENCES online_payment_inbox (id)\n'
 ')\n'
 '\n',
 'CREATE INDEX ix_online_payment_review_decisions_inbox_id ON online_payment_review_decisions (inbox_id)',
 'CREATE UNIQUE INDEX uq_online_review_final_reference ON online_payment_review_decisions (channel, '
 "payment_reference) WHERE action='confirmed_external_refund'",
 'DROP TRIGGER trg_payment_prepaid_source ON payments',
 'CREATE OR REPLACE FUNCTION trg_payment_prepaid_source_fn() RETURNS trigger AS $$\n'
 'BEGIN\n'
 '    \n'
 "    IF NEW.source_type='portal_order' AND NEW.kind='receipt' AND NOT EXISTS (SELECT 1 FROM portal_orders o "
 'JOIN timed_parking_passes t ON t.order_id=o.id WHERE o.id=NEW.source_id AND o.amount=NEW.amount AND '
 "o.site_id=NEW.site_id AND o.product_kind IN ('hourly','daily') AND ((o.payment_mode='demo' AND "
 "NEW.method='demo') OR (o.payment_mode='manual' AND NEW.method IN ('cash','transfer')) OR "
 "(o.payment_mode='payos' AND NEW.method='transfer' AND NEW.collected_by_id IS NULL))) THEN RAISE EXCEPTION "
 "'prepaid payment source or scope invalid' USING ERRCODE='23514'; END IF;\n"
 '    RETURN NEW;\n'
 'END; $$ LANGUAGE plpgsql;\n'
 'CREATE TRIGGER trg_payment_prepaid_source BEFORE INSERT ON payments FOR EACH ROW EXECUTE FUNCTION '
 'trg_payment_prepaid_source_fn();\n',
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
 'OLD.order_id OR NEW.site_id IS DISTINCT FROM OLD.site_id OR NEW.channel IS DISTINCT FROM OLD.channel OR '
 'NEW.receiver_digest IS DISTINCT FROM OLD.receiver_digest OR NEW.amount IS DISTINCT FROM OLD.amount OR '
 'NEW.currency IS DISTINCT FROM OLD.currency OR NEW.description IS DISTINCT FROM OLD.description OR '
 'NEW.return_url IS DISTINCT FROM OLD.return_url OR NEW.cancel_url IS DISTINCT FROM OLD.cancel_url OR '
 'NEW.expires_at IS DISTINCT FROM OLD.expires_at OR NEW.created_at IS DISTINCT FROM OLD.created_at OR '
 '(OLD.payment_link_id IS NOT NULL AND NEW.payment_link_id IS DISTINCT FROM OLD.payment_link_id) OR '
 '(OLD.settled_reference IS NOT NULL AND NEW.settled_reference IS DISTINCT FROM OLD.settled_reference) OR '
 '(OLD.receipt_id IS NOT NULL AND NEW.receipt_id IS DISTINCT FROM OLD.receipt_id)) THEN\n'
 "            RAISE EXCEPTION 'online payment identity is immutable' USING ERRCODE='23514';\n"
 '        END IF;\n'
 "        IF TG_OP='INSERT' AND NOT EXISTS (SELECT 1 FROM portal_orders o WHERE o.id=NEW.order_id\n"
 "            AND o.payment_mode='payos' AND o.status='pending' AND o.site_id=NEW.site_id\n"
 "            AND o.amount=NEW.amount AND NEW.currency='VND' AND o.expires_at=NEW.expires_at) THEN\n"
 "            RAISE EXCEPTION 'online payment source mismatch' USING ERRCODE='23514';\n"
 '        END IF;\n'
 '        IF NEW.receipt_id IS NOT NULL AND (NEW.settled_reference IS NULL OR NOT EXISTS\n'
 '            (SELECT 1 FROM portal_orders o JOIN payments p ON p.id=o.receipt_id WHERE o.id=NEW.order_id\n'
 "             AND o.receipt_id=NEW.receipt_id AND o.status IN ('fulfilled','refunded') AND "
 "p.method='transfer'\n"
 '             AND p.collected_by_id IS NULL AND p.amount=NEW.amount)) THEN\n'
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
 'online_payment_review_decisions FOR EACH ROW EXECUTE FUNCTION online_payment_guard();\n')


def upgrade():
    for sql in UPGRADE_SQL:
        op.execute(sql)


def downgrade():
    raise RuntimeError("Keep payment history and use a compatible application or forward migration; destructive downgrade is unsupported.")
