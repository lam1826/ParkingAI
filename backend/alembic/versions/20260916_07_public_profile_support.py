"""Public lot profile columns, customer support threads and receipt-based refund requests.

Additive only: existing rows, receipts and the legacy portal_refund_requests
history are untouched. Money movement stays in ``payments``; the new refund
request table only records the customer's request and the manager's decision.
"""
from alembic import op

revision = "20260916_07"
down_revision = "20260915_06"
branch_labels = None
depends_on = None

UPGRADE_SQL = (
    "ALTER TABLE parking_sites ADD COLUMN public_description VARCHAR(2000)",
    "ALTER TABLE parking_sites ADD COLUMN public_opening_hours VARCHAR(500)",
    "ALTER TABLE parking_sites ADD COLUMN public_contact_phone VARCHAR(20)",
    "ALTER TABLE parking_sites ADD COLUMN public_contact_email VARCHAR(100)",
    "ALTER TABLE parking_sites ADD COLUMN latitude FLOAT",
    "ALTER TABLE parking_sites ADD COLUMN longitude FLOAT",
    "ALTER TABLE parking_sites ADD COLUMN public_profile_updated_at TIMESTAMP WITHOUT TIME ZONE",
    "ALTER TABLE parking_sites ADD COLUMN public_profile_updated_by_id INTEGER REFERENCES users (id)",
    ('\n'
     'CREATE TABLE customer_support_requests (\n'
     '\tid VARCHAR(36) NOT NULL, \n'
     '\tsite_id INTEGER NOT NULL, \n'
     '\tcustomer_id INTEGER NOT NULL, \n'
     '\tuser_id INTEGER NOT NULL, \n'
     '\tsubject VARCHAR(150) NOT NULL, \n'
     '\tcategory VARCHAR(16) NOT NULL, \n'
     '\tstatus VARCHAR(12) NOT NULL, \n'
     '\tlinked_type VARCHAR(16), \n'
     '\tlinked_id VARCHAR(36), \n'
     '\tcreated_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, \n'
     '\tupdated_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, \n'
     '\tlast_message_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, \n'
     '\tclosed_at TIMESTAMP WITHOUT TIME ZONE, \n'
     '\tclosed_by_id INTEGER, \n'
     '\tPRIMARY KEY (id), \n'
     "\tCONSTRAINT ck_support_request_category CHECK (category IN ('general','order','session','receipt','refund')), \n"
     "\tCONSTRAINT ck_support_request_status CHECK (status IN ('open','answered','closed')), \n"
     "\tCONSTRAINT ck_support_request_link CHECK ((linked_type IS NULL AND linked_id IS NULL) OR (linked_type IN ('order','session','receipt','refund_request') AND linked_id IS NOT NULL)), \n"
     '\tCONSTRAINT ck_support_request_subject CHECK (length(trim(subject)) BETWEEN 3 AND 150), \n'
     "\tCONSTRAINT ck_support_request_closed CHECK (status != 'closed' OR (closed_at IS NOT NULL AND closed_by_id IS NOT NULL)), \n"
     '\tFOREIGN KEY(site_id) REFERENCES parking_sites (id), \n'
     '\tFOREIGN KEY(customer_id) REFERENCES customers (id), \n'
     '\tFOREIGN KEY(user_id) REFERENCES users (id), \n'
     '\tFOREIGN KEY(closed_by_id) REFERENCES users (id)\n'
     ')'),
    "CREATE INDEX ix_customer_support_requests_customer_id ON customer_support_requests (customer_id)",
    "CREATE INDEX ix_support_request_site_status ON customer_support_requests (site_id, status, last_message_at)",
    ('\n'
     'CREATE TABLE customer_support_messages (\n'
     '\tid VARCHAR(36) NOT NULL, \n'
     '\trequest_id VARCHAR(36) NOT NULL, \n'
     '\tauthor_id INTEGER NOT NULL, \n'
     '\tauthor_role VARCHAR(12) NOT NULL, \n'
     '\tbody VARCHAR(2000) NOT NULL, \n'
     '\tcreated_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, \n'
     '\tPRIMARY KEY (id), \n'
     "\tCONSTRAINT ck_support_message_role CHECK (author_role IN ('customer','staff','manager','admin')), \n"
     '\tCONSTRAINT ck_support_message_body CHECK (length(trim(body)) BETWEEN 1 AND 2000), \n'
     '\tFOREIGN KEY(request_id) REFERENCES customer_support_requests (id), \n'
     '\tFOREIGN KEY(author_id) REFERENCES users (id)\n'
     ')'),
    "CREATE INDEX ix_customer_support_messages_request_id ON customer_support_messages (request_id)",
    ('\n'
     'CREATE TABLE payment_refund_requests (\n'
     '\tid VARCHAR(36) NOT NULL, \n'
     '\treceipt_id VARCHAR(36) NOT NULL, \n'
     '\tsite_id INTEGER, \n'
     '\tcustomer_id INTEGER NOT NULL, \n'
     '\tuser_id INTEGER NOT NULL, \n'
     '\tsource_type VARCHAR(24) NOT NULL, \n'
     '\tsource_id VARCHAR(36) NOT NULL, \n'
     '\tpayment_channel VARCHAR(8) NOT NULL, \n'
     '\treceipt_method VARCHAR(16) NOT NULL, \n'
     '\treason VARCHAR(500) NOT NULL, \n'
     '\trequested_amount BIGINT NOT NULL, \n'
     '\tstatus VARCHAR(12) NOT NULL, \n'
     '\tapproved_amount BIGINT, \n'
     '\tdecision_note VARCHAR(500) NOT NULL, \n'
     '\treviewed_by_id INTEGER, \n'
     '\treviewed_at TIMESTAMP WITHOUT TIME ZONE, \n'
     '\trefund_payment_id VARCHAR(36), \n'
     '\trefund_method VARCHAR(16), \n'
     '\texternal_reference VARCHAR(120), \n'
     '\trefunded_by_id INTEGER, \n'
     '\trefunded_at TIMESTAMP WITHOUT TIME ZONE, \n'
     '\tcreated_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, \n'
     '\tupdated_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, \n'
     '\tPRIMARY KEY (id), \n'
     "\tCONSTRAINT ck_refund_request_status CHECK (status IN ('pending','reviewing','approved','rejected','refunded')), \n"
     "\tCONSTRAINT ck_refund_request_channel CHECK (payment_channel IN ('demo','counter','online','legacy')), \n"
     '\tCONSTRAINT ck_refund_request_amount CHECK (requested_amount > 0 AND requested_amount <= 9007199254740991), \n'
     '\tCONSTRAINT ck_refund_request_approved CHECK (approved_amount IS NULL OR (approved_amount > 0 AND approved_amount <= requested_amount)), \n'
     "\tCONSTRAINT ck_refund_request_approved_amount CHECK (status NOT IN ('approved','refunded') OR approved_amount IS NOT NULL), \n"
     "\tCONSTRAINT ck_refund_request_reviewed CHECK (status NOT IN ('approved','rejected','refunded') OR (reviewed_at IS NOT NULL AND reviewed_by_id IS NOT NULL)), \n"
     "\tCONSTRAINT ck_refund_request_refunded CHECK ((status = 'refunded' AND refund_payment_id IS NOT NULL AND refunded_at IS NOT NULL AND refunded_by_id IS NOT NULL AND refund_method IS NOT NULL) OR (status != 'refunded' AND refund_payment_id IS NULL AND refunded_at IS NULL)), \n"
     '\tFOREIGN KEY(receipt_id) REFERENCES payments (id), \n'
     '\tFOREIGN KEY(site_id) REFERENCES parking_sites (id), \n'
     '\tFOREIGN KEY(customer_id) REFERENCES customers (id), \n'
     '\tFOREIGN KEY(user_id) REFERENCES users (id), \n'
     '\tFOREIGN KEY(reviewed_by_id) REFERENCES users (id), \n'
     '\tUNIQUE (refund_payment_id), \n'
     '\tFOREIGN KEY(refund_payment_id) REFERENCES payments (id), \n'
     '\tFOREIGN KEY(refunded_by_id) REFERENCES users (id)\n'
     ')'),
    "CREATE INDEX ix_payment_refund_requests_customer_id ON payment_refund_requests (customer_id)",
    "CREATE INDEX ix_payment_refund_requests_receipt_id ON payment_refund_requests (receipt_id)",
    "CREATE INDEX ix_refund_request_site_status ON payment_refund_requests (site_id, status, created_at)",
    "CREATE UNIQUE INDEX uq_payment_refund_open ON payment_refund_requests (receipt_id) WHERE status IN ('pending','reviewing','approved')",
)


def upgrade():
    for sql in UPGRADE_SQL:
        op.execute(sql)


def downgrade():
    raise RuntimeError("Keep support threads and refund decisions; use a compatible application or a forward migration.")
