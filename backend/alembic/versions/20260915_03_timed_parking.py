"""Frozen prepaid single-entry windows and bounded capacity holds.

Revision ID: 20260915_03
Revises: 20260915_02
"""
from alembic import op

revision = "20260915_03"
down_revision = "20260915_02"
branch_labels = None
depends_on = None

UPGRADE_SQL = ("ALTER TABLE parking_sites ADD COLUMN customer_booking_mode VARCHAR(16) DEFAULT 'legacy' NOT NULL",
 "ALTER TABLE subscription_plans ADD COLUMN product_kind VARCHAR(8) DEFAULT 'monthly' NOT NULL",
 'ALTER TABLE subscription_plans ADD COLUMN duration_minutes INTEGER',
 "ALTER TABLE portal_orders ADD COLUMN product_kind VARCHAR(8) DEFAULT 'monthly' NOT NULL",
 'ALTER TABLE portal_orders ADD COLUMN plan_name VARCHAR(100)',
 'ALTER TABLE portal_orders ADD COLUMN duration_days INTEGER',
 'ALTER TABLE portal_orders ADD COLUMN duration_minutes INTEGER',
 'ALTER TABLE portal_orders ADD COLUMN start_at TIMESTAMP WITHOUT TIME ZONE',
 'ALTER TABLE portal_orders ADD COLUMN end_at TIMESTAMP WITHOUT TIME ZONE',
 'ALTER TABLE portal_orders ADD COLUMN arrival_deadline TIMESTAMP WITHOUT TIME ZONE',
 'ALTER TABLE portal_orders ADD COLUMN zone_id INTEGER REFERENCES zones (id)',
 'ALTER TABLE portal_orders ADD COLUMN slot_id INTEGER REFERENCES parking_slots (id)',
 'ALTER TABLE portal_orders ADD COLUMN requested_zone_id INTEGER',
 'ALTER TABLE portal_orders ADD COLUMN rate_config_id INTEGER',
 'ALTER TABLE portal_orders ADD COLUMN rate_ticket_type VARCHAR(8)',
 'ALTER TABLE portal_orders ADD COLUMN rate_unit_price BIGINT',
 'ALTER TABLE portal_orders ADD COLUMN rate_effective_date DATE',
 'ALTER TABLE portal_orders ADD COLUMN timed_pass_id VARCHAR(36)',
 'ALTER TABLE parking_reservations ADD COLUMN order_id VARCHAR(36) REFERENCES portal_orders (id)',
 'ALTER TABLE parking_sessions ADD COLUMN timed_pass_id VARCHAR(36)',
 'ALTER TABLE parking_sessions ADD COLUMN prepaid_start_at TIMESTAMP WITHOUT TIME ZONE',
 'ALTER TABLE parking_sessions ADD COLUMN prepaid_end_at TIMESTAMP WITHOUT TIME ZONE',
 'ALTER TABLE subscription_plans ALTER COLUMN duration_days DROP NOT NULL',
 'ALTER TABLE subscription_plans DROP CONSTRAINT IF EXISTS ck_portal_plan_duration',
 "ALTER TABLE subscription_plans ADD CONSTRAINT ck_portal_plan_duration CHECK ((product_kind='monthly' AND "
 "duration_days BETWEEN 1 AND 366 AND duration_minutes IS NULL) OR (product_kind='hourly' AND duration_days "
 "IS NULL AND duration_minutes BETWEEN 60 AND 1440 AND duration_minutes % 60=0) OR (product_kind='daily' AND "
 'duration_days IS NULL AND duration_minutes=1440))',
 'ALTER TABLE portal_orders DROP CONSTRAINT IF EXISTS ck_portal_order_fulfilled',
 'ALTER TABLE portal_orders ADD CONSTRAINT ck_portal_order_fulfilled CHECK (status NOT IN '
 "('fulfilled','refunded') OR (receipt_id IS NOT NULL AND ((product_kind='monthly' AND monthly_pass_id IS "
 "NOT NULL AND timed_pass_id IS NULL) OR (product_kind IN ('hourly','daily') AND timed_pass_id IS NOT NULL "
 'AND monthly_pass_id IS NULL))))',
 'ALTER TABLE portal_orders DROP CONSTRAINT IF EXISTS ck_portal_order_product',
 'ALTER TABLE portal_orders ADD CONSTRAINT ck_portal_order_product CHECK (product_kind IN '
 "('monthly','hourly','daily'))",
 'ALTER TABLE portal_orders DROP CONSTRAINT IF EXISTS ck_portal_order_timed',
 "ALTER TABLE portal_orders ADD CONSTRAINT ck_portal_order_timed CHECK (product_kind='monthly' OR (start_at "
 'IS NOT NULL AND end_at>start_at AND duration_minutes>0 AND slot_id IS NOT NULL AND '
 'arrival_deadline>=start_at AND arrival_deadline<=end_at AND rate_config_id>0 AND rate_ticket_type IN '
 "('HOURLY','DAILY') AND rate_unit_price>=0 AND rate_effective_date IS NOT NULL))",
 'ALTER TABLE payments DROP CONSTRAINT IF EXISTS ck_payment_source',
 "ALTER TABLE payments ADD CONSTRAINT ck_payment_source CHECK (source_type IN ('parking_session', "
 "'monthly_pass', 'portal_order'))",
 '\n'
 'CREATE TABLE parking_capacity_holds (\n'
 '\tid VARCHAR(36) NOT NULL, \n'
 '\torder_id VARCHAR(36) NOT NULL, \n'
 '\tsite_id INTEGER NOT NULL, \n'
 '\tslot_id INTEGER NOT NULL, \n'
 '\tcustomer_id INTEGER NOT NULL, \n'
 '\tvehicle_id INTEGER NOT NULL, \n'
 '\tstart_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, \n'
 '\tend_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, \n'
 '\texpires_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, \n'
 '\tstatus VARCHAR(12) NOT NULL, \n'
 '\treservation_id VARCHAR(36), \n'
 '\tcreated_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, \n'
 '\tPRIMARY KEY (id), \n'
 "\tCONSTRAINT ck_capacity_hold_status CHECK (status IN ('held','converted','released','expired')), \n"
 '\tCONSTRAINT ck_capacity_hold_window CHECK (end_at>start_at AND expires_at<=end_at), \n'
 '\tUNIQUE (order_id), \n'
 '\tFOREIGN KEY(order_id) REFERENCES portal_orders (id), \n'
 '\tFOREIGN KEY(site_id) REFERENCES parking_sites (id), \n'
 '\tFOREIGN KEY(slot_id) REFERENCES parking_slots (id), \n'
 '\tFOREIGN KEY(customer_id) REFERENCES customers (id), \n'
 '\tFOREIGN KEY(vehicle_id) REFERENCES vehicles (id), \n'
 '\tUNIQUE (reservation_id), \n'
 '\tFOREIGN KEY(reservation_id) REFERENCES parking_reservations (id)\n'
 ')\n'
 '\n',
 'CREATE INDEX ix_capacity_hold_due ON parking_capacity_holds (status, expires_at)',
 'CREATE INDEX ix_capacity_hold_slot_window ON parking_capacity_holds (slot_id, start_at, end_at)',
 '\n'
 'CREATE TABLE timed_parking_passes (\n'
 '\tid VARCHAR(36) NOT NULL, \n'
 '\torder_id VARCHAR(36) NOT NULL, \n'
 '\treservation_id VARCHAR(36) NOT NULL, \n'
 '\tsite_id INTEGER NOT NULL, \n'
 '\tslot_id INTEGER NOT NULL, \n'
 '\tcustomer_id INTEGER NOT NULL, \n'
 '\tvehicle_id INTEGER NOT NULL, \n'
 '\tvehicle_type_id INTEGER NOT NULL, \n'
 '\tstart_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, \n'
 '\tend_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, \n'
 '\tarrival_deadline TIMESTAMP WITHOUT TIME ZONE NOT NULL, \n'
 '\tamount BIGINT NOT NULL, \n'
 '\trate_config_id INTEGER NOT NULL, \n'
 '\trate_ticket_type VARCHAR(8) NOT NULL, \n'
 '\trate_unit_price BIGINT NOT NULL, \n'
 '\trate_effective_date DATE NOT NULL, \n'
 '\tstatus VARCHAR(12) NOT NULL, \n'
 '\tsession_id VARCHAR(36), \n'
 '\tcreated_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, \n'
 '\tPRIMARY KEY (id), \n'
 "\tCONSTRAINT ck_timed_pass_status CHECK (status IN ('ready','consumed','expired','revoked')), \n"
 '\tCONSTRAINT ck_timed_pass_window CHECK (end_at>start_at AND arrival_deadline>=start_at AND '
 'arrival_deadline<=end_at), \n'
 '\tCONSTRAINT ck_timed_pass_money CHECK (amount>0 AND rate_unit_price>=0 AND rate_ticket_type IN '
 "('HOURLY','DAILY')), \n"
 '\tUNIQUE (order_id), \n'
 '\tFOREIGN KEY(order_id) REFERENCES portal_orders (id), \n'
 '\tUNIQUE (reservation_id), \n'
 '\tFOREIGN KEY(reservation_id) REFERENCES parking_reservations (id), \n'
 '\tFOREIGN KEY(site_id) REFERENCES parking_sites (id), \n'
 '\tFOREIGN KEY(slot_id) REFERENCES parking_slots (id), \n'
 '\tFOREIGN KEY(customer_id) REFERENCES customers (id), \n'
 '\tFOREIGN KEY(vehicle_id) REFERENCES vehicles (id), \n'
 '\tFOREIGN KEY(vehicle_type_id) REFERENCES vehicle_types (id), \n'
 '\tUNIQUE (session_id), \n'
 '\tFOREIGN KEY(session_id) REFERENCES parking_sessions (id)\n'
 ')\n'
 '\n',
 'CREATE INDEX ix_timed_pass_customer ON timed_parking_passes (customer_id, start_at)',
 'CREATE INDEX ix_timed_pass_vehicle ON timed_parking_passes (vehicle_id, status)',
 'CREATE UNIQUE INDEX uq_portal_orders_timed_pass_id ON portal_orders (timed_pass_id)',
 'CREATE UNIQUE INDEX uq_parking_sessions_timed_pass_id ON parking_sessions (timed_pass_id)',
 'CREATE UNIQUE INDEX uq_parking_reservations_order_id ON parking_reservations (order_id)',
 'DROP TRIGGER IF EXISTS trg_parking_sessions_billing_snapshot_guard ON parking_sessions',
 'DROP TRIGGER IF EXISTS trg_payment_guard ON payments',
 'DROP TRIGGER IF EXISTS trg_payment_demo_boundary ON payments',
 'DROP TRIGGER IF EXISTS trg_payment_site_guard ON payments',
 'DROP TRIGGER IF EXISTS trg_cash_shift_site_immutable ON cash_shifts',
 '\n'
 'CREATE OR REPLACE FUNCTION parking_billing_snapshot_guard() RETURNS trigger AS $$\n'
 'BEGIN\n'
 "    IF TG_OP = 'DELETE' THEN\n"
 '        IF OLD.billing_policy_version IS NOT NULL THEN\n'
 "            RAISE EXCEPTION 'billing snapshot history cannot be deleted' USING ERRCODE = '23514';\n"
 '        END IF;\n'
 '        RETURN OLD;\n'
 '    END IF;\n'
 "    IF TG_OP = 'UPDATE' THEN\n"
 '        IF ROW(NEW.billing_policy_version, NEW.rate_config_id, NEW.rate_ticket_type,\n'
 '               NEW.rate_unit_price, NEW.rate_effective_date) IS DISTINCT FROM\n'
 '           ROW(OLD.billing_policy_version, OLD.rate_config_id, OLD.rate_ticket_type,\n'
 '               OLD.rate_unit_price, OLD.rate_effective_date) THEN\n'
 "            RAISE EXCEPTION 'billing snapshot immutable' USING ERRCODE = '23514';\n"
 '        END IF;\n'
 "        IF OLD.status = 'cancelled' AND ROW(NEW.status, NEW.check_out_time, NEW.parking_fee, "
 'NEW.staff_out_id)\n'
 '            IS DISTINCT FROM ROW(OLD.status, OLD.check_out_time, OLD.parking_fee, OLD.staff_out_id) THEN\n'
 "            RAISE EXCEPTION 'cancelled parking session is terminal' USING ERRCODE = '23514';\n"
 '        END IF;\n'
 '    END IF;\n'
 '    IF NOT (NEW.billing_policy_version IS NULL AND NEW.rate_config_id IS NULL\n'
 '        AND NEW.rate_ticket_type IS NULL AND NEW.rate_unit_price IS NULL AND NEW.rate_effective_date IS '
 'NULL)\n'
 "        AND NOT COALESCE((NEW.billing_policy_version IN ('entry-v1','prepaid-window-v1') AND "
 'NEW.rate_config_id > 0\n'
 "        AND NEW.rate_ticket_type IN ('HOURLY', 'DAILY') AND NEW.rate_unit_price BETWEEN 0 AND "
 '9007199254740991\n'
 '        AND NEW.rate_effective_date <= NEW.check_in_time::date\n'
 '        AND (NEW.monthly_pass_id IS NULL OR NEW.monthly_coverage_end IS NOT NULL)), false) THEN\n'
 "        RAISE EXCEPTION 'billing snapshot invalid' USING ERRCODE = '23514';\n"
 '    END IF;\n'
 '    RETURN NEW;\n'
 'END; $$ LANGUAGE plpgsql;\n'
 'CREATE TRIGGER trg_parking_sessions_billing_snapshot_guard BEFORE INSERT OR UPDATE OR DELETE ON '
 'parking_sessions\n'
 'FOR EACH ROW EXECUTE FUNCTION parking_billing_snapshot_guard();\n',
 '\n'
 'CREATE OR REPLACE FUNCTION parking_payment_guard() RETURNS trigger AS $$\n'
 'DECLARE original payments%ROWTYPE; active_shift cash_shifts%ROWTYPE; refunded numeric; source_amount '
 'bigint;\n'
 'BEGIN\n'
 "    IF TG_OP <> 'INSERT' THEN RAISE EXCEPTION 'payment is immutable' USING ERRCODE = '23514'; END IF;\n"
 "    IF NEW.kind = 'receipt' THEN\n"
 "        IF NEW.source_type = 'parking_session' THEN\n"
 '            SELECT parking_fee INTO source_amount FROM parking_sessions WHERE id = NEW.source_id AND '
 "status = 'completed' FOR UPDATE;\n"
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
 '\n'
 'CREATE OR REPLACE FUNCTION parking_payment_demo_boundary() RETURNS trigger AS $$\n'
 'BEGIN\n'
 "    IF (NEW.method='demo' AND (NEW.source_type NOT IN ('monthly_pass','portal_order') OR NEW.shift_id IS "
 'NOT NULL\n'
 "        OR (NEW.kind='receipt' AND NEW.collected_by_id IS NOT NULL)))\n"
 "       OR (NEW.kind='refund' AND EXISTS (SELECT 1 FROM payments original\n"
 "           WHERE original.id=NEW.original_payment_id AND ((original.method='demo') != "
 "(NEW.method='demo')))) THEN\n"
 "        RAISE EXCEPTION 'demo payment cannot be mixed with real collection' USING ERRCODE='23514';\n"
 '    END IF;\n'
 '    RETURN NEW;\n'
 'END; $$ LANGUAGE plpgsql;\n'
 'CREATE TRIGGER trg_payment_demo_boundary BEFORE INSERT ON payments\n'
 'FOR EACH ROW EXECUTE FUNCTION parking_payment_demo_boundary();\n',
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
 'CREATE OR REPLACE FUNCTION trg_site_booking_mode_insert_fn() RETURNS trigger AS $$\n'
 'BEGIN\n'
 '    \n'
 "    IF NEW.customer_booking_mode NOT IN ('legacy','paid_packages') THEN RAISE EXCEPTION 'unknown customer "
 "booking mode' USING ERRCODE='23514'; END IF;\n"
 '    RETURN NEW;\n'
 'END; $$ LANGUAGE plpgsql;\n'
 'CREATE TRIGGER trg_site_booking_mode_insert BEFORE INSERT ON parking_sites FOR EACH ROW EXECUTE FUNCTION '
 'trg_site_booking_mode_insert_fn();\n'
 '\n'
 'CREATE OR REPLACE FUNCTION trg_site_booking_mode_update_fn() RETURNS trigger AS $$\n'
 'BEGIN\n'
 '    \n'
 "    IF NEW.customer_booking_mode NOT IN ('legacy','paid_packages') THEN RAISE EXCEPTION 'unknown customer "
 "booking mode' USING ERRCODE='23514'; END IF;\n"
 '    RETURN NEW;\n'
 'END; $$ LANGUAGE plpgsql;\n'
 'CREATE TRIGGER trg_site_booking_mode_update BEFORE UPDATE ON parking_sites FOR EACH ROW EXECUTE FUNCTION '
 'trg_site_booking_mode_update_fn();\n'
 '\n'
 'CREATE OR REPLACE FUNCTION trg_timed_order_insert_fn() RETURNS trigger AS $$\n'
 'BEGIN\n'
 '    \n'
 "    IF NEW.product_kind!='monthly' AND NOT COALESCE((NEW.status='pending' AND NEW.start_at IS NOT NULL AND "
 'NEW.end_at>NEW.start_at AND NEW.arrival_deadline>=NEW.start_at AND NEW.arrival_deadline<=NEW.end_at AND '
 'NEW.expires_at<=NEW.arrival_deadline AND NEW.rate_unit_price>=0 AND NEW.rate_unit_price<=9007199254740991 '
 "AND NEW.rate_ticket_type IN ('HOURLY','DAILY') AND NEW.rate_config_id>0 AND NEW.rate_effective_date IS NOT "
 'NULL AND NEW.duration_minutes>0 AND NEW.plan_name IS NOT NULL AND NEW.slot_id IS NOT NULL AND NEW.zone_id '
 'IS NOT NULL AND NEW.timed_pass_id IS NULL AND NEW.receipt_id IS NULL AND NEW.monthly_pass_id IS NULL), '
 "false) THEN RAISE EXCEPTION 'timed order snapshot invalid' USING ERRCODE='23514'; END IF;\n"
 '    RETURN NEW;\n'
 'END; $$ LANGUAGE plpgsql;\n'
 'CREATE TRIGGER trg_timed_order_insert BEFORE INSERT ON portal_orders FOR EACH ROW EXECUTE FUNCTION '
 'trg_timed_order_insert_fn();\n'
 '\n'
 'CREATE OR REPLACE FUNCTION trg_timed_order_price_source_fn() RETURNS trigger AS $$\n'
 'BEGIN\n'
 '    \n'
 "    IF NEW.product_kind!='monthly' AND NOT EXISTS (SELECT 1 FROM subscription_plans p JOIN vehicles v ON "
 'v.id=NEW.vehicle_id JOIN price_configs r ON r.id=NEW.rate_config_id WHERE p.id=NEW.plan_id AND p.is_active '
 'IS TRUE AND p.site_id=NEW.site_id AND p.vehicle_type_id=v.vehicle_type_id AND p.name=NEW.plan_name AND '
 'p.price=NEW.amount AND p.product_kind=NEW.product_kind AND p.duration_minutes=NEW.duration_minutes AND '
 'r.vehicle_type_id=v.vehicle_type_id AND r.is_active IS TRUE AND r.price=NEW.rate_unit_price AND '
 'r.ticket_type=NEW.rate_ticket_type AND r.effective_date=NEW.rate_effective_date) THEN RAISE EXCEPTION '
 "'timed order price source invalid' USING ERRCODE='23514'; END IF;\n"
 '    RETURN NEW;\n'
 'END; $$ LANGUAGE plpgsql;\n'
 'CREATE TRIGGER trg_timed_order_price_source BEFORE INSERT ON portal_orders FOR EACH ROW EXECUTE FUNCTION '
 'trg_timed_order_price_source_fn();\n'
 '\n'
 'CREATE OR REPLACE FUNCTION trg_timed_order_immutable_fn() RETURNS trigger AS $$\n'
 'BEGIN\n'
 '    \n'
 '    IF NEW.id IS DISTINCT FROM OLD.id OR NEW.user_id IS DISTINCT FROM OLD.user_id OR NEW.customer_id IS '
 'DISTINCT FROM OLD.customer_id OR NEW.vehicle_id IS DISTINCT FROM OLD.vehicle_id OR NEW.plan_id IS DISTINCT '
 'FROM OLD.plan_id OR NEW.site_id IS DISTINCT FROM OLD.site_id OR NEW.amount IS DISTINCT FROM OLD.amount OR '
 'NEW.start_date IS DISTINCT FROM OLD.start_date OR NEW.end_date IS DISTINCT FROM OLD.end_date OR '
 'NEW.payment_mode IS DISTINCT FROM OLD.payment_mode OR NEW.idempotency_key IS DISTINCT FROM '
 'OLD.idempotency_key OR NEW.demo_token IS DISTINCT FROM OLD.demo_token OR NEW.expires_at IS DISTINCT FROM '
 'OLD.expires_at OR NEW.created_at IS DISTINCT FROM OLD.created_at OR NEW.product_kind IS DISTINCT FROM '
 'OLD.product_kind OR NEW.plan_name IS DISTINCT FROM OLD.plan_name OR NEW.duration_days IS DISTINCT FROM '
 'OLD.duration_days OR NEW.duration_minutes IS DISTINCT FROM OLD.duration_minutes OR NEW.start_at IS '
 'DISTINCT FROM OLD.start_at OR NEW.end_at IS DISTINCT FROM OLD.end_at OR NEW.arrival_deadline IS DISTINCT '
 'FROM OLD.arrival_deadline OR NEW.zone_id IS DISTINCT FROM OLD.zone_id OR NEW.slot_id IS DISTINCT FROM '
 'OLD.slot_id OR NEW.requested_zone_id IS DISTINCT FROM OLD.requested_zone_id OR NEW.rate_config_id IS '
 'DISTINCT FROM OLD.rate_config_id OR NEW.rate_ticket_type IS DISTINCT FROM OLD.rate_ticket_type OR '
 'NEW.rate_unit_price IS DISTINCT FROM OLD.rate_unit_price OR NEW.rate_effective_date IS DISTINCT FROM '
 "OLD.rate_effective_date OR (OLD.status IN ('fulfilled','refunded') AND (NEW.timed_pass_id IS DISTINCT FROM "
 'OLD.timed_pass_id OR NEW.monthly_pass_id IS DISTINCT FROM OLD.monthly_pass_id OR NEW.receipt_id IS '
 "DISTINCT FROM OLD.receipt_id OR NEW.status NOT IN ('fulfilled','refunded'))) OR (OLD.status='refunded' AND "
 "NEW.status!='refunded') THEN RAISE EXCEPTION 'portal order snapshot immutable' USING ERRCODE='23514'; END "
 'IF;\n'
 '    RETURN NEW;\n'
 'END; $$ LANGUAGE plpgsql;\n'
 'CREATE TRIGGER trg_timed_order_immutable BEFORE UPDATE ON portal_orders FOR EACH ROW EXECUTE FUNCTION '
 'trg_timed_order_immutable_fn();\n'
 '\n'
 'CREATE OR REPLACE FUNCTION trg_timed_order_delete_fn() RETURNS trigger AS $$\n'
 'BEGIN\n'
 '    \n'
 "    IF true THEN RAISE EXCEPTION 'portal order history cannot be deleted' USING ERRCODE='23514'; END IF;\n"
 '    RETURN OLD;\n'
 'END; $$ LANGUAGE plpgsql;\n'
 'CREATE TRIGGER trg_timed_order_delete BEFORE DELETE ON portal_orders FOR EACH ROW EXECUTE FUNCTION '
 'trg_timed_order_delete_fn();\n'
 '\n'
 'CREATE OR REPLACE FUNCTION trg_timed_order_replace_fn() RETURNS trigger AS $$\n'
 'BEGIN\n'
 '    \n'
 "    IF EXISTS (SELECT 1 FROM portal_orders WHERE id=NEW.id) THEN RAISE EXCEPTION 'portal order snapshot "
 "immutable' USING ERRCODE='23514'; END IF;\n"
 '    RETURN NEW;\n'
 'END; $$ LANGUAGE plpgsql;\n'
 'CREATE TRIGGER trg_timed_order_replace BEFORE INSERT ON portal_orders FOR EACH ROW EXECUTE FUNCTION '
 'trg_timed_order_replace_fn();\n'
 '\n'
 'CREATE OR REPLACE FUNCTION trg_timed_order_fulfilled_fn() RETURNS trigger AS $$\n'
 'BEGIN\n'
 '    \n'
 "    IF NEW.product_kind!='monthly' AND NEW.status IN ('fulfilled','refunded') AND NOT EXISTS (SELECT 1 "
 'FROM timed_parking_passes t JOIN payments p ON p.id=NEW.receipt_id WHERE t.id=NEW.timed_pass_id AND '
 "t.order_id=NEW.id AND p.source_type='portal_order' AND p.source_id=NEW.id AND p.kind='receipt' AND "
 "p.amount=NEW.amount AND p.site_id=NEW.site_id) THEN RAISE EXCEPTION 'paid order requires ticket and "
 "receipt' USING ERRCODE='23514'; END IF;\n"
 '    RETURN NEW;\n'
 'END; $$ LANGUAGE plpgsql;\n'
 'CREATE TRIGGER trg_timed_order_fulfilled BEFORE UPDATE ON portal_orders FOR EACH ROW EXECUTE FUNCTION '
 'trg_timed_order_fulfilled_fn();\n'
 '\n'
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
 "parking_reservations r WHERE r.slot_id=NEW.slot_id AND r.status IN ('confirmed','arrived') AND "
 'r.start_at<NEW.end_at AND r.end_at>NEW.start_at) OR EXISTS (SELECT 1 FROM guaranteed_allocations a WHERE '
 "a.slot_id=NEW.slot_id AND a.status='active' AND a.start_at<NEW.end_at AND a.end_at>NEW.start_at) THEN "
 "RAISE EXCEPTION 'capacity hold source or overlap invalid' USING ERRCODE='23514'; END IF;\n"
 '    RETURN NEW;\n'
 'END; $$ LANGUAGE plpgsql;\n'
 'CREATE TRIGGER trg_capacity_hold_insert BEFORE INSERT ON parking_capacity_holds FOR EACH ROW EXECUTE '
 'FUNCTION trg_capacity_hold_insert_fn();\n'
 '\n'
 'CREATE OR REPLACE FUNCTION trg_capacity_hold_update_fn() RETURNS trigger AS $$\n'
 'BEGIN\n'
 '    \n'
 '    IF NEW.id IS DISTINCT FROM OLD.id OR NEW.order_id IS DISTINCT FROM OLD.order_id OR NEW.site_id IS '
 'DISTINCT FROM OLD.site_id OR NEW.slot_id IS DISTINCT FROM OLD.slot_id OR NEW.customer_id IS DISTINCT FROM '
 'OLD.customer_id OR NEW.vehicle_id IS DISTINCT FROM OLD.vehicle_id OR NEW.start_at IS DISTINCT FROM '
 'OLD.start_at OR NEW.end_at IS DISTINCT FROM OLD.end_at OR NEW.created_at IS DISTINCT FROM OLD.created_at '
 "OR NEW.expires_at IS DISTINCT FROM OLD.expires_at OR (OLD.status!='held' AND NEW.status!=OLD.status) OR "
 "(NEW.reservation_id IS DISTINCT FROM OLD.reservation_id AND (OLD.status!='held' OR "
 "NEW.status!='converted')) OR (NEW.status='converted' AND NOT EXISTS (SELECT 1 FROM parking_reservations r "
 "WHERE r.id=NEW.reservation_id AND r.order_id=NEW.order_id)) THEN RAISE EXCEPTION 'capacity hold immutable "
 "or terminal' USING ERRCODE='23514'; END IF;\n"
 '    RETURN NEW;\n'
 'END; $$ LANGUAGE plpgsql;\n'
 'CREATE TRIGGER trg_capacity_hold_update BEFORE UPDATE ON parking_capacity_holds FOR EACH ROW EXECUTE '
 'FUNCTION trg_capacity_hold_update_fn();\n'
 '\n'
 'CREATE OR REPLACE FUNCTION trg_parking_capacity_holds_delete_fn() RETURNS trigger AS $$\n'
 'BEGIN\n'
 '    \n'
 "    IF true THEN RAISE EXCEPTION 'prepaid history cannot be deleted' USING ERRCODE='23514'; END IF;\n"
 '    RETURN OLD;\n'
 'END; $$ LANGUAGE plpgsql;\n'
 'CREATE TRIGGER trg_parking_capacity_holds_delete BEFORE DELETE ON parking_capacity_holds FOR EACH ROW '
 'EXECUTE FUNCTION trg_parking_capacity_holds_delete_fn();\n'
 '\n'
 'CREATE OR REPLACE FUNCTION trg_parking_capacity_holds_replace_fn() RETURNS trigger AS $$\n'
 'BEGIN\n'
 '    PERFORM 1 FROM vehicles WHERE id=NEW.vehicle_id FOR NO KEY UPDATE; PERFORM 1 FROM vehicle_types WHERE '
 'id=(SELECT vehicle_type_id FROM vehicles WHERE id=NEW.vehicle_id) FOR SHARE; PERFORM 1 FROM parking_slots '
 'WHERE id=NEW.slot_id FOR UPDATE;\n'
 "    IF EXISTS (SELECT 1 FROM parking_capacity_holds WHERE id=NEW.id) THEN RAISE EXCEPTION 'prepaid history "
 "cannot be replaced' USING ERRCODE='23514'; END IF;\n"
 '    RETURN NEW;\n'
 'END; $$ LANGUAGE plpgsql;\n'
 'CREATE TRIGGER trg_parking_capacity_holds_replace BEFORE INSERT ON parking_capacity_holds FOR EACH ROW '
 'EXECUTE FUNCTION trg_parking_capacity_holds_replace_fn();\n'
 '\n'
 'CREATE OR REPLACE FUNCTION trg_timed_parking_passes_delete_fn() RETURNS trigger AS $$\n'
 'BEGIN\n'
 '    \n'
 "    IF true THEN RAISE EXCEPTION 'prepaid history cannot be deleted' USING ERRCODE='23514'; END IF;\n"
 '    RETURN OLD;\n'
 'END; $$ LANGUAGE plpgsql;\n'
 'CREATE TRIGGER trg_timed_parking_passes_delete BEFORE DELETE ON timed_parking_passes FOR EACH ROW EXECUTE '
 'FUNCTION trg_timed_parking_passes_delete_fn();\n'
 '\n'
 'CREATE OR REPLACE FUNCTION trg_timed_parking_passes_replace_fn() RETURNS trigger AS $$\n'
 'BEGIN\n'
 '    \n'
 "    IF EXISTS (SELECT 1 FROM timed_parking_passes WHERE id=NEW.id) THEN RAISE EXCEPTION 'prepaid history "
 "cannot be replaced' USING ERRCODE='23514'; END IF;\n"
 '    RETURN NEW;\n'
 'END; $$ LANGUAGE plpgsql;\n'
 'CREATE TRIGGER trg_timed_parking_passes_replace BEFORE INSERT ON timed_parking_passes FOR EACH ROW EXECUTE '
 'FUNCTION trg_timed_parking_passes_replace_fn();\n'
 '\n'
 'CREATE OR REPLACE FUNCTION trg_timed_pass_insert_fn() RETURNS trigger AS $$\n'
 'BEGIN\n'
 '    \n'
 "    IF NEW.status!='ready' OR NEW.session_id IS NOT NULL OR NOT EXISTS (SELECT 1 FROM portal_orders o JOIN "
 'parking_reservations r ON r.order_id=o.id JOIN vehicles v ON v.id=o.vehicle_id WHERE o.id=NEW.order_id AND '
 "r.id=NEW.reservation_id AND r.status='confirmed' AND o.status IN ('pending','review') AND "
 'v.vehicle_type_id=NEW.vehicle_type_id AND o.site_id=NEW.site_id AND o.slot_id=NEW.slot_id AND '
 'o.customer_id=NEW.customer_id AND o.vehicle_id=NEW.vehicle_id AND o.start_at=NEW.start_at AND '
 'o.end_at=NEW.end_at AND o.arrival_deadline=NEW.arrival_deadline AND o.amount=NEW.amount AND '
 'o.rate_config_id=NEW.rate_config_id AND o.rate_ticket_type=NEW.rate_ticket_type AND '
 'o.rate_unit_price=NEW.rate_unit_price AND o.rate_effective_date=NEW.rate_effective_date) THEN RAISE '
 "EXCEPTION 'prepaid ticket source invalid' USING ERRCODE='23514'; END IF;\n"
 '    RETURN NEW;\n'
 'END; $$ LANGUAGE plpgsql;\n'
 'CREATE TRIGGER trg_timed_pass_insert BEFORE INSERT ON timed_parking_passes FOR EACH ROW EXECUTE FUNCTION '
 'trg_timed_pass_insert_fn();\n'
 '\n'
 'CREATE OR REPLACE FUNCTION trg_timed_pass_update_fn() RETURNS trigger AS $$\n'
 'BEGIN\n'
 '    \n'
 '    IF NEW.id IS DISTINCT FROM OLD.id OR NEW.order_id IS DISTINCT FROM OLD.order_id OR NEW.site_id IS '
 'DISTINCT FROM OLD.site_id OR NEW.slot_id IS DISTINCT FROM OLD.slot_id OR NEW.customer_id IS DISTINCT FROM '
 'OLD.customer_id OR NEW.vehicle_id IS DISTINCT FROM OLD.vehicle_id OR NEW.start_at IS DISTINCT FROM '
 'OLD.start_at OR NEW.end_at IS DISTINCT FROM OLD.end_at OR NEW.created_at IS DISTINCT FROM OLD.created_at '
 'OR NEW.reservation_id IS DISTINCT FROM OLD.reservation_id OR NEW.vehicle_type_id IS DISTINCT FROM '
 'OLD.vehicle_type_id OR NEW.arrival_deadline IS DISTINCT FROM OLD.arrival_deadline OR NEW.amount IS '
 'DISTINCT FROM OLD.amount OR NEW.rate_config_id IS DISTINCT FROM OLD.rate_config_id OR NEW.rate_ticket_type '
 'IS DISTINCT FROM OLD.rate_ticket_type OR NEW.rate_unit_price IS DISTINCT FROM OLD.rate_unit_price OR '
 "NEW.rate_effective_date IS DISTINCT FROM OLD.rate_effective_date OR (OLD.status!='ready' AND "
 "NEW.status!=OLD.status) OR (NEW.session_id IS DISTINCT FROM OLD.session_id AND (OLD.status!='ready' OR "
 "NEW.status!='consumed')) OR (NEW.status='consumed' AND NOT EXISTS (SELECT 1 FROM parking_sessions s WHERE "
 "s.id=NEW.session_id AND s.timed_pass_id=NEW.id)) THEN RAISE EXCEPTION 'prepaid ticket immutable or "
 "consumed' USING ERRCODE='23514'; END IF;\n"
 '    RETURN NEW;\n'
 'END; $$ LANGUAGE plpgsql;\n'
 'CREATE TRIGGER trg_timed_pass_update BEFORE UPDATE ON timed_parking_passes FOR EACH ROW EXECUTE FUNCTION '
 'trg_timed_pass_update_fn();\n'
 '\n'
 'CREATE OR REPLACE FUNCTION trg_parking_reservations_capacity_hold_fn() RETURNS trigger AS $$\n'
 'BEGIN\n'
 '    PERFORM 1 FROM vehicles WHERE id=NEW.vehicle_id FOR NO KEY UPDATE; PERFORM 1 FROM vehicle_types WHERE '
 'id=(SELECT vehicle_type_id FROM vehicles WHERE id=NEW.vehicle_id) FOR SHARE; PERFORM 1 FROM parking_slots '
 'WHERE id=NEW.slot_id FOR UPDATE;\n'
 "    IF EXISTS (SELECT 1 FROM parking_capacity_holds h WHERE h.slot_id=NEW.slot_id AND h.status='held' AND "
 "h.expires_at>(clock_timestamp() AT TIME ZONE 'Asia/Ho_Chi_Minh') AND h.order_id IS DISTINCT FROM "
 "NEW.order_id AND h.start_at<NEW.end_at AND h.end_at>NEW.start_at) THEN RAISE EXCEPTION 'slot has a live "
 "payment hold' USING ERRCODE='23514'; END IF;\n"
 '    RETURN NEW;\n'
 'END; $$ LANGUAGE plpgsql;\n'
 'CREATE TRIGGER trg_parking_reservations_capacity_hold BEFORE INSERT ON parking_reservations FOR EACH ROW '
 'EXECUTE FUNCTION trg_parking_reservations_capacity_hold_fn();\n'
 '\n'
 'CREATE OR REPLACE FUNCTION trg_guaranteed_allocations_capacity_hold_fn() RETURNS trigger AS $$\n'
 'BEGIN\n'
 '    PERFORM 1 FROM vehicles WHERE id=NEW.vehicle_id FOR NO KEY UPDATE; PERFORM 1 FROM vehicle_types WHERE '
 'id=(SELECT vehicle_type_id FROM vehicles WHERE id=NEW.vehicle_id) FOR SHARE; PERFORM 1 FROM parking_slots '
 'WHERE id=NEW.slot_id FOR UPDATE;\n'
 "    IF EXISTS (SELECT 1 FROM parking_capacity_holds h WHERE h.slot_id=NEW.slot_id AND h.status='held' AND "
 "h.expires_at>(clock_timestamp() AT TIME ZONE 'Asia/Ho_Chi_Minh') AND h.start_at<NEW.end_at AND "
 "h.end_at>NEW.start_at) THEN RAISE EXCEPTION 'slot has a live payment hold' USING ERRCODE='23514'; END IF;\n"
 '    RETURN NEW;\n'
 'END; $$ LANGUAGE plpgsql;\n'
 'CREATE TRIGGER trg_guaranteed_allocations_capacity_hold BEFORE INSERT ON guaranteed_allocations FOR EACH '
 'ROW EXECUTE FUNCTION trg_guaranteed_allocations_capacity_hold_fn();\n'
 '\n'
 'CREATE OR REPLACE FUNCTION trg_reservation_order_identity_fn() RETURNS trigger AS $$\n'
 'BEGIN\n'
 '    \n'
 "    IF NEW.order_id IS DISTINCT FROM OLD.order_id THEN RAISE EXCEPTION 'reservation order immutable' USING "
 "ERRCODE='23514'; END IF;\n"
 '    RETURN NEW;\n'
 'END; $$ LANGUAGE plpgsql;\n'
 'CREATE TRIGGER trg_reservation_order_identity BEFORE UPDATE ON parking_reservations FOR EACH ROW EXECUTE '
 'FUNCTION trg_reservation_order_identity_fn();\n'
 '\n'
 'CREATE OR REPLACE FUNCTION trg_reservation_paid_source_fn() RETURNS trigger AS $$\n'
 'BEGIN\n'
 '    PERFORM 1 FROM vehicles WHERE id=NEW.vehicle_id FOR NO KEY UPDATE; PERFORM 1 FROM vehicle_types WHERE '
 'id=(SELECT vehicle_type_id FROM vehicles WHERE id=NEW.vehicle_id) FOR SHARE; PERFORM 1 FROM parking_slots '
 'WHERE id=NEW.slot_id FOR UPDATE;\n'
 '    IF NEW.order_id IS NOT NULL AND NOT EXISTS (SELECT 1 FROM parking_capacity_holds h JOIN portal_orders '
 "o ON o.id=h.order_id WHERE h.order_id=NEW.order_id AND h.status='held' AND h.expires_at>(clock_timestamp() "
 "AT TIME ZONE 'Asia/Ho_Chi_Minh') AND o.status IN ('pending','review') AND h.slot_id=NEW.slot_id AND "
 'h.site_id=NEW.site_id AND h.vehicle_id=NEW.vehicle_id AND h.customer_id=NEW.customer_id AND '
 'h.start_at=NEW.start_at AND h.end_at=NEW.end_at AND o.arrival_deadline=NEW.arrival_deadline AND '
 "o.user_id=NEW.created_by_id) THEN RAISE EXCEPTION 'paid reservation requires live matching hold' USING "
 "ERRCODE='23514'; END IF;\n"
 '    RETURN NEW;\n'
 'END; $$ LANGUAGE plpgsql;\n'
 'CREATE TRIGGER trg_reservation_paid_source BEFORE INSERT ON parking_reservations FOR EACH ROW EXECUTE '
 'FUNCTION trg_reservation_paid_source_fn();\n'
 '\n'
 'CREATE OR REPLACE FUNCTION trg_parking_reservations_paid_booking_mode_fn() RETURNS trigger AS $$\n'
 'BEGIN\n'
 '    PERFORM 1 FROM vehicles WHERE id=NEW.vehicle_id FOR NO KEY UPDATE; PERFORM 1 FROM vehicle_types WHERE '
 'id=(SELECT vehicle_type_id FROM vehicles WHERE id=NEW.vehicle_id) FOR SHARE; PERFORM 1 FROM parking_slots '
 'WHERE id=NEW.slot_id FOR UPDATE;\n'
 '    IF EXISTS (SELECT 1 FROM parking_sites p WHERE p.id=NEW.site_id AND '
 "p.customer_booking_mode='paid_packages') AND NEW.order_id IS NULL AND NOT EXISTS (SELECT 1 FROM users u "
 "JOIN roles r ON r.id=u.role_id WHERE u.id=NEW.created_by_id AND u.is_active IS TRUE AND (r.name='admin' OR "
 "(r.name IN ('manager','staff') AND EXISTS (SELECT 1 FROM site_memberships m WHERE m.user_id=u.id AND "
 "m.site_id=NEW.site_id)))) AND NOT EXISTS (SELECT 1 FROM guaranteed_allocations a WHERE a.status='active' "
 'AND a.site_id=NEW.site_id AND a.vehicle_id=NEW.vehicle_id AND a.customer_id=NEW.customer_id AND '
 'a.start_at<=NEW.start_at AND a.end_at>=NEW.end_at AND a.slot_id=NEW.slot_id) THEN RAISE EXCEPTION '
 "'customer booking requires a paid package' USING ERRCODE='23514'; END IF;\n"
 '    RETURN NEW;\n'
 'END; $$ LANGUAGE plpgsql;\n'
 'CREATE TRIGGER trg_parking_reservations_paid_booking_mode BEFORE INSERT ON parking_reservations FOR EACH '
 'ROW EXECUTE FUNCTION trg_parking_reservations_paid_booking_mode_fn();\n'
 '\n'
 'CREATE OR REPLACE FUNCTION trg_site_waitlist_paid_booking_mode_fn() RETURNS trigger AS $$\n'
 'BEGIN\n'
 '    \n'
 '    IF EXISTS (SELECT 1 FROM parking_sites p WHERE p.id=NEW.site_id AND '
 "p.customer_booking_mode='paid_packages') AND NOT EXISTS (SELECT 1 FROM users u JOIN roles r ON "
 "r.id=u.role_id WHERE u.id=NEW.created_by_id AND u.is_active IS TRUE AND (r.name='admin' OR (r.name IN "
 "('manager','staff') AND EXISTS (SELECT 1 FROM site_memberships m WHERE m.user_id=u.id AND "
 "m.site_id=NEW.site_id)))) AND NOT EXISTS (SELECT 1 FROM guaranteed_allocations a WHERE a.status='active' "
 'AND a.site_id=NEW.site_id AND a.vehicle_id=NEW.vehicle_id AND a.customer_id=NEW.customer_id AND '
 "a.start_at<=NEW.start_at AND a.end_at>=NEW.end_at) THEN RAISE EXCEPTION 'customer booking requires a paid "
 "package' USING ERRCODE='23514'; END IF;\n"
 '    RETURN NEW;\n'
 'END; $$ LANGUAGE plpgsql;\n'
 'CREATE TRIGGER trg_site_waitlist_paid_booking_mode BEFORE INSERT ON site_waitlist FOR EACH ROW EXECUTE '
 'FUNCTION trg_site_waitlist_paid_booking_mode_fn();\n'
 '\n'
 'CREATE OR REPLACE FUNCTION trg_session_prepaid_immutable_fn() RETURNS trigger AS $$\n'
 'BEGIN\n'
 '    \n'
 '    IF NEW.timed_pass_id IS DISTINCT FROM OLD.timed_pass_id OR NEW.prepaid_start_at IS DISTINCT FROM '
 'OLD.prepaid_start_at OR NEW.prepaid_end_at IS DISTINCT FROM OLD.prepaid_end_at THEN RAISE EXCEPTION '
 "'session prepaid window immutable' USING ERRCODE='23514'; END IF;\n"
 '    RETURN NEW;\n'
 'END; $$ LANGUAGE plpgsql;\n'
 'CREATE TRIGGER trg_session_prepaid_immutable BEFORE UPDATE ON parking_sessions FOR EACH ROW EXECUTE '
 'FUNCTION trg_session_prepaid_immutable_fn();\n'
 '\n'
 'CREATE OR REPLACE FUNCTION trg_session_prepaid_source_fn() RETURNS trigger AS $$\n'
 'BEGIN\n'
 '    \n'
 "    IF (NEW.billing_policy_version='prepaid-window-v1' AND (NEW.timed_pass_id IS NULL OR "
 'NEW.monthly_pass_id IS NOT NULL OR NOT EXISTS (SELECT 1 FROM timed_parking_passes t JOIN portal_orders o '
 'ON o.id=t.order_id JOIN parking_reservations r ON r.id=t.reservation_id JOIN vehicles v ON '
 "v.id=t.vehicle_id JOIN payments p ON p.id=o.receipt_id WHERE t.id=NEW.timed_pass_id AND t.status='ready' "
 "AND t.session_id IS NULL AND o.status='fulfilled' AND r.status='confirmed' AND "
 "p.source_type='portal_order' AND p.source_id=o.id AND p.kind='receipt' AND p.amount=t.amount AND "
 't.slot_id=NEW.parking_slot_id AND t.customer_id=v.customer_id AND t.vehicle_type_id=v.vehicle_type_id AND '
 'NEW.check_in_time>=t.start_at AND NEW.check_in_time<t.arrival_deadline AND t.start_at=NEW.prepaid_start_at '
 'AND t.end_at=NEW.prepaid_end_at AND t.vehicle_id=NEW.vehicle_id AND t.rate_config_id=NEW.rate_config_id '
 'AND t.rate_ticket_type=NEW.rate_ticket_type AND t.rate_unit_price=NEW.rate_unit_price AND '
 't.rate_effective_date=NEW.rate_effective_date))) OR '
 "(COALESCE(NEW.billing_policy_version,'')!='prepaid-window-v1' AND (NEW.timed_pass_id IS NOT NULL OR "
 "NEW.prepaid_start_at IS NOT NULL OR NEW.prepaid_end_at IS NOT NULL)) THEN RAISE EXCEPTION 'session prepaid "
 "source invalid' USING ERRCODE='23514'; END IF;\n"
 '    RETURN NEW;\n'
 'END; $$ LANGUAGE plpgsql;\n'
 'CREATE TRIGGER trg_session_prepaid_source BEFORE INSERT ON parking_sessions FOR EACH ROW EXECUTE FUNCTION '
 'trg_session_prepaid_source_fn();\n'
 '\n'
 'CREATE OR REPLACE FUNCTION trg_session_capacity_hold_fn() RETURNS trigger AS $$\n'
 'BEGIN\n'
 '    \n'
 "    IF NEW.status='active' AND EXISTS (SELECT 1 FROM parking_capacity_holds h WHERE "
 "h.slot_id=NEW.parking_slot_id AND h.status='held' AND h.expires_at>(clock_timestamp() AT TIME ZONE "
 "'Asia/Ho_Chi_Minh') AND h.start_at < COALESCE((SELECT MAX(bound.end_at) FROM (SELECT r.end_at FROM "
 'parking_reservations r JOIN vehicles v ON v.id=r.vehicle_id WHERE r.slot_id=NEW.parking_slot_id AND '
 "r.vehicle_id=NEW.vehicle_id AND r.customer_id=v.customer_id AND r.status='confirmed' AND "
 'r.start_at<=NEW.check_in_time AND r.arrival_deadline>NEW.check_in_time UNION ALL SELECT a.end_at FROM '
 'guaranteed_allocations a JOIN vehicles v ON v.id=a.vehicle_id WHERE a.slot_id=NEW.parking_slot_id AND '
 "a.vehicle_id=NEW.vehicle_id AND a.customer_id=v.customer_id AND a.status='active' AND "
 "a.start_at<=NEW.check_in_time AND a.end_at>NEW.check_in_time) bound), '9999-12-31')) THEN RAISE EXCEPTION "
 "'slot has a live payment hold' USING ERRCODE='23514'; END IF;\n"
 '    RETURN NEW;\n'
 'END; $$ LANGUAGE plpgsql;\n'
 'CREATE TRIGGER trg_session_capacity_hold BEFORE INSERT ON parking_sessions FOR EACH ROW EXECUTE FUNCTION '
 'trg_session_capacity_hold_fn();\n'
 '\n'
 'CREATE OR REPLACE FUNCTION trg_payment_prepaid_source_fn() RETURNS trigger AS $$\n'
 'BEGIN\n'
 '    \n'
 "    IF NEW.source_type='portal_order' AND NEW.kind='receipt' AND NOT EXISTS (SELECT 1 FROM portal_orders o "
 'JOIN timed_parking_passes t ON t.order_id=o.id WHERE o.id=NEW.source_id AND o.amount=NEW.amount AND '
 "o.site_id=NEW.site_id AND o.product_kind IN ('hourly','daily') AND ((o.payment_mode='demo' AND "
 "NEW.method='demo') OR (o.payment_mode='manual' AND NEW.method IN ('cash','transfer')))) THEN RAISE "
 "EXCEPTION 'prepaid payment source or scope invalid' USING ERRCODE='23514'; END IF;\n"
 '    RETURN NEW;\n'
 'END; $$ LANGUAGE plpgsql;\n'
 'CREATE TRIGGER trg_payment_prepaid_source BEFORE INSERT ON payments FOR EACH ROW EXECUTE FUNCTION '
 'trg_payment_prepaid_source_fn();\n'
 '\n'
 'CREATE OR REPLACE FUNCTION trg_parking_slots_hold_operational_fn() RETURNS trigger AS $$\n'
 'BEGIN\n'
 '    \n'
 '    IF (NEW.is_active IS FALSE AND OLD.is_active IS TRUE OR NEW.zone_id IS DISTINCT FROM OLD.zone_id OR '
 'NEW.vehicle_type_id IS DISTINCT FROM OLD.vehicle_type_id) AND EXISTS (SELECT 1 FROM parking_capacity_holds '
 "h WHERE h.slot_id IN (SELECT OLD.id) AND h.status='held' AND h.expires_at>(clock_timestamp() AT TIME ZONE "
 "'Asia/Ho_Chi_Minh')) THEN RAISE EXCEPTION 'cannot disable inventory with payment holds' USING "
 "ERRCODE='23514'; END IF;\n"
 '    RETURN NEW;\n'
 'END; $$ LANGUAGE plpgsql;\n'
 'CREATE TRIGGER trg_parking_slots_hold_operational BEFORE UPDATE ON parking_slots FOR EACH ROW EXECUTE '
 'FUNCTION trg_parking_slots_hold_operational_fn();\n'
 '\n'
 'CREATE OR REPLACE FUNCTION trg_zones_hold_operational_fn() RETURNS trigger AS $$\n'
 'BEGIN\n'
 '    \n'
 '    IF (NEW.is_active IS FALSE AND OLD.is_active IS TRUE OR NEW.site_id IS DISTINCT FROM OLD.site_id) AND '
 'EXISTS (SELECT 1 FROM parking_capacity_holds h WHERE h.slot_id IN (SELECT id FROM parking_slots WHERE '
 "zone_id=OLD.id) AND h.status='held' AND h.expires_at>(clock_timestamp() AT TIME ZONE 'Asia/Ho_Chi_Minh')) "
 "THEN RAISE EXCEPTION 'cannot disable inventory with payment holds' USING ERRCODE='23514'; END IF;\n"
 '    RETURN NEW;\n'
 'END; $$ LANGUAGE plpgsql;\n'
 'CREATE TRIGGER trg_zones_hold_operational BEFORE UPDATE ON zones FOR EACH ROW EXECUTE FUNCTION '
 'trg_zones_hold_operational_fn();\n'
 '\n'
 'CREATE OR REPLACE FUNCTION trg_vehicle_types_hold_operational_fn() RETURNS trigger AS $$\n'
 'BEGIN\n'
 '    \n'
 '    IF (NEW.is_active IS FALSE AND OLD.is_active IS TRUE) AND EXISTS (SELECT 1 FROM parking_capacity_holds '
 "h WHERE h.slot_id IN (SELECT id FROM parking_slots WHERE vehicle_type_id=OLD.id) AND h.status='held' AND "
 "h.expires_at>(clock_timestamp() AT TIME ZONE 'Asia/Ho_Chi_Minh')) THEN RAISE EXCEPTION 'cannot disable "
 "inventory with payment holds' USING ERRCODE='23514'; END IF;\n"
 '    RETURN NEW;\n'
 'END; $$ LANGUAGE plpgsql;\n'
 'CREATE TRIGGER trg_vehicle_types_hold_operational BEFORE UPDATE ON vehicle_types FOR EACH ROW EXECUTE '
 'FUNCTION trg_vehicle_types_hold_operational_fn();\n'
 '\n'
 'CREATE OR REPLACE FUNCTION trg_parking_sites_hold_operational_fn() RETURNS trigger AS $$\n'
 'BEGIN\n'
 '    \n'
 '    IF (NEW.is_active IS FALSE AND OLD.is_active IS TRUE) AND EXISTS (SELECT 1 FROM parking_capacity_holds '
 'h WHERE h.slot_id IN (SELECT s.id FROM parking_slots s JOIN zones z ON z.id=s.zone_id WHERE '
 "z.site_id=OLD.id) AND h.status='held' AND h.expires_at>(clock_timestamp() AT TIME ZONE "
 "'Asia/Ho_Chi_Minh')) THEN RAISE EXCEPTION 'cannot disable inventory with payment holds' USING "
 "ERRCODE='23514'; END IF;\n"
 '    RETURN NEW;\n'
 'END; $$ LANGUAGE plpgsql;\n'
 'CREATE TRIGGER trg_parking_sites_hold_operational BEFORE UPDATE ON parking_sites FOR EACH ROW EXECUTE '
 'FUNCTION trg_parking_sites_hold_operational_fn();\n')


def upgrade():
    for statement in UPGRADE_SQL:
        op.execute(statement)


def downgrade():
    raise RuntimeError("Retain prepaid rights and receipts; use a prepaid-window-v1-compatible application or a forward fix.")
