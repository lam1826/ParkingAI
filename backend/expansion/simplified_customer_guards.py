"""Additive cross-table capacity and authority backstops for simplified flows."""

_NOW = "datetime('now','+7 hours')"
_NORMAL = "replace(replace(replace(upper(v.license_plate),'-',''),'.',''),' ','')"
_BOOKING_SOURCE = """EXISTS (SELECT 1 FROM parking_slots s JOIN zones z ON z.id=s.zone_id
 JOIN parking_sites p ON p.id=z.site_id JOIN vehicle_types t ON t.id=s.vehicle_type_id
 JOIN users u ON u.id=NEW.user_id JOIN roles role ON role.id=u.role_id
 WHERE s.id=NEW.slot_id AND z.site_id=NEW.site_id AND t.id=NEW.vehicle_type_id
 AND s.is_active=1 AND z.is_active=1 AND p.is_active=1 AND t.is_active=1 AND u.is_active=1
 AND role.name='customer' AND s.is_occupied=0)
 AND NOT EXISTS (SELECT 1 FROM parking_sessions s WHERE s.parking_slot_id=NEW.slot_id AND s.status IN ('active','checking_out'))"""
_NEW_COLLISION = """EXISTS (SELECT 1 FROM declared_parking_reservations r WHERE
 (r.slot_id=NEW.slot_id OR r.normalized_plate=NEW.normalized_plate) AND r.status='confirmed'
 AND r.arrival_deadline>NEW.created_at AND r.end_at>NEW.created_at AND r.start_at<NEW.end_at AND r.end_at>NEW.start_at)"""
_OLD_COLLISION = """EXISTS (SELECT 1 FROM parking_reservations r WHERE r.slot_id=NEW.slot_id
 AND (r.status='confirmed' OR (r.status='arrived' AND EXISTS(SELECT 1 FROM parking_sessions s WHERE s.id=r.session_id AND s.status IN ('active','checking_out'))))
 AND r.arrival_deadline>NEW.created_at AND r.start_at<NEW.end_at AND r.end_at>NEW.start_at)
 OR EXISTS (SELECT 1 FROM guaranteed_allocations a WHERE a.slot_id=NEW.slot_id AND a.status='active' AND a.start_at<NEW.end_at AND a.end_at>NEW.start_at)
 OR EXISTS (SELECT 1 FROM parking_capacity_holds h WHERE h.slot_id=NEW.slot_id AND h.status='held' AND h.expires_at>NEW.created_at AND h.start_at<NEW.end_at AND h.end_at>NEW.start_at)"""
_FIELDS = ('id','site_id','slot_id','user_id','license_plate','normalized_plate','vehicle_type_id','start_at','end_at','arrival_deadline','request_id','created_at')
_CHANGED = ' OR '.join(f'NEW.{key} IS NOT OLD.{key}' for key in _FIELDS)
_ARRIVAL = f"""EXISTS (SELECT 1 FROM parking_sessions s JOIN vehicles v ON v.id=s.vehicle_id
 WHERE s.id=NEW.session_id AND s.parking_slot_id=NEW.slot_id AND s.status IN ('active','checking_out')
 AND v.vehicle_type_id=NEW.vehicle_type_id AND {_NORMAL}=NEW.normalized_plate
 AND s.check_in_time>=NEW.start_at AND s.check_in_time<NEW.arrival_deadline)"""
_SESSION_BLOCKED = f"""EXISTS (SELECT 1 FROM declared_parking_reservations r JOIN vehicles v ON v.id=NEW.vehicle_id
 WHERE r.status='confirmed' AND r.arrival_deadline>NEW.check_in_time AND r.end_at>NEW.check_in_time
 AND r.slot_id=NEW.parking_slot_id AND NOT (r.normalized_plate={_NORMAL}
 AND r.vehicle_type_id=v.vehicle_type_id AND r.start_at<=NEW.check_in_time))"""
_ACCESS_SOURCE = """EXISTS(SELECT 1 FROM session_ticket_credentials c JOIN parking_sessions s ON s.id=c.session_id
 JOIN vehicles v ON v.id=s.vehicle_id JOIN users u ON u.id=NEW.user_id JOIN roles role ON role.id=u.role_id
 WHERE s.id=NEW.session_id AND s.status='active' AND c.revoked_at IS NULL
 AND c.version=NEW.credential_version AND v.id=NEW.vehicle_id AND v.customer_id IS NEW.customer_snapshot_id
 AND u.is_active=1 AND role.name='customer')"""


def trigger(name, operation, table, when, message):
    return f"CREATE TRIGGER IF NOT EXISTS {name} BEFORE {operation} ON {table} WHEN {when} BEGIN SELECT RAISE(ABORT,'{message}'); END"


SIMPLIFIED_SQLITE_GUARDS = {
    'trg_declared_booking_source': trigger('trg_declared_booking_source', 'INSERT', 'declared_parking_reservations',
        f"NEW.status!='confirmed' OR NEW.session_id IS NOT NULL OR NEW.normalized_plate!=replace(replace(replace(upper(NEW.license_plate),'-',''),'.',''),' ','') OR NOT ({_BOOKING_SOURCE}) OR {_NEW_COLLISION} OR {_OLD_COLLISION}", 'declared booking capacity or source invalid'),
    'trg_declared_booking_frozen': trigger('trg_declared_booking_frozen', 'UPDATE', 'declared_parking_reservations',
        f"{_CHANGED} OR (OLD.status!='confirmed' AND NEW.status!=OLD.status) OR (NEW.session_id IS NOT OLD.session_id AND NOT(OLD.status='confirmed' AND NEW.status='arrived')) OR (NEW.status='arrived' AND NOT({_ARRIVAL}))", 'declared booking identity or state invalid'),
    'trg_declared_booking_delete': trigger('trg_declared_booking_delete', 'DELETE', 'declared_parking_reservations', '1=1', 'declared booking must be retained'),
    'trg_declared_booking_replace': trigger('trg_declared_booking_replace', 'INSERT', 'declared_parking_reservations',
        'EXISTS(SELECT 1 FROM declared_parking_reservations WHERE id=NEW.id OR (user_id=NEW.user_id AND request_id=NEW.request_id))', 'declared booking cannot be replaced'),
    'trg_declared_session_insert': trigger('trg_declared_session_insert', 'INSERT', 'parking_sessions', f"NEW.status='active' AND ({_SESSION_BLOCKED})", 'slot has declared booking'),
    'trg_declared_session_activate': trigger('trg_declared_session_activate', 'UPDATE OF status', 'parking_sessions', f"NEW.status='active' AND OLD.status!='active' AND ({_SESSION_BLOCKED})", 'slot has declared booking'),
    'trg_declared_session_cancel': trigger('trg_declared_session_cancel', 'UPDATE OF status', 'parking_sessions', "NEW.status='cancelled' AND EXISTS(SELECT 1 FROM declared_parking_reservations WHERE session_id=OLD.id)", 'session has declared booking arrival'),
    'trg_ticket_access_source': trigger('trg_ticket_access_source', 'INSERT', 'session_payment_access', f'NOT({_ACCESS_SOURCE})', 'ticket payment access source invalid'),
    'trg_ticket_access_update': trigger('trg_ticket_access_update', 'UPDATE', 'session_payment_access', f'NEW.id IS NOT OLD.id OR NEW.user_id IS NOT OLD.user_id OR NEW.session_id IS NOT OLD.session_id OR (NEW.revoked_at IS NULL AND NOT({_ACCESS_SOURCE}))', 'ticket payment access source invalid'),
    'trg_ticket_access_delete': trigger('trg_ticket_access_delete', 'DELETE', 'session_payment_access', '1=1', 'ticket payment access history retained'),
    'trg_type_identity_mode': trigger('trg_type_identity_mode', 'UPDATE OF requires_plate', 'vehicle_types', 'NEW.requires_plate IS NOT OLD.requires_plate AND (EXISTS(SELECT 1 FROM vehicles WHERE vehicle_type_id=OLD.id) OR EXISTS(SELECT 1 FROM declared_parking_reservations WHERE vehicle_type_id=OLD.id))', 'vehicle identity mode already used'),
}

for table in ('parking_reservations', 'guaranteed_allocations', 'parking_capacity_holds'):
    name = 'trg_declared_blocks_' + table
    SIMPLIFIED_SQLITE_GUARDS[name] = trigger(name, 'INSERT', table,
        f"EXISTS(SELECT 1 FROM declared_parking_reservations r WHERE (r.slot_id=NEW.slot_id OR r.normalized_plate=(SELECT {_NORMAL} FROM vehicles v WHERE v.id=NEW.vehicle_id)) AND r.status='confirmed' AND r.arrival_deadline>{_NOW} AND r.start_at<NEW.end_at AND r.end_at>NEW.start_at)", 'slot has declared booking')

for table, key, changed in (
    ('parking_slots', 'r.slot_id=OLD.id', 'NEW.zone_id IS NOT OLD.zone_id OR NEW.vehicle_type_id IS NOT OLD.vehicle_type_id OR NEW.is_active=0'),
    ('zones', 'r.slot_id IN(SELECT id FROM parking_slots WHERE zone_id=OLD.id)', 'NEW.is_active=0'),
    ('vehicle_types', 'r.vehicle_type_id=OLD.id', 'NEW.is_active=0'),
):
    name = 'trg_declared_catalog_' + table
    SIMPLIFIED_SQLITE_GUARDS[name] = trigger(name, 'UPDATE', table,
        f"({changed}) AND EXISTS(SELECT 1 FROM declared_parking_reservations r WHERE {key} AND r.status='confirmed' AND r.arrival_deadline>{_NOW})", 'catalog has declared booking')

for operation in ('INSERT', 'UPDATE'):
    name = 'trg_type_requires_plate_' + operation.lower()
    SIMPLIFIED_SQLITE_GUARDS[name] = trigger(name, operation, 'vehicle_types',
        "NEW.requires_plate IS NULL OR typeof(NEW.requires_plate)!='integer' OR NEW.requires_plate NOT IN(0,1) OR (NEW.code_prefix IS NOT NULL AND (length(NEW.code_prefix)<1 OR length(NEW.code_prefix)>8 OR NEW.code_prefix GLOB '*[^A-Z0-9]*' OR substr(NEW.code_prefix,1,1) GLOB '[^A-Z]'))", 'vehicle identity settings invalid')


def _pg(expression):
    value = expression.replace(' IS NOT ', ' IS DISTINCT FROM ').replace(' IS NEW.', ' IS NOT DISTINCT FROM NEW.')
    value = value.replace(_NOW, "(CURRENT_TIMESTAMP AT TIME ZONE 'Asia/Ho_Chi_Minh')")
    for alias in ('s','z','p','t','u'):
        value = value.replace(f'{alias}.is_active=1', f'{alias}.is_active').replace(f'{alias}.is_occupied=0', f'NOT {alias}.is_occupied')
    return value.replace('NEW.is_active=0', 'NOT NEW.is_active')


# New trigger names avoid replacing any frozen historical guard definition.
_PG_PARTS = []
for name, statement in SIMPLIFIED_SQLITE_GUARDS.items():
    operation, tail = statement.split(' BEFORE ', 1)[1].split(' ON ', 1)
    table, rest = tail.split(' WHEN ', 1)
    expression, message_tail = rest.split(" BEGIN SELECT RAISE(ABORT,'", 1)
    message = message_tail.split("'); END", 1)[0]
    if name.startswith('trg_type_requires_plate_'):
        expression = "NEW.requires_plate IS NULL OR (NEW.code_prefix IS NOT NULL AND NEW.code_prefix !~ '^[A-Z][A-Z0-9]{0,7}$')"
    lock = ''
    if table == 'declared_parking_reservations' and operation == 'INSERT':
        lock = f"PERFORM pg_advisory_xact_lock(hashtextextended(NEW.normalized_plate,0)); PERFORM id FROM vehicles v WHERE {_NORMAL}=NEW.normalized_plate ORDER BY id FOR NO KEY UPDATE; PERFORM id FROM parking_slots WHERE id=NEW.slot_id FOR UPDATE;"
    elif table in ('parking_reservations','guaranteed_allocations','parking_capacity_holds'):
        lock = 'PERFORM id FROM vehicles WHERE id=NEW.vehicle_id FOR NO KEY UPDATE; PERFORM id FROM parking_slots WHERE id=NEW.slot_id FOR UPDATE;'
    returns = 'OLD' if operation == 'DELETE' else 'NEW'
    _PG_PARTS.append(f"CREATE OR REPLACE FUNCTION {name}_fn() RETURNS trigger AS $$ BEGIN {lock} IF {_pg(expression)} THEN RAISE EXCEPTION '{message}' USING ERRCODE='23514'; END IF; RETURN {returns}; END; $$ LANGUAGE plpgsql; CREATE TRIGGER {name} BEFORE {operation} ON {table} FOR EACH ROW EXECUTE FUNCTION {name}_fn();")
SIMPLIFIED_POSTGRES_GUARD_SQL = '\n'.join(_PG_PARTS)

# A possession proof must not silently acquire a new owner's payment authority.
# Revocation also applies to reassignment outside the HTTP service boundary.
SIMPLIFIED_SQLITE_GUARDS['trg_ticket_owner_changed'] = """CREATE TRIGGER IF NOT EXISTS trg_ticket_owner_changed
 AFTER UPDATE OF customer_id ON vehicles WHEN NEW.customer_id IS NOT OLD.customer_id BEGIN
 UPDATE session_ticket_credentials SET revoked_at=datetime('now','+7 hours') WHERE session_id IN
 (SELECT id FROM parking_sessions WHERE vehicle_id=OLD.id AND status IN ('active','checking_out'));
 UPDATE session_payment_access SET revoked_at=datetime('now','+7 hours') WHERE session_id IN
 (SELECT id FROM parking_sessions WHERE vehicle_id=OLD.id AND status IN ('active','checking_out'));
 END"""
SIMPLIFIED_POSTGRES_GUARD_SQL += """
CREATE OR REPLACE FUNCTION trg_ticket_owner_changed_fn() RETURNS trigger AS $$ BEGIN
 IF NEW.customer_id IS DISTINCT FROM OLD.customer_id THEN
 UPDATE session_ticket_credentials SET revoked_at=CURRENT_TIMESTAMP AT TIME ZONE 'Asia/Ho_Chi_Minh'
 WHERE session_id IN(SELECT id FROM parking_sessions WHERE vehicle_id=OLD.id AND status IN ('active','checking_out'));
 UPDATE session_payment_access SET revoked_at=CURRENT_TIMESTAMP AT TIME ZONE 'Asia/Ho_Chi_Minh'
 WHERE session_id IN(SELECT id FROM parking_sessions WHERE vehicle_id=OLD.id AND status IN ('active','checking_out'));
 END IF; RETURN NEW; END; $$ LANGUAGE plpgsql;
CREATE TRIGGER trg_ticket_owner_changed AFTER UPDATE OF customer_id ON vehicles
FOR EACH ROW EXECUTE FUNCTION trg_ticket_owner_changed_fn();
"""
