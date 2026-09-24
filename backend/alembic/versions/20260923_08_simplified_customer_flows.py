"""Frozen additive approved-demo schema; preserve historical rows and authority."""
from alembic import op

revision = '20260923_08'
down_revision = '20260916_07'
branch_labels = None
depends_on = None

UPGRADE_SQL = ('ALTER TABLE vehicle_types ADD COLUMN requires_plate BOOLEAN NOT NULL DEFAULT true',
 'ALTER TABLE vehicle_types ADD COLUMN code_prefix VARCHAR(8)',
 'CREATE UNIQUE INDEX uq_vehicle_types_code_prefix ON vehicle_types (code_prefix)',
 'CREATE TABLE session_ticket_credentials (\n'
 '\tsession_id VARCHAR(36) NOT NULL, \n'
 '\tversion VARCHAR(32) NOT NULL, \n'
 '\tcreated_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, \n'
 '\trevoked_at TIMESTAMP WITHOUT TIME ZONE, \n'
 '\tPRIMARY KEY (session_id), \n'
 '\tFOREIGN KEY(session_id) REFERENCES parking_sessions (id)\n'
 ')',
 'CREATE TABLE session_payment_access (\n'
 '\tid VARCHAR(36) NOT NULL, \n'
 '\tuser_id INTEGER NOT NULL, \n'
 '\tsession_id VARCHAR(36) NOT NULL, \n'
 '\tcredential_version VARCHAR(32) NOT NULL, \n'
 '\tvehicle_id INTEGER NOT NULL, \n'
 '\tcustomer_snapshot_id INTEGER, \n'
 '\tcreated_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, \n'
 '\texpires_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, \n'
 '\trevoked_at TIMESTAMP WITHOUT TIME ZONE, \n'
 '\tPRIMARY KEY (id), \n'
 '\tCONSTRAINT uq_session_payment_access_user_session UNIQUE (user_id, session_id), \n'
 '\tCONSTRAINT ck_session_payment_access_expiry CHECK (expires_at>created_at), \n'
 '\tFOREIGN KEY(user_id) REFERENCES users (id), \n'
 '\tFOREIGN KEY(session_id) REFERENCES parking_sessions (id), \n'
 '\tFOREIGN KEY(vehicle_id) REFERENCES vehicles (id)\n'
 ')',
 'CREATE INDEX ix_session_payment_access_session_id ON session_payment_access (session_id)',
 'CREATE INDEX ix_session_payment_access_user_id ON session_payment_access (user_id)',
 'CREATE TABLE declared_parking_reservations (\n'
 '\tid VARCHAR(36) NOT NULL, \n'
 '\tsite_id INTEGER NOT NULL, \n'
 '\tslot_id INTEGER NOT NULL, \n'
 '\tuser_id INTEGER NOT NULL, \n'
 '\tlicense_plate VARCHAR(20) NOT NULL, \n'
 '\tnormalized_plate VARCHAR(20) NOT NULL, \n'
 '\tvehicle_type_id INTEGER NOT NULL, \n'
 '\tstart_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, \n'
 '\tend_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, \n'
 '\tarrival_deadline TIMESTAMP WITHOUT TIME ZONE NOT NULL, \n'
 '\tstatus VARCHAR(12) NOT NULL, \n'
 '\tsession_id VARCHAR(36), \n'
 '\trequest_id VARCHAR(64) NOT NULL, \n'
 '\tcreated_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, \n'
 '\tPRIMARY KEY (id), \n'
 '\tCONSTRAINT uq_declared_booking_request UNIQUE (user_id, request_id), \n'
 '\tCONSTRAINT ck_declared_booking_interval CHECK (end_at>start_at AND arrival_deadline>start_at AND '
 'arrival_deadline<=end_at), \n'
 "\tCONSTRAINT ck_declared_booking_status CHECK (status IN ('confirmed','arrived','cancelled','expired')), \n"
 '\tFOREIGN KEY(site_id) REFERENCES parking_sites (id), \n'
 '\tFOREIGN KEY(slot_id) REFERENCES parking_slots (id), \n'
 '\tFOREIGN KEY(user_id) REFERENCES users (id), \n'
 '\tFOREIGN KEY(vehicle_type_id) REFERENCES vehicle_types (id), \n'
 '\tUNIQUE (session_id), \n'
 '\tFOREIGN KEY(session_id) REFERENCES parking_sessions (id)\n'
 ')',
 'CREATE INDEX ix_declared_booking_plate_interval ON declared_parking_reservations (normalized_plate, '
 'start_at, end_at)',
 'CREATE INDEX ix_declared_booking_slot_interval ON declared_parking_reservations (slot_id, start_at, '
 'end_at)',
 'CREATE INDEX ix_declared_parking_reservations_site_id ON declared_parking_reservations (site_id)',
 'CREATE INDEX ix_declared_parking_reservations_user_id ON declared_parking_reservations (user_id)',
 'CREATE OR REPLACE FUNCTION trg_declared_booking_source_fn() RETURNS trigger AS $$ BEGIN PERFORM '
 'pg_advisory_xact_lock(hashtextextended(NEW.normalized_plate,0)); PERFORM id FROM vehicles v WHERE '
 "replace(replace(replace(upper(v.license_plate),'-',''),'.',''),' ','')=NEW.normalized_plate ORDER BY id "
 'FOR NO KEY UPDATE; PERFORM id FROM parking_slots WHERE id=NEW.slot_id FOR UPDATE; IF '
 "NEW.status!='confirmed' OR NEW.session_id IS DISTINCT FROM NULL OR "
 "NEW.normalized_plate!=replace(replace(replace(upper(NEW.license_plate),'-',''),'.',''),' ','') OR NOT "
 '(EXISTS (SELECT 1 FROM parking_slots s JOIN zones z ON z.id=s.zone_id\n'
 ' JOIN parking_sites p ON p.id=z.site_id JOIN vehicle_types t ON t.id=s.vehicle_type_id\n'
 ' JOIN users u ON u.id=NEW.user_id JOIN roles role ON role.id=u.role_id\n'
 ' WHERE s.id=NEW.slot_id AND z.site_id=NEW.site_id AND t.id=NEW.vehicle_type_id\n'
 ' AND s.is_active AND z.is_active AND p.is_active AND t.is_active AND u.is_active\n'
 " AND role.name='customer' AND NOT s.is_occupied)\n"
 ' AND NOT EXISTS (SELECT 1 FROM parking_sessions s WHERE s.parking_slot_id=NEW.slot_id AND s.status IN '
 "('active','checking_out'))) OR EXISTS (SELECT 1 FROM declared_parking_reservations r WHERE\n"
 " (r.slot_id=NEW.slot_id OR r.normalized_plate=NEW.normalized_plate) AND r.status='confirmed'\n"
 ' AND r.arrival_deadline>NEW.created_at AND r.end_at>NEW.created_at AND r.start_at<NEW.end_at AND '
 'r.end_at>NEW.start_at) OR EXISTS (SELECT 1 FROM parking_reservations r WHERE r.slot_id=NEW.slot_id\n'
 " AND (r.status='confirmed' OR (r.status='arrived' AND EXISTS(SELECT 1 FROM parking_sessions s WHERE "
 "s.id=r.session_id AND s.status IN ('active','checking_out'))))\n"
 ' AND r.arrival_deadline>NEW.created_at AND r.start_at<NEW.end_at AND r.end_at>NEW.start_at)\n'
 " OR EXISTS (SELECT 1 FROM guaranteed_allocations a WHERE a.slot_id=NEW.slot_id AND a.status='active' AND "
 'a.start_at<NEW.end_at AND a.end_at>NEW.start_at)\n'
 " OR EXISTS (SELECT 1 FROM parking_capacity_holds h WHERE h.slot_id=NEW.slot_id AND h.status='held' AND "
 'h.expires_at>NEW.created_at AND h.start_at<NEW.end_at AND h.end_at>NEW.start_at) THEN RAISE EXCEPTION '
 "'declared booking capacity or source invalid' USING ERRCODE='23514'; END IF; RETURN NEW; END; $$ LANGUAGE "
 'plpgsql; CREATE TRIGGER trg_declared_booking_source BEFORE INSERT ON declared_parking_reservations FOR '
 'EACH ROW EXECUTE FUNCTION trg_declared_booking_source_fn();\n'
 'CREATE OR REPLACE FUNCTION trg_declared_booking_frozen_fn() RETURNS trigger AS $$ BEGIN  IF NEW.id IS '
 'DISTINCT FROM OLD.id OR NEW.site_id IS DISTINCT FROM OLD.site_id OR NEW.slot_id IS DISTINCT FROM '
 'OLD.slot_id OR NEW.user_id IS DISTINCT FROM OLD.user_id OR NEW.license_plate IS DISTINCT FROM '
 'OLD.license_plate OR NEW.normalized_plate IS DISTINCT FROM OLD.normalized_plate OR NEW.vehicle_type_id IS '
 'DISTINCT FROM OLD.vehicle_type_id OR NEW.start_at IS DISTINCT FROM OLD.start_at OR NEW.end_at IS DISTINCT '
 'FROM OLD.end_at OR NEW.arrival_deadline IS DISTINCT FROM OLD.arrival_deadline OR NEW.request_id IS '
 "DISTINCT FROM OLD.request_id OR NEW.created_at IS DISTINCT FROM OLD.created_at OR (OLD.status!='confirmed' "
 'AND NEW.status!=OLD.status) OR (NEW.session_id IS DISTINCT FROM OLD.session_id AND '
 "NOT(OLD.status='confirmed' AND NEW.status='arrived')) OR (NEW.status='arrived' AND NOT(EXISTS (SELECT 1 "
 'FROM parking_sessions s JOIN vehicles v ON v.id=s.vehicle_id\n'
 " WHERE s.id=NEW.session_id AND s.parking_slot_id=NEW.slot_id AND s.status IN ('active','checking_out')\n"
 ' AND v.vehicle_type_id=NEW.vehicle_type_id AND '
 "replace(replace(replace(upper(v.license_plate),'-',''),'.',''),' ','')=NEW.normalized_plate\n"
 ' AND s.check_in_time>=NEW.start_at AND s.check_in_time<NEW.arrival_deadline))) THEN RAISE EXCEPTION '
 "'declared booking identity or state invalid' USING ERRCODE='23514'; END IF; RETURN NEW; END; $$ LANGUAGE "
 'plpgsql; CREATE TRIGGER trg_declared_booking_frozen BEFORE UPDATE ON declared_parking_reservations FOR '
 'EACH ROW EXECUTE FUNCTION trg_declared_booking_frozen_fn();\n'
 'CREATE OR REPLACE FUNCTION trg_declared_booking_delete_fn() RETURNS trigger AS $$ BEGIN  IF 1=1 THEN RAISE '
 "EXCEPTION 'declared booking must be retained' USING ERRCODE='23514'; END IF; RETURN OLD; END; $$ LANGUAGE "
 'plpgsql; CREATE TRIGGER trg_declared_booking_delete BEFORE DELETE ON declared_parking_reservations FOR '
 'EACH ROW EXECUTE FUNCTION trg_declared_booking_delete_fn();\n'
 'CREATE OR REPLACE FUNCTION trg_declared_booking_replace_fn() RETURNS trigger AS $$ BEGIN PERFORM '
 'pg_advisory_xact_lock(hashtextextended(NEW.normalized_plate,0)); PERFORM id FROM vehicles v WHERE '
 "replace(replace(replace(upper(v.license_plate),'-',''),'.',''),' ','')=NEW.normalized_plate ORDER BY id "
 'FOR NO KEY UPDATE; PERFORM id FROM parking_slots WHERE id=NEW.slot_id FOR UPDATE; IF EXISTS(SELECT 1 FROM '
 'declared_parking_reservations WHERE id=NEW.id OR (user_id=NEW.user_id AND request_id=NEW.request_id)) THEN '
 "RAISE EXCEPTION 'declared booking cannot be replaced' USING ERRCODE='23514'; END IF; RETURN NEW; END; $$ "
 'LANGUAGE plpgsql; CREATE TRIGGER trg_declared_booking_replace BEFORE INSERT ON '
 'declared_parking_reservations FOR EACH ROW EXECUTE FUNCTION trg_declared_booking_replace_fn();\n'
 'CREATE OR REPLACE FUNCTION trg_declared_session_insert_fn() RETURNS trigger AS $$ BEGIN  IF '
 "NEW.status='active' AND (EXISTS (SELECT 1 FROM declared_parking_reservations r JOIN vehicles v ON "
 'v.id=NEW.vehicle_id\n'
 " WHERE r.status='confirmed' AND r.arrival_deadline>NEW.check_in_time AND r.end_at>NEW.check_in_time\n"
 ' AND r.slot_id=NEW.parking_slot_id AND NOT '
 "(r.normalized_plate=replace(replace(replace(upper(v.license_plate),'-',''),'.',''),' ','')\n"
 " AND r.vehicle_type_id=v.vehicle_type_id AND r.start_at<=NEW.check_in_time))) THEN RAISE EXCEPTION 'slot "
 "has declared booking' USING ERRCODE='23514'; END IF; RETURN NEW; END; $$ LANGUAGE plpgsql; CREATE TRIGGER "
 'trg_declared_session_insert BEFORE INSERT ON parking_sessions FOR EACH ROW EXECUTE FUNCTION '
 'trg_declared_session_insert_fn();\n'
 'CREATE OR REPLACE FUNCTION trg_declared_session_activate_fn() RETURNS trigger AS $$ BEGIN  IF '
 "NEW.status='active' AND OLD.status!='active' AND (EXISTS (SELECT 1 FROM declared_parking_reservations r "
 'JOIN vehicles v ON v.id=NEW.vehicle_id\n'
 " WHERE r.status='confirmed' AND r.arrival_deadline>NEW.check_in_time AND r.end_at>NEW.check_in_time\n"
 ' AND r.slot_id=NEW.parking_slot_id AND NOT '
 "(r.normalized_plate=replace(replace(replace(upper(v.license_plate),'-',''),'.',''),' ','')\n"
 " AND r.vehicle_type_id=v.vehicle_type_id AND r.start_at<=NEW.check_in_time))) THEN RAISE EXCEPTION 'slot "
 "has declared booking' USING ERRCODE='23514'; END IF; RETURN NEW; END; $$ LANGUAGE plpgsql; CREATE TRIGGER "
 'trg_declared_session_activate BEFORE UPDATE OF status ON parking_sessions FOR EACH ROW EXECUTE FUNCTION '
 'trg_declared_session_activate_fn();\n'
 'CREATE OR REPLACE FUNCTION trg_declared_session_cancel_fn() RETURNS trigger AS $$ BEGIN  IF '
 "NEW.status='cancelled' AND EXISTS(SELECT 1 FROM declared_parking_reservations WHERE session_id=OLD.id) "
 "THEN RAISE EXCEPTION 'session has declared booking arrival' USING ERRCODE='23514'; END IF; RETURN NEW; "
 'END; $$ LANGUAGE plpgsql; CREATE TRIGGER trg_declared_session_cancel BEFORE UPDATE OF status ON '
 'parking_sessions FOR EACH ROW EXECUTE FUNCTION trg_declared_session_cancel_fn();\n'
 'CREATE OR REPLACE FUNCTION trg_ticket_access_source_fn() RETURNS trigger AS $$ BEGIN  IF NOT(EXISTS(SELECT '
 '1 FROM session_ticket_credentials c JOIN parking_sessions s ON s.id=c.session_id\n'
 ' JOIN vehicles v ON v.id=s.vehicle_id JOIN users u ON u.id=NEW.user_id JOIN roles role ON '
 'role.id=u.role_id\n'
 " WHERE s.id=NEW.session_id AND s.status='active' AND c.revoked_at IS NULL\n"
 ' AND c.version=NEW.credential_version AND v.id=NEW.vehicle_id AND v.customer_id IS NOT DISTINCT FROM '
 'NEW.customer_snapshot_id\n'
 " AND u.is_active AND role.name='customer')) THEN RAISE EXCEPTION 'ticket payment access source invalid' "
 "USING ERRCODE='23514'; END IF; RETURN NEW; END; $$ LANGUAGE plpgsql; CREATE TRIGGER "
 'trg_ticket_access_source BEFORE INSERT ON session_payment_access FOR EACH ROW EXECUTE FUNCTION '
 'trg_ticket_access_source_fn();\n'
 'CREATE OR REPLACE FUNCTION trg_ticket_access_update_fn() RETURNS trigger AS $$ BEGIN  IF NEW.id IS '
 'DISTINCT FROM OLD.id OR NEW.user_id IS DISTINCT FROM OLD.user_id OR NEW.session_id IS DISTINCT FROM '
 'OLD.session_id OR (NEW.revoked_at IS NULL AND NOT(EXISTS(SELECT 1 FROM session_ticket_credentials c JOIN '
 'parking_sessions s ON s.id=c.session_id\n'
 ' JOIN vehicles v ON v.id=s.vehicle_id JOIN users u ON u.id=NEW.user_id JOIN roles role ON '
 'role.id=u.role_id\n'
 " WHERE s.id=NEW.session_id AND s.status='active' AND c.revoked_at IS NULL\n"
 ' AND c.version=NEW.credential_version AND v.id=NEW.vehicle_id AND v.customer_id IS NOT DISTINCT FROM '
 'NEW.customer_snapshot_id\n'
 " AND u.is_active AND role.name='customer'))) THEN RAISE EXCEPTION 'ticket payment access source invalid' "
 "USING ERRCODE='23514'; END IF; RETURN NEW; END; $$ LANGUAGE plpgsql; CREATE TRIGGER "
 'trg_ticket_access_update BEFORE UPDATE ON session_payment_access FOR EACH ROW EXECUTE FUNCTION '
 'trg_ticket_access_update_fn();\n'
 'CREATE OR REPLACE FUNCTION trg_ticket_access_delete_fn() RETURNS trigger AS $$ BEGIN  IF 1=1 THEN RAISE '
 "EXCEPTION 'ticket payment access history retained' USING ERRCODE='23514'; END IF; RETURN OLD; END; $$ "
 'LANGUAGE plpgsql; CREATE TRIGGER trg_ticket_access_delete BEFORE DELETE ON session_payment_access FOR EACH '
 'ROW EXECUTE FUNCTION trg_ticket_access_delete_fn();\n'
 'CREATE OR REPLACE FUNCTION trg_type_identity_mode_fn() RETURNS trigger AS $$ BEGIN  IF NEW.requires_plate '
 'IS DISTINCT FROM OLD.requires_plate AND (EXISTS(SELECT 1 FROM vehicles WHERE vehicle_type_id=OLD.id) OR '
 'EXISTS(SELECT 1 FROM declared_parking_reservations WHERE vehicle_type_id=OLD.id)) THEN RAISE EXCEPTION '
 "'vehicle identity mode already used' USING ERRCODE='23514'; END IF; RETURN NEW; END; $$ LANGUAGE plpgsql; "
 'CREATE TRIGGER trg_type_identity_mode BEFORE UPDATE OF requires_plate ON vehicle_types FOR EACH ROW '
 'EXECUTE FUNCTION trg_type_identity_mode_fn();\n'
 'CREATE OR REPLACE FUNCTION trg_declared_blocks_parking_reservations_fn() RETURNS trigger AS $$ BEGIN '
 'PERFORM id FROM vehicles WHERE id=NEW.vehicle_id FOR NO KEY UPDATE; PERFORM id FROM parking_slots WHERE '
 'id=NEW.slot_id FOR UPDATE; IF EXISTS(SELECT 1 FROM declared_parking_reservations r WHERE '
 '(r.slot_id=NEW.slot_id OR r.normalized_plate=(SELECT '
 "replace(replace(replace(upper(v.license_plate),'-',''),'.',''),' ','') FROM vehicles v WHERE "
 "v.id=NEW.vehicle_id)) AND r.status='confirmed' AND r.arrival_deadline>(CURRENT_TIMESTAMP AT TIME ZONE "
 "'Asia/Ho_Chi_Minh') AND r.start_at<NEW.end_at AND r.end_at>NEW.start_at) THEN RAISE EXCEPTION 'slot has "
 "declared booking' USING ERRCODE='23514'; END IF; RETURN NEW; END; $$ LANGUAGE plpgsql; CREATE TRIGGER "
 'trg_declared_blocks_parking_reservations BEFORE INSERT ON parking_reservations FOR EACH ROW EXECUTE '
 'FUNCTION trg_declared_blocks_parking_reservations_fn();\n'
 'CREATE OR REPLACE FUNCTION trg_declared_blocks_guaranteed_allocations_fn() RETURNS trigger AS $$ BEGIN '
 'PERFORM id FROM vehicles WHERE id=NEW.vehicle_id FOR NO KEY UPDATE; PERFORM id FROM parking_slots WHERE '
 'id=NEW.slot_id FOR UPDATE; IF EXISTS(SELECT 1 FROM declared_parking_reservations r WHERE '
 '(r.slot_id=NEW.slot_id OR r.normalized_plate=(SELECT '
 "replace(replace(replace(upper(v.license_plate),'-',''),'.',''),' ','') FROM vehicles v WHERE "
 "v.id=NEW.vehicle_id)) AND r.status='confirmed' AND r.arrival_deadline>(CURRENT_TIMESTAMP AT TIME ZONE "
 "'Asia/Ho_Chi_Minh') AND r.start_at<NEW.end_at AND r.end_at>NEW.start_at) THEN RAISE EXCEPTION 'slot has "
 "declared booking' USING ERRCODE='23514'; END IF; RETURN NEW; END; $$ LANGUAGE plpgsql; CREATE TRIGGER "
 'trg_declared_blocks_guaranteed_allocations BEFORE INSERT ON guaranteed_allocations FOR EACH ROW EXECUTE '
 'FUNCTION trg_declared_blocks_guaranteed_allocations_fn();\n'
 'CREATE OR REPLACE FUNCTION trg_declared_blocks_parking_capacity_holds_fn() RETURNS trigger AS $$ BEGIN '
 'PERFORM id FROM vehicles WHERE id=NEW.vehicle_id FOR NO KEY UPDATE; PERFORM id FROM parking_slots WHERE '
 'id=NEW.slot_id FOR UPDATE; IF EXISTS(SELECT 1 FROM declared_parking_reservations r WHERE '
 '(r.slot_id=NEW.slot_id OR r.normalized_plate=(SELECT '
 "replace(replace(replace(upper(v.license_plate),'-',''),'.',''),' ','') FROM vehicles v WHERE "
 "v.id=NEW.vehicle_id)) AND r.status='confirmed' AND r.arrival_deadline>(CURRENT_TIMESTAMP AT TIME ZONE "
 "'Asia/Ho_Chi_Minh') AND r.start_at<NEW.end_at AND r.end_at>NEW.start_at) THEN RAISE EXCEPTION 'slot has "
 "declared booking' USING ERRCODE='23514'; END IF; RETURN NEW; END; $$ LANGUAGE plpgsql; CREATE TRIGGER "
 'trg_declared_blocks_parking_capacity_holds BEFORE INSERT ON parking_capacity_holds FOR EACH ROW EXECUTE '
 'FUNCTION trg_declared_blocks_parking_capacity_holds_fn();\n'
 'CREATE OR REPLACE FUNCTION trg_declared_catalog_parking_slots_fn() RETURNS trigger AS $$ BEGIN  IF '
 '(NEW.zone_id IS DISTINCT FROM OLD.zone_id OR NEW.vehicle_type_id IS DISTINCT FROM OLD.vehicle_type_id OR '
 'NOT NEW.is_active) AND EXISTS(SELECT 1 FROM declared_parking_reservations r WHERE r.slot_id=OLD.id AND '
 "r.status='confirmed' AND r.arrival_deadline>(CURRENT_TIMESTAMP AT TIME ZONE 'Asia/Ho_Chi_Minh')) THEN "
 "RAISE EXCEPTION 'catalog has declared booking' USING ERRCODE='23514'; END IF; RETURN NEW; END; $$ LANGUAGE "
 'plpgsql; CREATE TRIGGER trg_declared_catalog_parking_slots BEFORE UPDATE ON parking_slots FOR EACH ROW '
 'EXECUTE FUNCTION trg_declared_catalog_parking_slots_fn();\n'
 'CREATE OR REPLACE FUNCTION trg_declared_catalog_zones_fn() RETURNS trigger AS $$ BEGIN  IF (NOT '
 'NEW.is_active) AND EXISTS(SELECT 1 FROM declared_parking_reservations r WHERE r.slot_id IN(SELECT id FROM '
 "parking_slots WHERE zone_id=OLD.id) AND r.status='confirmed' AND r.arrival_deadline>(CURRENT_TIMESTAMP AT "
 "TIME ZONE 'Asia/Ho_Chi_Minh')) THEN RAISE EXCEPTION 'catalog has declared booking' USING ERRCODE='23514'; "
 'END IF; RETURN NEW; END; $$ LANGUAGE plpgsql; CREATE TRIGGER trg_declared_catalog_zones BEFORE UPDATE ON '
 'zones FOR EACH ROW EXECUTE FUNCTION trg_declared_catalog_zones_fn();\n'
 'CREATE OR REPLACE FUNCTION trg_declared_catalog_vehicle_types_fn() RETURNS trigger AS $$ BEGIN  IF (NOT '
 'NEW.is_active) AND EXISTS(SELECT 1 FROM declared_parking_reservations r WHERE r.vehicle_type_id=OLD.id AND '
 "r.status='confirmed' AND r.arrival_deadline>(CURRENT_TIMESTAMP AT TIME ZONE 'Asia/Ho_Chi_Minh')) THEN "
 "RAISE EXCEPTION 'catalog has declared booking' USING ERRCODE='23514'; END IF; RETURN NEW; END; $$ LANGUAGE "
 'plpgsql; CREATE TRIGGER trg_declared_catalog_vehicle_types BEFORE UPDATE ON vehicle_types FOR EACH ROW '
 'EXECUTE FUNCTION trg_declared_catalog_vehicle_types_fn();\n'
 'CREATE OR REPLACE FUNCTION trg_type_requires_plate_insert_fn() RETURNS trigger AS $$ BEGIN  IF '
 'NEW.requires_plate IS NULL OR (NEW.code_prefix IS DISTINCT FROM NULL AND NEW.code_prefix !~ '
 "'^[A-Z][A-Z0-9]{0,7}$') THEN RAISE EXCEPTION 'vehicle identity settings invalid' USING ERRCODE='23514'; "
 'END IF; RETURN NEW; END; $$ LANGUAGE plpgsql; CREATE TRIGGER trg_type_requires_plate_insert BEFORE INSERT '
 'ON vehicle_types FOR EACH ROW EXECUTE FUNCTION trg_type_requires_plate_insert_fn();\n'
 'CREATE OR REPLACE FUNCTION trg_type_requires_plate_update_fn() RETURNS trigger AS $$ BEGIN  IF '
 'NEW.requires_plate IS NULL OR (NEW.code_prefix IS DISTINCT FROM NULL AND NEW.code_prefix !~ '
 "'^[A-Z][A-Z0-9]{0,7}$') THEN RAISE EXCEPTION 'vehicle identity settings invalid' USING ERRCODE='23514'; "
 'END IF; RETURN NEW; END; $$ LANGUAGE plpgsql; CREATE TRIGGER trg_type_requires_plate_update BEFORE UPDATE '
 'ON vehicle_types FOR EACH ROW EXECUTE FUNCTION trg_type_requires_plate_update_fn();\n'
 'CREATE OR REPLACE FUNCTION trg_ticket_owner_changed_fn() RETURNS trigger AS $$ BEGIN\n'
 ' IF NEW.customer_id IS DISTINCT FROM OLD.customer_id THEN\n'
 " UPDATE session_ticket_credentials SET revoked_at=CURRENT_TIMESTAMP AT TIME ZONE 'Asia/Ho_Chi_Minh'\n"
 ' WHERE session_id IN(SELECT id FROM parking_sessions WHERE vehicle_id=OLD.id AND status IN '
 "('active','checking_out'));\n"
 " UPDATE session_payment_access SET revoked_at=CURRENT_TIMESTAMP AT TIME ZONE 'Asia/Ho_Chi_Minh'\n"
 ' WHERE session_id IN(SELECT id FROM parking_sessions WHERE vehicle_id=OLD.id AND status IN '
 "('active','checking_out'));\n"
 ' END IF; RETURN NEW; END; $$ LANGUAGE plpgsql;\n'
 'CREATE TRIGGER trg_ticket_owner_changed AFTER UPDATE OF customer_id ON vehicles\n'
 'FOR EACH ROW EXECUTE FUNCTION trg_ticket_owner_changed_fn();\n')

def upgrade():
    for sql in UPGRADE_SQL:
        op.execute(sql)


def downgrade():
    raise RuntimeError("Preserve booking, payment-access and camera history; use a compatible application or a forward migration.")
