"""SQLite upgrade bridge for the 05/10/2026 review fixes.

The review fixes corrected the predicates of several SQLite backstop triggers
(lane CX-BOOKING: migration 20261005_11; lane CL-LEDGER: migration 20261005_12).
An existing schema10 SQLite database still stores the previous definitions.
``db_rollout`` must (1) accept exactly those frozen previous definitions during
preflight and (2) drop them so ``Base.metadata.create_all`` recreates the
current DDL from the owning guard modules. Arbitrary or unknown trigger bodies
are still rejected by preflight.

Frozen strings are copied verbatim from the migrations' PREVIOUS_SQLITE_GUARDS;
never edit them.
"""

PRE_REVIEW_20261005_TRIGGER_SQL = {}

# CX-BOOKING — backend/alembic/versions/20261005_11_review_admission_guards.py
PRE_REVIEW_20261005_TRIGGER_SQL.update({'trg_declared_booking_source': "CREATE TRIGGER IF NOT EXISTS trg_declared_booking_source BEFORE INSERT ON declared_parking_reservations WHEN NEW.status!='confirmed' OR NEW.session_id IS NOT NULL OR "
                                "NEW.normalized_plate!=replace(replace(replace(upper(NEW.license_plate),'-',''),'.',''),' ','') OR NOT (EXISTS (SELECT 1 FROM parking_slots s JOIN zones z ON "
                                'z.id=s.zone_id\n'
                                ' JOIN parking_sites p ON p.id=z.site_id JOIN vehicle_types t ON t.id=s.vehicle_type_id\n'
                                ' JOIN users u ON u.id=NEW.user_id JOIN roles role ON role.id=u.role_id\n'
                                ' WHERE s.id=NEW.slot_id AND z.site_id=NEW.site_id AND t.id=NEW.vehicle_type_id\n'
                                ' AND s.is_active=1 AND z.is_active=1 AND p.is_active=1 AND t.is_active=1 AND u.is_active=1\n'
                                " AND role.name='customer' AND s.is_occupied=0)\n"
                                " AND NOT EXISTS (SELECT 1 FROM parking_sessions s WHERE s.parking_slot_id=NEW.slot_id AND s.status IN ('active','checking_out'))) OR EXISTS (SELECT 1 FROM "
                                'declared_parking_reservations r WHERE\n'
                                " (r.slot_id=NEW.slot_id OR r.normalized_plate=NEW.normalized_plate) AND r.status='confirmed'\n"
                                ' AND r.arrival_deadline>NEW.created_at AND r.end_at>NEW.created_at AND r.start_at<NEW.end_at AND r.end_at>NEW.start_at) OR EXISTS (SELECT 1 FROM parking_reservations '
                                'r WHERE r.slot_id=NEW.slot_id\n'
                                " AND (r.status='confirmed' OR (r.status='arrived' AND EXISTS(SELECT 1 FROM parking_sessions s WHERE s.id=r.session_id AND s.status IN ('active','checking_out'))))\n"
                                ' AND r.arrival_deadline>NEW.created_at AND r.start_at<NEW.end_at AND r.end_at>NEW.start_at)\n'
                                " OR EXISTS (SELECT 1 FROM guaranteed_allocations a WHERE a.slot_id=NEW.slot_id AND a.status='active' AND a.start_at<NEW.end_at AND a.end_at>NEW.start_at)\n"
                                " OR EXISTS (SELECT 1 FROM parking_capacity_holds h WHERE h.slot_id=NEW.slot_id AND h.status='held' AND h.expires_at>NEW.created_at AND h.start_at<NEW.end_at AND "
                                "h.end_at>NEW.start_at) BEGIN SELECT RAISE(ABORT,'declared booking capacity or source invalid'); END",
 'trg_declared_session_activate': "CREATE TRIGGER IF NOT EXISTS trg_declared_session_activate BEFORE UPDATE OF status ON parking_sessions WHEN NEW.status='active' AND OLD.status!='active' AND "
                                  '(EXISTS (SELECT 1 FROM declared_parking_reservations r JOIN vehicles v ON v.id=NEW.vehicle_id\n'
                                  " WHERE r.status='confirmed' AND r.arrival_deadline>NEW.check_in_time AND r.end_at>NEW.check_in_time\n"
                                  " AND r.slot_id=NEW.parking_slot_id AND NOT (r.normalized_plate=replace(replace(replace(upper(v.license_plate),'-',''),'.',''),' ','')\n"
                                  " AND r.vehicle_type_id=v.vehicle_type_id AND r.start_at<=NEW.check_in_time))) BEGIN SELECT RAISE(ABORT,'slot has declared booking'); END",
 'trg_declared_session_insert': "CREATE TRIGGER IF NOT EXISTS trg_declared_session_insert BEFORE INSERT ON parking_sessions WHEN NEW.status='active' AND (EXISTS (SELECT 1 FROM "
                                'declared_parking_reservations r JOIN vehicles v ON v.id=NEW.vehicle_id\n'
                                " WHERE r.status='confirmed' AND r.arrival_deadline>NEW.check_in_time AND r.end_at>NEW.check_in_time\n"
                                " AND r.slot_id=NEW.parking_slot_id AND NOT (r.normalized_plate=replace(replace(replace(upper(v.license_plate),'-',''),'.',''),' ','')\n"
                                " AND r.vehicle_type_id=v.vehicle_type_id AND r.start_at<=NEW.check_in_time))) BEGIN SELECT RAISE(ABORT,'slot has declared booking'); END",
 'trg_session_capacity_hold': "CREATE TRIGGER IF NOT EXISTS trg_session_capacity_hold BEFORE INSERT ON parking_sessions FOR EACH ROW WHEN NEW.status='active' AND EXISTS (SELECT 1 FROM "
                              "parking_capacity_holds h WHERE h.slot_id=NEW.parking_slot_id AND h.status='held' AND h.expires_at>strftime('%Y-%m-%d %H:%M:%f','now','+7 hours') AND h.start_at < "
                              'COALESCE((SELECT MAX(bound.end_at) FROM (SELECT r.end_at FROM parking_reservations r JOIN vehicles v ON v.id=r.vehicle_id WHERE r.slot_id=NEW.parking_slot_id AND '
                              "r.vehicle_id=NEW.vehicle_id AND r.customer_id=v.customer_id AND r.status='confirmed' AND r.start_at<=NEW.check_in_time AND r.arrival_deadline>NEW.check_in_time UNION "
                              'ALL SELECT a.end_at FROM guaranteed_allocations a JOIN vehicles v ON v.id=a.vehicle_id WHERE a.slot_id=NEW.parking_slot_id AND a.vehicle_id=NEW.vehicle_id AND '
                              "a.customer_id=v.customer_id AND a.status='active' AND a.start_at<=NEW.check_in_time AND a.end_at>NEW.check_in_time) bound), '9999-12-31')) BEGIN SELECT RAISE(ABORT, "
                              "'slot has a live payment hold'); END"})


# CL-LEDGER — backend/alembic/versions/20261005_12_review_finance_site.py
PRE_REVIEW_20261005_TRIGGER_SQL.update({'trg_payment_site_guard': 'CREATE TRIGGER IF NOT EXISTS trg_payment_site_guard BEFORE INSERT ON payments WHEN\n'
                           "        (NEW.site_id IS NOT NULL AND NEW.kind = 'receipt' AND (\n"
                           "            (NEW.source_type = 'session_credit' AND NEW.site_id IS NOT (SELECT q.site_id FROM session_fee_credits c JOIN session_fee_quotes q ON q.id=c.quote_id WHERE "
                           'c.id=NEW.source_id)) OR\n'
                           "            (NEW.source_type = 'monthly_pass' AND NEW.site_id IS NOT (SELECT o.site_id FROM monthly_passes p JOIN portal_orders o ON p.renewal_key='portal:' || o.id WHERE "
                           'CAST(p.id AS TEXT)=NEW.source_id)) OR\n'
                           "            (NEW.source_type = 'parking_session' AND NEW.site_id IS NOT (SELECT z.site_id FROM parking_sessions p JOIN parking_slots s ON s.id=p.parking_slot_id JOIN "
                           'zones z ON z.id=s.zone_id WHERE p.id=NEW.source_id))))\n'
                           "        OR (NEW.kind = 'refund' AND NEW.site_id IS NOT (SELECT site_id FROM payments WHERE id=NEW.original_payment_id))\n"
                           '        OR (NEW.shift_id IS NOT NULL AND EXISTS (SELECT 1 FROM cash_shifts c WHERE c.id=NEW.shift_id AND c.site_id IS NOT NULL AND c.site_id IS NOT NEW.site_id))\n'
                           "        BEGIN SELECT RAISE(ABORT, 'payment site mismatch'); END"})

def _signature(sql):
    signature = "".join((sql or "").lower().split()).rstrip(";")
    return signature.replace("ifnotexists", "")


def is_pre_review_trigger(name, definition):
    old = PRE_REVIEW_20261005_TRIGGER_SQL.get(name)
    return old is not None and _signature(definition) == _signature(old)


def drop_pre_review_triggers(target_engine):
    """Drop only triggers whose stored SQL equals a frozen previous definition."""
    dropped = []
    with target_engine.begin() as connection:
        for name in PRE_REVIEW_20261005_TRIGGER_SQL:
            row = connection.exec_driver_sql(
                "SELECT sql FROM sqlite_master WHERE type='trigger' AND name=?", (name,)
            ).fetchone()
            if row and is_pre_review_trigger(name, row[0]):
                connection.exec_driver_sql(f'DROP TRIGGER "{name}"')
                dropped.append(name)
    return dropped
