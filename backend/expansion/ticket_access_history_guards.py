"""Retain exact PAP1 intervals without extending authority across expired gaps."""

_RENEWAL = """OLD.revoked_at IS NULL AND NEW.revoked_at IS NULL
 AND NEW.id=OLD.id AND NEW.user_id=OLD.user_id AND NEW.session_id=OLD.session_id
 AND NEW.credential_version=OLD.credential_version AND NEW.vehicle_id=OLD.vehicle_id
 AND NEW.customer_snapshot_id IS OLD.customer_snapshot_id
 AND NEW.created_at>=OLD.expires_at AND NEW.expires_at>NEW.created_at"""
_INSERT_OLD = """INSERT INTO session_payment_access_history
 (access_id,created_at,expires_at,credential_version,vehicle_id,customer_snapshot_id,revoked_at)
 VALUES(OLD.id,OLD.created_at,OLD.expires_at,OLD.credential_version,OLD.vehicle_id,OLD.customer_snapshot_id,NULL)"""
_SOURCE = """EXISTS(SELECT 1 FROM session_payment_access a WHERE a.id=NEW.access_id
 AND a.created_at=NEW.created_at AND a.expires_at=NEW.expires_at
 AND a.credential_version=NEW.credential_version AND a.vehicle_id=NEW.vehicle_id
 AND a.customer_snapshot_id IS NEW.customer_snapshot_id AND a.revoked_at IS NULL)
 AND NEW.revoked_at IS NULL"""
_FIELDS = ('access_id', 'created_at', 'expires_at', 'credential_version', 'vehicle_id', 'customer_snapshot_id')
_CHANGED = ' OR '.join(f'NEW.{field} IS NOT OLD.{field}' for field in _FIELDS)
_CHANGED += ' OR (OLD.revoked_at IS NOT NULL AND NEW.revoked_at IS NULL)'

TICKET_ACCESS_HISTORY_SQLITE_GUARDS = {
    'trg_ticket_access_archive': f"""CREATE TRIGGER IF NOT EXISTS trg_ticket_access_archive
 BEFORE UPDATE ON session_payment_access WHEN {_RENEWAL} BEGIN {_INSERT_OLD}; END""",
    'trg_ticket_access_history_revoke': """CREATE TRIGGER IF NOT EXISTS trg_ticket_access_history_revoke
 AFTER UPDATE OF revoked_at ON session_payment_access WHEN NEW.revoked_at IS NOT NULL BEGIN
 UPDATE session_payment_access_history SET revoked_at=NEW.revoked_at WHERE access_id=NEW.id AND revoked_at IS NULL; END""",
    'trg_ticket_access_history_source': f"""CREATE TRIGGER IF NOT EXISTS trg_ticket_access_history_source
 BEFORE INSERT ON session_payment_access_history WHEN NOT({_SOURCE}) BEGIN
 SELECT RAISE(ABORT,'ticket access history source invalid'); END""",
    'trg_ticket_access_history_frozen': f"""CREATE TRIGGER IF NOT EXISTS trg_ticket_access_history_frozen
 BEFORE UPDATE ON session_payment_access_history WHEN {_CHANGED} BEGIN
 SELECT RAISE(ABORT,'ticket access history immutable'); END""",
    'trg_ticket_access_history_delete': """CREATE TRIGGER IF NOT EXISTS trg_ticket_access_history_delete
 BEFORE DELETE ON session_payment_access_history BEGIN SELECT RAISE(ABORT,'ticket access history retained'); END""",
    'trg_ticket_access_history_replace': """CREATE TRIGGER IF NOT EXISTS trg_ticket_access_history_replace
 BEFORE INSERT ON session_payment_access_history WHEN EXISTS(SELECT 1 FROM session_payment_access_history
 WHERE access_id=NEW.access_id AND created_at=NEW.created_at) BEGIN SELECT RAISE(ABORT,'ticket access history retained'); END""",
}


def _pg(expression):
    return expression.replace(' IS NOT ', ' IS DISTINCT FROM ').replace(' IS OLD.', ' IS NOT DISTINCT FROM OLD.').replace(' IS NEW.', ' IS NOT DISTINCT FROM NEW.')


TICKET_ACCESS_HISTORY_POSTGRES_SQL = f"""
CREATE OR REPLACE FUNCTION ticket_access_history_guard() RETURNS trigger AS $$
BEGIN
 IF TG_TABLE_NAME='session_payment_access' THEN
  IF TG_WHEN='BEFORE' THEN
   IF {_pg(_RENEWAL)} THEN {_INSERT_OLD}; END IF;
  ELSIF NEW.revoked_at IS NOT NULL THEN
   UPDATE session_payment_access_history SET revoked_at=NEW.revoked_at WHERE access_id=NEW.id AND revoked_at IS NULL;
  END IF;
 ELSE
  IF TG_OP='DELETE' THEN RAISE EXCEPTION 'ticket access history retained' USING ERRCODE='23514'; END IF;
  IF TG_OP='INSERT' AND NOT({_pg(_SOURCE)}) THEN RAISE EXCEPTION 'ticket access history source invalid' USING ERRCODE='23514'; END IF;
  IF TG_OP='UPDATE' AND ({_pg(_CHANGED)}) THEN RAISE EXCEPTION 'ticket access history immutable' USING ERRCODE='23514'; END IF;
 END IF;
 RETURN NEW;
END; $$ LANGUAGE plpgsql;
CREATE TRIGGER trg_ticket_access_archive BEFORE UPDATE ON session_payment_access
 FOR EACH ROW EXECUTE FUNCTION ticket_access_history_guard();
CREATE TRIGGER trg_ticket_access_history_revoke AFTER UPDATE OF revoked_at ON session_payment_access
 FOR EACH ROW EXECUTE FUNCTION ticket_access_history_guard();
CREATE TRIGGER trg_ticket_access_history_guard BEFORE INSERT OR UPDATE OR DELETE ON session_payment_access_history
 FOR EACH ROW EXECUTE FUNCTION ticket_access_history_guard();
"""
