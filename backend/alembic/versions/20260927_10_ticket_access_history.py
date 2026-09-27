"""Retain expired PAP1 intervals on renewal without changing existing grants."""
from alembic import op

revision = '20260927_10'
down_revision = '20260923_09'
branch_labels = None
depends_on = None

UPGRADE_SQL = ('CREATE TABLE session_payment_access_history (\n'
 '\taccess_id VARCHAR(36) NOT NULL, \n'
 '\tcreated_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, \n'
 '\texpires_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, \n'
 '\tcredential_version VARCHAR(32) NOT NULL, \n'
 '\tvehicle_id INTEGER NOT NULL, \n'
 '\tcustomer_snapshot_id INTEGER, \n'
 '\trevoked_at TIMESTAMP WITHOUT TIME ZONE, \n'
 '\tPRIMARY KEY (access_id, created_at), \n'
 '\tCONSTRAINT ck_session_payment_access_history_expiry CHECK (expires_at>created_at), \n'
 '\tFOREIGN KEY(access_id) REFERENCES session_payment_access (id), \n'
 '\tFOREIGN KEY(vehicle_id) REFERENCES vehicles (id)\n'
 ')',
 '\n'
 'CREATE OR REPLACE FUNCTION ticket_access_history_guard() RETURNS trigger AS $$\n'
 'BEGIN\n'
 " IF TG_TABLE_NAME='session_payment_access' THEN\n"
 "  IF TG_WHEN='BEFORE' THEN\n"
 '   IF OLD.revoked_at IS NULL AND NEW.revoked_at IS NULL\n'
 ' AND NEW.id=OLD.id AND NEW.user_id=OLD.user_id AND NEW.session_id=OLD.session_id\n'
 ' AND NEW.credential_version=OLD.credential_version AND NEW.vehicle_id=OLD.vehicle_id\n'
 ' AND NEW.customer_snapshot_id IS NOT DISTINCT FROM OLD.customer_snapshot_id\n'
 ' AND NEW.created_at>=OLD.expires_at AND NEW.expires_at>NEW.created_at THEN INSERT INTO '
 'session_payment_access_history\n'
 ' (access_id,created_at,expires_at,credential_version,vehicle_id,customer_snapshot_id,revoked_at)\n'
 ' '
 'VALUES(OLD.id,OLD.created_at,OLD.expires_at,OLD.credential_version,OLD.vehicle_id,OLD.customer_snapshot_id,NULL); '
 'END IF;\n'
 '  ELSIF NEW.revoked_at IS NOT NULL THEN\n'
 '   UPDATE session_payment_access_history SET revoked_at=NEW.revoked_at WHERE access_id=NEW.id AND '
 'revoked_at IS NULL;\n'
 '  END IF;\n'
 ' ELSE\n'
 "  IF TG_OP='DELETE' THEN RAISE EXCEPTION 'ticket access history retained' USING ERRCODE='23514'; END IF;\n"
 "  IF TG_OP='INSERT' AND NOT(EXISTS(SELECT 1 FROM session_payment_access a WHERE a.id=NEW.access_id\n"
 ' AND a.created_at=NEW.created_at AND a.expires_at=NEW.expires_at\n'
 ' AND a.credential_version=NEW.credential_version AND a.vehicle_id=NEW.vehicle_id\n'
 ' AND a.customer_snapshot_id IS NOT DISTINCT FROM NEW.customer_snapshot_id AND a.revoked_at IS NULL)\n'
 " AND NEW.revoked_at IS NULL) THEN RAISE EXCEPTION 'ticket access history source invalid' USING "
 "ERRCODE='23514'; END IF;\n"
 "  IF TG_OP='UPDATE' AND (NEW.access_id IS DISTINCT FROM OLD.access_id OR NEW.created_at IS DISTINCT FROM "
 'OLD.created_at OR NEW.expires_at IS DISTINCT FROM OLD.expires_at OR NEW.credential_version IS DISTINCT '
 'FROM OLD.credential_version OR NEW.vehicle_id IS DISTINCT FROM OLD.vehicle_id OR NEW.customer_snapshot_id '
 'IS DISTINCT FROM OLD.customer_snapshot_id OR (OLD.revoked_at IS DISTINCT FROM NULL AND NEW.revoked_at IS '
 "NULL)) THEN RAISE EXCEPTION 'ticket access history immutable' USING ERRCODE='23514'; END IF;\n"
 ' END IF;\n'
 ' RETURN NEW;\n'
 'END; $$ LANGUAGE plpgsql;\n'
 'CREATE TRIGGER trg_ticket_access_archive BEFORE UPDATE ON session_payment_access\n'
 ' FOR EACH ROW EXECUTE FUNCTION ticket_access_history_guard();\n'
 'CREATE TRIGGER trg_ticket_access_history_revoke AFTER UPDATE OF revoked_at ON session_payment_access\n'
 ' FOR EACH ROW EXECUTE FUNCTION ticket_access_history_guard();\n'
 'CREATE TRIGGER trg_ticket_access_history_guard BEFORE INSERT OR UPDATE OR DELETE ON '
 'session_payment_access_history\n'
 ' FOR EACH ROW EXECUTE FUNCTION ticket_access_history_guard();\n')


def upgrade():
    for sql in UPGRADE_SQL:
        op.execute(sql)


def downgrade():
    raise RuntimeError("Retain payment authorization history; use a compatible application or forward migration.")
