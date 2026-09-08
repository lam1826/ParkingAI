"""Customer portal, demo ledger, parking sites/bookings and human-reviewed vision.

Revision ID: 20260907_02
Revises: 20260907_01

Frozen DDL: this revision never imports mutable application models. Historical
customer authority and camera observations are not inferred. Application rollback
retains the new schema and ledger; downgrade is intentionally non-destructive.
"""
from alembic import op
import sqlalchemy as sa

revision = "20260907_02"
down_revision = "20260907_01"
branch_labels = None
depends_on = None

EXPANSION_TABLE_SQL = ('CREATE TABLE parking_sites (\n'
 '\tid SERIAL NOT NULL, \n'
 '\tname VARCHAR(100) NOT NULL, \n'
 '\taddress VARCHAR(250) NOT NULL, \n'
 '\tis_active BOOLEAN NOT NULL, \n'
 '\tcreated_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, \n'
 '\tPRIMARY KEY (id), \n'
 '\tUNIQUE (name)\n'
 ')',
 'CREATE TABLE organizations (\n'
 '\tid SERIAL NOT NULL, \n'
 '\tsite_id INTEGER NOT NULL, \n'
 '\tname VARCHAR(150) NOT NULL, \n'
 '\tis_active BOOLEAN NOT NULL, \n'
 '\tcreated_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, \n'
 '\tPRIMARY KEY (id), \n'
 '\tFOREIGN KEY(site_id) REFERENCES parking_sites (id)\n'
 ')',
 'CREATE TABLE portal_notifications (\n'
 '\tid VARCHAR(36) NOT NULL, \n'
 '\tcustomer_id INTEGER NOT NULL, \n'
 '\tevent_key VARCHAR(128) NOT NULL, \n'
 '\tmessage VARCHAR(500) NOT NULL, \n'
 '\tcreated_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, \n'
 '\tread_at TIMESTAMP WITHOUT TIME ZONE, \n'
 '\tPRIMARY KEY (id), \n'
 '\tFOREIGN KEY(customer_id) REFERENCES customers (id), \n'
 '\tUNIQUE (event_key)\n'
 ')',
 'CREATE TABLE subscription_plans (\n'
 '\tid SERIAL NOT NULL, \n'
 '\tname VARCHAR(100) NOT NULL, \n'
 '\tsite_id INTEGER, \n'
 '\tvehicle_type_id INTEGER NOT NULL, \n'
 '\tduration_days INTEGER NOT NULL, \n'
 '\tprice BIGINT NOT NULL, \n'
 '\tis_active BOOLEAN NOT NULL, \n'
 '\tPRIMARY KEY (id), \n'
 '\tCONSTRAINT ck_portal_plan_price CHECK (price > 0 AND price <= 9007199254740991), \n'
 '\tCONSTRAINT ck_portal_plan_duration CHECK (duration_days >= 1 AND duration_days <= 366), \n'
 '\tFOREIGN KEY(site_id) REFERENCES parking_sites (id), \n'
 '\tFOREIGN KEY(vehicle_type_id) REFERENCES vehicle_types (id)\n'
 ')',
 'CREATE TABLE fleet_vehicles (\n'
 '\tid SERIAL NOT NULL, \n'
 '\torganization_id INTEGER NOT NULL, \n'
 '\tvehicle_id INTEGER NOT NULL, \n'
 '\tcreated_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, \n'
 '\tPRIMARY KEY (id), \n'
 '\tCONSTRAINT uq_fleet_vehicle UNIQUE (organization_id, vehicle_id), \n'
 '\tFOREIGN KEY(organization_id) REFERENCES organizations (id), \n'
 '\tFOREIGN KEY(vehicle_id) REFERENCES vehicles (id)\n'
 ')',
 'CREATE TABLE organization_memberships (\n'
 '\tid SERIAL NOT NULL, \n'
 '\torganization_id INTEGER NOT NULL, \n'
 '\tuser_id INTEGER NOT NULL, \n'
 '\tPRIMARY KEY (id), \n'
 '\tCONSTRAINT uq_organization_member UNIQUE (organization_id, user_id), \n'
 '\tFOREIGN KEY(organization_id) REFERENCES organizations (id), \n'
 '\tFOREIGN KEY(user_id) REFERENCES users (id)\n'
 ')',
 'CREATE TABLE portal_account_links (\n'
 '\tid SERIAL NOT NULL, \n'
 '\tuser_id INTEGER NOT NULL, \n'
 '\tcustomer_id INTEGER NOT NULL, \n'
 '\tverified_by_id INTEGER, \n'
 '\tverification VARCHAR(24) NOT NULL, \n'
 '\tcreated_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, \n'
 '\tPRIMARY KEY (id), \n'
 '\tUNIQUE (user_id), \n'
 '\tFOREIGN KEY(user_id) REFERENCES users (id), \n'
 '\tUNIQUE (customer_id), \n'
 '\tFOREIGN KEY(customer_id) REFERENCES customers (id), \n'
 '\tFOREIGN KEY(verified_by_id) REFERENCES users (id)\n'
 ')',
 'CREATE TABLE portal_link_requests (\n'
 '\tid VARCHAR(36) NOT NULL, \n'
 '\tuser_id INTEGER NOT NULL, \n'
 '\tphone_number VARCHAR(20) NOT NULL, \n'
 '\tnote VARCHAR(500) NOT NULL, \n'
 '\tstatus VARCHAR(12) NOT NULL, \n'
 '\treviewed_by_id INTEGER, \n'
 '\tcreated_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, \n'
 '\tPRIMARY KEY (id), \n'
 "\tCONSTRAINT ck_portal_link_state CHECK (status IN ('pending','approved','rejected')), \n"
 '\tFOREIGN KEY(user_id) REFERENCES users (id), \n'
 '\tFOREIGN KEY(reviewed_by_id) REFERENCES users (id)\n'
 ')',
 'CREATE TABLE portal_vehicle_ownerships (\n'
 '\tid SERIAL NOT NULL, \n'
 '\tcustomer_id INTEGER NOT NULL, \n'
 '\tvehicle_id INTEGER NOT NULL, \n'
 '\tapproved_by_id INTEGER NOT NULL, \n'
 '\tapproved_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, \n'
 '\tPRIMARY KEY (id), \n'
 '\tCONSTRAINT uq_portal_vehicle_owner UNIQUE (customer_id, vehicle_id), \n'
 '\tFOREIGN KEY(customer_id) REFERENCES customers (id), \n'
 '\tFOREIGN KEY(vehicle_id) REFERENCES vehicles (id), \n'
 '\tFOREIGN KEY(approved_by_id) REFERENCES users (id)\n'
 ')',
 'CREATE TABLE portal_vehicle_requests (\n'
 '\tid VARCHAR(36) NOT NULL, \n'
 '\tcustomer_id INTEGER NOT NULL, \n'
 '\tlicense_plate VARCHAR(20) NOT NULL, \n'
 '\tvehicle_type_id INTEGER NOT NULL, \n'
 '\tnote VARCHAR(500) NOT NULL, \n'
 '\tstatus VARCHAR(12) NOT NULL, \n'
 '\treviewed_by_id INTEGER, \n'
 '\tcreated_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, \n'
 '\tPRIMARY KEY (id), \n'
 "\tCONSTRAINT ck_portal_vehicle_request_state CHECK (status IN ('pending','approved','rejected')), \n"
 '\tFOREIGN KEY(customer_id) REFERENCES customers (id), \n'
 '\tFOREIGN KEY(vehicle_type_id) REFERENCES vehicle_types (id), \n'
 '\tFOREIGN KEY(reviewed_by_id) REFERENCES users (id)\n'
 ')',
 'CREATE TABLE site_memberships (\n'
 '\tid SERIAL NOT NULL, \n'
 '\tsite_id INTEGER NOT NULL, \n'
 '\tuser_id INTEGER NOT NULL, \n'
 '\trole VARCHAR(12) NOT NULL, \n'
 '\tPRIMARY KEY (id), \n'
 '\tCONSTRAINT uq_site_member UNIQUE (site_id, user_id), \n'
 "\tCONSTRAINT ck_site_member_role CHECK (role IN ('staff', 'manager')), \n"
 '\tFOREIGN KEY(site_id) REFERENCES parking_sites (id), \n'
 '\tFOREIGN KEY(user_id) REFERENCES users (id)\n'
 ')',
 'CREATE TABLE vision_cameras (\n'
 '\tid SERIAL NOT NULL, \n'
 '\tsite_id INTEGER NOT NULL, \n'
 '\tzone_id INTEGER, \n'
 '\tname VARCHAR(100) NOT NULL, \n'
 '\tdirection VARCHAR(8) NOT NULL, \n'
 '\tis_active BOOLEAN NOT NULL, \n'
 '\tretention_hours INTEGER NOT NULL, \n'
 '\tedge_token_hash VARCHAR(64), \n'
 '\tcreated_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, \n'
 '\tPRIMARY KEY (id), \n'
 "\tCONSTRAINT ck_camera_direction CHECK (direction IN ('entry','exit')), \n"
 '\tCONSTRAINT ck_camera_retention CHECK (retention_hours BETWEEN 1 AND 72), \n'
 '\tCONSTRAINT uq_camera_site_name UNIQUE (site_id, name), \n'
 '\tFOREIGN KEY(site_id) REFERENCES parking_sites (id), \n'
 '\tFOREIGN KEY(zone_id) REFERENCES zones (id)\n'
 ')',
 'CREATE TABLE guaranteed_allocations (\n'
 '\tid VARCHAR(36) NOT NULL, \n'
 '\tsite_id INTEGER NOT NULL, \n'
 '\tslot_id INTEGER NOT NULL, \n'
 '\tcustomer_id INTEGER NOT NULL, \n'
 '\tvehicle_id INTEGER NOT NULL, \n'
 '\tstart_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, \n'
 '\tend_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, \n'
 '\tstatus VARCHAR(12) NOT NULL, \n'
 '\trequest_id VARCHAR(64) NOT NULL, \n'
 '\tcreated_by_id INTEGER NOT NULL, \n'
 '\tcreated_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, \n'
 '\tPRIMARY KEY (id), \n'
 '\tCONSTRAINT ck_allocation_interval CHECK (end_at > start_at), \n'
 "\tCONSTRAINT ck_allocation_status CHECK (status IN ('active','cancelled')), \n"
 '\tFOREIGN KEY(site_id) REFERENCES parking_sites (id), \n'
 '\tFOREIGN KEY(slot_id) REFERENCES parking_slots (id), \n'
 '\tFOREIGN KEY(customer_id) REFERENCES customers (id), \n'
 '\tFOREIGN KEY(vehicle_id) REFERENCES vehicles (id), \n'
 '\tUNIQUE (request_id), \n'
 '\tFOREIGN KEY(created_by_id) REFERENCES users (id)\n'
 ')',
 'CREATE TABLE vision_observations (\n'
 '\tid VARCHAR(36) NOT NULL, \n'
 '\tcamera_id INTEGER NOT NULL, \n'
 '\tsite_id INTEGER NOT NULL, \n'
 '\tevent_id VARCHAR(36) NOT NULL, \n'
 '\timage_hash VARCHAR(64) NOT NULL, \n'
 '\timage_bytes BYTEA NOT NULL, \n'
 '\timage_width INTEGER NOT NULL, \n'
 '\timage_height INTEGER NOT NULL, \n'
 '\tobserved_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, \n'
 '\tcaptured_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, \n'
 '\texpires_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, \n'
 '\tocr_status VARCHAR(20) NOT NULL, \n'
 '\tsuggested_plate VARCHAR(20), \n'
 '\tconfidence FLOAT, \n'
 '\tdetections JSON NOT NULL, \n'
 '\tengine VARCHAR(50) NOT NULL, \n'
 '\treview_status VARCHAR(10) NOT NULL, \n'
 '\tconfirmed_plate VARCHAR(20), \n'
 '\treviewed_by_id INTEGER, \n'
 '\treviewed_at TIMESTAMP WITHOUT TIME ZONE, \n'
 '\tPRIMARY KEY (id), \n'
 '\tCONSTRAINT uq_vision_camera_event UNIQUE (camera_id, event_id), \n'
 "\tCONSTRAINT ck_vision_review_status CHECK (review_status IN ('pending','accepted','rejected')), \n"
 '\tFOREIGN KEY(camera_id) REFERENCES vision_cameras (id), \n'
 '\tFOREIGN KEY(site_id) REFERENCES parking_sites (id), \n'
 '\tFOREIGN KEY(reviewed_by_id) REFERENCES users (id)\n'
 ')',
 'CREATE TABLE portal_orders (\n'
 '\tid VARCHAR(36) NOT NULL, \n'
 '\tuser_id INTEGER NOT NULL, \n'
 '\tcustomer_id INTEGER NOT NULL, \n'
 '\tvehicle_id INTEGER NOT NULL, \n'
 '\tplan_id INTEGER NOT NULL, \n'
 '\tsite_id INTEGER NOT NULL, \n'
 '\tcard_id INTEGER, \n'
 '\tamount BIGINT NOT NULL, \n'
 '\tstart_date DATE NOT NULL, \n'
 '\tend_date DATE NOT NULL, \n'
 '\tpayment_mode VARCHAR(8) NOT NULL, \n'
 '\tstatus VARCHAR(12) NOT NULL, \n'
 '\tidempotency_key VARCHAR(64) NOT NULL, \n'
 '\tdemo_token VARCHAR(64), \n'
 '\texpires_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, \n'
 '\tcreated_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, \n'
 '\tmonthly_pass_id INTEGER, \n'
 '\treceipt_id VARCHAR(36), \n'
 '\treview_reason VARCHAR(100), \n'
 '\tPRIMARY KEY (id), \n'
 '\tCONSTRAINT uq_portal_order_request UNIQUE (user_id, idempotency_key), \n'
 '\tCONSTRAINT ck_portal_order_amount CHECK (amount > 0 AND amount <= 9007199254740991), \n'
 '\tCONSTRAINT ck_portal_order_dates CHECK (end_date >= start_date), \n'
 "\tCONSTRAINT ck_portal_order_mode CHECK (payment_mode IN ('demo','manual')), \n"
 '\tCONSTRAINT ck_portal_order_state CHECK (status IN '
 "('pending','fulfilled','failed','cancelled','expired','review','refunded')), \n"
 "\tCONSTRAINT ck_portal_order_fulfilled CHECK (status NOT IN ('fulfilled','refunded') OR (monthly_pass_id "
 'IS NOT NULL AND receipt_id IS NOT NULL)), \n'
 '\tFOREIGN KEY(user_id) REFERENCES users (id), \n'
 '\tFOREIGN KEY(customer_id) REFERENCES customers (id), \n'
 '\tFOREIGN KEY(vehicle_id) REFERENCES vehicles (id), \n'
 '\tFOREIGN KEY(plan_id) REFERENCES subscription_plans (id), \n'
 '\tFOREIGN KEY(site_id) REFERENCES parking_sites (id), \n'
 '\tFOREIGN KEY(card_id) REFERENCES parking_cards (id), \n'
 '\tUNIQUE (monthly_pass_id), \n'
 '\tFOREIGN KEY(monthly_pass_id) REFERENCES monthly_passes (id), \n'
 '\tUNIQUE (receipt_id), \n'
 '\tFOREIGN KEY(receipt_id) REFERENCES payments (id)\n'
 ')',
 'CREATE TABLE parking_reservations (\n'
 '\tid VARCHAR(36) NOT NULL, \n'
 '\tsite_id INTEGER NOT NULL, \n'
 '\tslot_id INTEGER NOT NULL, \n'
 '\tcustomer_id INTEGER NOT NULL, \n'
 '\tvehicle_id INTEGER NOT NULL, \n'
 '\tstart_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, \n'
 '\tend_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, \n'
 '\tarrival_deadline TIMESTAMP WITHOUT TIME ZONE NOT NULL, \n'
 '\tstatus VARCHAR(12) NOT NULL, \n'
 '\trequest_id VARCHAR(64) NOT NULL, \n'
 '\tcreated_by_id INTEGER NOT NULL, \n'
 '\tsession_id VARCHAR(36), \n'
 '\tcreated_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, \n'
 '\tPRIMARY KEY (id), \n'
 '\tCONSTRAINT ck_reservation_interval CHECK (end_at > start_at), \n'
 '\tCONSTRAINT ck_reservation_arrival CHECK (arrival_deadline >= start_at AND arrival_deadline <= end_at), \n'
 "\tCONSTRAINT ck_reservation_status CHECK (status IN ('confirmed','arrived','cancelled','expired')), \n"
 '\tFOREIGN KEY(site_id) REFERENCES parking_sites (id), \n'
 '\tFOREIGN KEY(slot_id) REFERENCES parking_slots (id), \n'
 '\tFOREIGN KEY(customer_id) REFERENCES customers (id), \n'
 '\tFOREIGN KEY(vehicle_id) REFERENCES vehicles (id), \n'
 '\tUNIQUE (request_id), \n'
 '\tFOREIGN KEY(created_by_id) REFERENCES users (id), \n'
 '\tUNIQUE (session_id), \n'
 '\tFOREIGN KEY(session_id) REFERENCES parking_sessions (id)\n'
 ')',
 'CREATE TABLE portal_payment_events (\n'
 '\tid VARCHAR(36) NOT NULL, \n'
 '\torder_id VARCHAR(36) NOT NULL, \n'
 '\tprovider VARCHAR(12) NOT NULL, \n'
 '\treference VARCHAR(64) NOT NULL, \n'
 '\toutcome VARCHAR(12) NOT NULL, \n'
 '\tstatus VARCHAR(12) NOT NULL, \n'
 '\tamount BIGINT NOT NULL, \n'
 '\treceived_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, \n'
 '\tattempts INTEGER NOT NULL, \n'
 '\tnext_attempt_at TIMESTAMP WITHOUT TIME ZONE, \n'
 '\terror_code VARCHAR(100), \n'
 '\tPRIMARY KEY (id), \n'
 '\tCONSTRAINT uq_portal_provider_reference UNIQUE (provider, reference), \n'
 "\tCONSTRAINT ck_portal_event_outcome CHECK (outcome IN ('success','failed','cancelled')), \n"
 "\tCONSTRAINT ck_portal_event_state CHECK (status IN ('received','processed','review')), \n"
 '\tFOREIGN KEY(order_id) REFERENCES portal_orders (id)\n'
 ')',
 'CREATE TABLE portal_refund_requests (\n'
 '\tid VARCHAR(36) NOT NULL, \n'
 '\torder_id VARCHAR(36) NOT NULL, \n'
 '\tcustomer_id INTEGER NOT NULL, \n'
 '\treason VARCHAR(500) NOT NULL, \n'
 '\tstatus VARCHAR(12) NOT NULL, \n'
 '\tnote VARCHAR(500) NOT NULL, \n'
 '\treviewed_by_id INTEGER, \n'
 '\trefund_payment_id VARCHAR(36), \n'
 '\tcreated_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, \n'
 '\tPRIMARY KEY (id), \n'
 "\tCONSTRAINT ck_portal_refund_state CHECK (status IN ('pending','approved','rejected')), \n"
 '\tUNIQUE (order_id), \n'
 '\tFOREIGN KEY(order_id) REFERENCES portal_orders (id), \n'
 '\tFOREIGN KEY(customer_id) REFERENCES customers (id), \n'
 '\tFOREIGN KEY(reviewed_by_id) REFERENCES users (id), \n'
 '\tUNIQUE (refund_payment_id), \n'
 '\tFOREIGN KEY(refund_payment_id) REFERENCES payments (id)\n'
 ')',
 'CREATE TABLE portal_session_grants (\n'
 '\tparking_session_id VARCHAR(36) NOT NULL, \n'
 '\tcustomer_id INTEGER NOT NULL, \n'
 '\tPRIMARY KEY (parking_session_id), \n'
 '\tFOREIGN KEY(parking_session_id) REFERENCES parking_sessions (id), \n'
 '\tFOREIGN KEY(customer_id) REFERENCES customers (id)\n'
 ')',
 'CREATE TABLE site_waitlist (\n'
 '\tid VARCHAR(36) NOT NULL, \n'
 '\tsite_id INTEGER NOT NULL, \n'
 '\tcustomer_id INTEGER NOT NULL, \n'
 '\tvehicle_id INTEGER NOT NULL, \n'
 '\tstart_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, \n'
 '\tend_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, \n'
 '\tstatus VARCHAR(12) NOT NULL, \n'
 '\trequest_id VARCHAR(64) NOT NULL, \n'
 '\treservation_id VARCHAR(36), \n'
 '\tcreated_by_id INTEGER NOT NULL, \n'
 '\tcreated_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, \n'
 '\tPRIMARY KEY (id), \n'
 '\tCONSTRAINT ck_waitlist_interval CHECK (end_at > start_at), \n'
 "\tCONSTRAINT ck_waitlist_status CHECK (status IN ('waiting','offered','cancelled')), \n"
 '\tFOREIGN KEY(site_id) REFERENCES parking_sites (id), \n'
 '\tFOREIGN KEY(customer_id) REFERENCES customers (id), \n'
 '\tFOREIGN KEY(vehicle_id) REFERENCES vehicles (id), \n'
 '\tUNIQUE (request_id), \n'
 '\tUNIQUE (reservation_id), \n'
 '\tFOREIGN KEY(reservation_id) REFERENCES parking_reservations (id), \n'
 '\tFOREIGN KEY(created_by_id) REFERENCES users (id)\n'
 ')')

EXPANSION_INDEX_SQL = ('CREATE INDEX ix_organizations_site_id ON organizations (site_id)',
 'CREATE INDEX ix_portal_notifications_customer_id ON portal_notifications (customer_id)',
 'CREATE INDEX ix_subscription_plans_site_id ON subscription_plans (site_id)',
 'CREATE INDEX ix_fleet_vehicles_organization_id ON fleet_vehicles (organization_id)',
 'CREATE INDEX ix_organization_memberships_organization_id ON organization_memberships (organization_id)',
 'CREATE INDEX ix_portal_link_requests_user_id ON portal_link_requests (user_id)',
 'CREATE INDEX ix_portal_vehicle_ownerships_customer_id ON portal_vehicle_ownerships (customer_id)',
 'CREATE INDEX ix_portal_vehicle_ownerships_vehicle_id ON portal_vehicle_ownerships (vehicle_id)',
 'CREATE INDEX ix_portal_vehicle_requests_customer_id ON portal_vehicle_requests (customer_id)',
 'CREATE INDEX ix_site_memberships_site_id ON site_memberships (site_id)',
 'CREATE INDEX ix_site_memberships_user_id ON site_memberships (user_id)',
 'CREATE INDEX ix_vision_cameras_site_id ON vision_cameras (site_id)',
 'CREATE INDEX ix_allocation_slot_interval ON guaranteed_allocations (slot_id, start_at, end_at)',
 'CREATE INDEX ix_guaranteed_allocations_site_id ON guaranteed_allocations (site_id)',
 'CREATE INDEX ix_vision_observations_camera_id ON vision_observations (camera_id)',
 'CREATE INDEX ix_vision_observations_expires_at ON vision_observations (expires_at)',
 'CREATE INDEX ix_vision_observations_site_id ON vision_observations (site_id)',
 'CREATE INDEX ix_portal_order_due ON portal_orders (status, expires_at)',
 'CREATE INDEX ix_portal_orders_customer_id ON portal_orders (customer_id)',
 'CREATE INDEX ix_portal_orders_site_id ON portal_orders (site_id)',
 'CREATE INDEX ix_portal_orders_user_id ON portal_orders (user_id)',
 'CREATE INDEX ix_portal_orders_vehicle_id ON portal_orders (vehicle_id)',
 'CREATE INDEX ix_parking_reservations_customer_id ON parking_reservations (customer_id)',
 'CREATE INDEX ix_parking_reservations_site_id ON parking_reservations (site_id)',
 'CREATE INDEX ix_parking_reservations_vehicle_id ON parking_reservations (vehicle_id)',
 'CREATE INDEX ix_reservation_slot_interval ON parking_reservations (slot_id, start_at, end_at)',
 'CREATE INDEX ix_portal_payment_events_order_id ON portal_payment_events (order_id)',
 'CREATE INDEX ix_portal_refund_requests_customer_id ON portal_refund_requests (customer_id)',
 'CREATE INDEX ix_portal_session_grants_customer_id ON portal_session_grants (customer_id)',
 'CREATE INDEX ix_site_waitlist_site_id ON site_waitlist (site_id)',
 'CREATE INDEX ix_zones_site_id ON zones (site_id)')

SITE_SQLITE_GUARDS = {'trg_guaranteed_allocations_insert_guard': 'CREATE TRIGGER IF NOT EXISTS '
                                            'trg_guaranteed_allocations_insert_guard BEFORE INSERT ON '
                                            "guaranteed_allocations WHEN NEW.status!='active' OR NOT EXISTS "
                                            '(SELECT 1 FROM parking_slots s JOIN zones z ON z.id=s.zone_id '
                                            'JOIN vehicles v ON v.id=NEW.vehicle_id JOIN parking_sites p ON '
                                            'p.id=z.site_id WHERE s.id=NEW.slot_id AND z.site_id=NEW.site_id '
                                            'AND v.customer_id=NEW.customer_id AND '
                                            's.vehicle_type_id=v.vehicle_type_id AND s.is_active=1 AND '
                                            'z.is_active=1 AND p.is_active=1) OR EXISTS (SELECT 1 FROM '
                                            'parking_slots WHERE id=NEW.slot_id AND is_occupied=1) OR EXISTS '
                                            '(SELECT 1 FROM parking_reservations r WHERE '
                                            "r.slot_id=NEW.slot_id AND r.status IN ('confirmed','arrived') "
                                            'AND r.start_at<NEW.end_at AND r.end_at>NEW.start_at) OR EXISTS '
                                            '(SELECT 1 FROM guaranteed_allocations a WHERE '
                                            "a.slot_id=NEW.slot_id AND a.status='active' AND "
                                            'a.start_at<NEW.end_at AND a.end_at>NEW.start_at) BEGIN SELECT '
                                            "RAISE(ABORT, 'reservation capacity or source invalid'); END",
 'trg_guaranteed_allocations_update_guard': 'CREATE TRIGGER IF NOT EXISTS '
                                            'trg_guaranteed_allocations_update_guard BEFORE UPDATE ON '
                                            'guaranteed_allocations WHEN NEW.site_id IS NOT OLD.site_id OR '
                                            'NEW.slot_id IS NOT OLD.slot_id OR NEW.customer_id IS NOT '
                                            'OLD.customer_id OR NEW.vehicle_id IS NOT OLD.vehicle_id OR '
                                            'NEW.start_at IS NOT OLD.start_at OR NEW.end_at IS NOT '
                                            'OLD.end_at OR NEW.request_id IS NOT OLD.request_id OR '
                                            'NEW.created_by_id IS NOT OLD.created_by_id OR NEW.created_at IS '
                                            "NOT OLD.created_at OR (OLD.status!='active' AND "
                                            "NEW.status!=OLD.status) BEGIN SELECT RAISE(ABORT, 'reservation "
                                            "identity or state invalid'); END",
 'trg_parking_reservations_insert_guard': 'CREATE TRIGGER IF NOT EXISTS '
                                          'trg_parking_reservations_insert_guard BEFORE INSERT ON '
                                          "parking_reservations WHEN NEW.status!='confirmed' OR NOT EXISTS "
                                          '(SELECT 1 FROM parking_slots s JOIN zones z ON z.id=s.zone_id '
                                          'JOIN vehicles v ON v.id=NEW.vehicle_id JOIN parking_sites p ON '
                                          'p.id=z.site_id WHERE s.id=NEW.slot_id AND z.site_id=NEW.site_id '
                                          'AND v.customer_id=NEW.customer_id AND '
                                          's.vehicle_type_id=v.vehicle_type_id AND s.is_active=1 AND '
                                          'z.is_active=1 AND p.is_active=1) OR EXISTS (SELECT 1 FROM '
                                          'parking_slots WHERE id=NEW.slot_id AND is_occupied=1) OR EXISTS '
                                          '(SELECT 1 FROM parking_reservations r WHERE r.slot_id=NEW.slot_id '
                                          "AND r.status IN ('confirmed','arrived') AND r.start_at<NEW.end_at "
                                          'AND r.end_at>NEW.start_at) OR EXISTS (SELECT 1 FROM '
                                          'guaranteed_allocations a WHERE a.slot_id=NEW.slot_id AND '
                                          "a.status='active' AND a.start_at<NEW.end_at AND "
                                          'a.end_at>NEW.start_at AND NOT (a.vehicle_id=NEW.vehicle_id AND '
                                          'a.start_at<=NEW.start_at AND a.end_at>=NEW.end_at)) BEGIN SELECT '
                                          "RAISE(ABORT, 'reservation capacity or source invalid'); END",
 'trg_parking_reservations_update_guard': 'CREATE TRIGGER IF NOT EXISTS '
                                          'trg_parking_reservations_update_guard BEFORE UPDATE ON '
                                          'parking_reservations WHEN NEW.site_id IS NOT OLD.site_id OR '
                                          'NEW.slot_id IS NOT OLD.slot_id OR NEW.customer_id IS NOT '
                                          'OLD.customer_id OR NEW.vehicle_id IS NOT OLD.vehicle_id OR '
                                          'NEW.start_at IS NOT OLD.start_at OR NEW.end_at IS NOT OLD.end_at '
                                          'OR NEW.request_id IS NOT OLD.request_id OR NEW.created_by_id IS '
                                          'NOT OLD.created_by_id OR NEW.created_at IS NOT OLD.created_at OR '
                                          'NEW.arrival_deadline IS NOT OLD.arrival_deadline OR '
                                          "(OLD.status!='confirmed' AND NEW.status!=OLD.status) OR "
                                          '(NEW.session_id IS NOT OLD.session_id AND '
                                          "(OLD.status!='confirmed' OR NEW.status!='arrived')) OR "
                                          "(NEW.status='arrived' AND NOT EXISTS (SELECT 1 FROM "
                                          'parking_sessions s WHERE s.id=NEW.session_id AND '
                                          's.vehicle_id=NEW.vehicle_id AND s.parking_slot_id=NEW.slot_id AND '
                                          's.check_in_time>=NEW.start_at AND '
                                          's.check_in_time<NEW.arrival_deadline)) BEGIN SELECT RAISE(ABORT, '
                                          "'reservation identity or state invalid'); END",
 'trg_slot_commitment_guard': 'CREATE TRIGGER IF NOT EXISTS trg_slot_commitment_guard BEFORE UPDATE ON '
                              'parking_slots WHEN (NEW.zone_id IS NOT OLD.zone_id OR NEW.vehicle_type_id IS '
                              'NOT OLD.vehicle_type_id OR NEW.is_active=0) AND (EXISTS (SELECT 1 FROM '
                              'parking_reservations r WHERE r.slot_id=OLD.id AND r.status IN '
                              "('confirmed','arrived') AND r.end_at>datetime('now','+7 hours')) OR EXISTS "
                              '(SELECT 1 FROM guaranteed_allocations a WHERE a.slot_id=OLD.id AND '
                              "a.status='active' AND a.end_at>datetime('now','+7 hours'))) BEGIN SELECT "
                              "RAISE(ABORT, 'slot has parking commitments'); END",
 'trg_zone_site_immutable': 'CREATE TRIGGER IF NOT EXISTS trg_zone_site_immutable BEFORE UPDATE OF site_id '
                            'ON zones WHEN OLD.site_id IS NOT NULL AND NEW.site_id IS NOT OLD.site_id BEGIN '
                            "SELECT RAISE(ABORT, 'zone site identity is immutable'); END"}

SITE_POSTGRES_GUARD_SQL = """
CREATE OR REPLACE FUNCTION parking_commitment_guard() RETURNS trigger AS $$
DECLARE expected text;
BEGIN
    expected := CASE WHEN TG_TABLE_NAME='parking_reservations' THEN 'confirmed' ELSE 'active' END;
    IF TG_OP='UPDATE' THEN
        IF ROW(NEW.site_id,NEW.slot_id,NEW.customer_id,NEW.vehicle_id,NEW.start_at,NEW.end_at,NEW.request_id,NEW.created_by_id,NEW.created_at)
           IS DISTINCT FROM ROW(OLD.site_id,OLD.slot_id,OLD.customer_id,OLD.vehicle_id,OLD.start_at,OLD.end_at,OLD.request_id,OLD.created_by_id,OLD.created_at)
           OR (OLD.status<>expected AND NEW.status<>OLD.status) THEN
            RAISE EXCEPTION 'reservation identity or state invalid' USING ERRCODE='23514';
        END IF;
        IF TG_TABLE_NAME='parking_reservations' THEN
            IF NEW.arrival_deadline IS DISTINCT FROM OLD.arrival_deadline
               OR (NEW.session_id IS DISTINCT FROM OLD.session_id AND (OLD.status<>'confirmed' OR NEW.status<>'arrived'))
               OR (NEW.status='arrived' AND NOT EXISTS (SELECT 1 FROM parking_sessions s WHERE s.id=NEW.session_id
                   AND s.vehicle_id=NEW.vehicle_id AND s.parking_slot_id=NEW.slot_id
                   AND s.check_in_time>=NEW.start_at AND s.check_in_time<NEW.arrival_deadline)) THEN
                RAISE EXCEPTION 'reservation identity or state invalid' USING ERRCODE='23514';
            END IF;
        END IF;
        RETURN NEW;
    END IF;
    PERFORM id FROM parking_slots WHERE id=NEW.slot_id FOR UPDATE;
    IF NEW.status<>expected OR NOT EXISTS (SELECT 1 FROM parking_slots s JOIN zones z ON z.id=s.zone_id
        JOIN vehicles v ON v.id=NEW.vehicle_id JOIN parking_sites p ON p.id=z.site_id
        WHERE s.id=NEW.slot_id AND z.site_id=NEW.site_id AND v.customer_id=NEW.customer_id
        AND s.vehicle_type_id=v.vehicle_type_id AND s.is_active AND z.is_active AND p.is_active AND NOT s.is_occupied)
        OR EXISTS (SELECT 1 FROM parking_reservations r WHERE r.slot_id=NEW.slot_id AND r.status IN ('confirmed','arrived')
                   AND r.start_at<NEW.end_at AND r.end_at>NEW.start_at)
        OR EXISTS (SELECT 1 FROM guaranteed_allocations a WHERE a.slot_id=NEW.slot_id AND a.status='active'
                   AND a.start_at<NEW.end_at AND a.end_at>NEW.start_at AND NOT
                   (TG_TABLE_NAME='parking_reservations' AND a.vehicle_id=NEW.vehicle_id AND a.start_at<=NEW.start_at AND a.end_at>=NEW.end_at)) THEN
        RAISE EXCEPTION 'reservation capacity or source invalid' USING ERRCODE='23514';
    END IF;
    RETURN NEW;
END; $$ LANGUAGE plpgsql;
CREATE TRIGGER trg_parking_reservations_guard BEFORE INSERT OR UPDATE ON parking_reservations FOR EACH ROW EXECUTE FUNCTION parking_commitment_guard();
CREATE TRIGGER trg_guaranteed_allocations_guard BEFORE INSERT OR UPDATE ON guaranteed_allocations FOR EACH ROW EXECUTE FUNCTION parking_commitment_guard();
CREATE OR REPLACE FUNCTION parking_slot_commitment_guard() RETURNS trigger AS $$
BEGIN
    IF (NEW.zone_id IS DISTINCT FROM OLD.zone_id OR NEW.vehicle_type_id IS DISTINCT FROM OLD.vehicle_type_id OR NOT NEW.is_active)
       AND (EXISTS (SELECT 1 FROM parking_reservations r WHERE r.slot_id=OLD.id AND r.status IN ('confirmed','arrived')
                    AND r.end_at>CURRENT_TIMESTAMP AT TIME ZONE 'Asia/Ho_Chi_Minh')
            OR EXISTS (SELECT 1 FROM guaranteed_allocations a WHERE a.slot_id=OLD.id AND a.status='active'
                       AND a.end_at>CURRENT_TIMESTAMP AT TIME ZONE 'Asia/Ho_Chi_Minh')) THEN
        RAISE EXCEPTION 'slot has parking commitments' USING ERRCODE='23514';
    END IF;
    RETURN NEW;
END; $$ LANGUAGE plpgsql;
CREATE TRIGGER trg_slot_commitment_guard BEFORE UPDATE ON parking_slots FOR EACH ROW EXECUTE FUNCTION parking_slot_commitment_guard();
CREATE OR REPLACE FUNCTION parking_zone_site_guard() RETURNS trigger AS $$
BEGIN
    IF OLD.site_id IS NOT NULL AND NEW.site_id IS DISTINCT FROM OLD.site_id THEN
        RAISE EXCEPTION 'zone site identity is immutable' USING ERRCODE='23514';
    END IF;
    RETURN NEW;
END; $$ LANGUAGE plpgsql;
CREATE TRIGGER trg_zone_site_immutable BEFORE UPDATE OF site_id ON zones FOR EACH ROW EXECUTE FUNCTION parking_zone_site_guard();
"""

LEGACY_SITE_BACKFILL_SQL = """
INSERT INTO parking_sites (name,address,is_active,created_at)
VALUES ('Bãi xe mặc định','',true,CURRENT_TIMESTAMP AT TIME ZONE 'Asia/Ho_Chi_Minh');
UPDATE zones SET site_id=(SELECT id FROM parking_sites) WHERE site_id IS NULL;
INSERT INTO site_memberships (site_id,user_id,role)
SELECT s.id,u.id,r.name FROM parking_sites s CROSS JOIN users u JOIN roles r ON r.id=u.role_id
WHERE r.name IN ('staff','manager');
"""

DEMO_POSTGRES_GUARD_SQL = """
CREATE OR REPLACE FUNCTION parking_payment_demo_boundary() RETURNS trigger AS $$
BEGIN
    IF (NEW.method='demo' AND (NEW.source_type!='monthly_pass' OR NEW.shift_id IS NOT NULL
        OR (NEW.kind='receipt' AND NEW.collected_by_id IS NOT NULL)))
       OR (NEW.kind='refund' AND EXISTS (SELECT 1 FROM payments original
           WHERE original.id=NEW.original_payment_id AND ((original.method='demo') != (NEW.method='demo')))) THEN
        RAISE EXCEPTION 'demo payment cannot be mixed with real collection' USING ERRCODE='23514';
    END IF;
    RETURN NEW;
END; $$ LANGUAGE plpgsql;
CREATE TRIGGER trg_payment_demo_boundary BEFORE INSERT ON payments
FOR EACH ROW EXECUTE FUNCTION parking_payment_demo_boundary();
"""


def upgrade():
    for statement in EXPANSION_TABLE_SQL:
        op.execute(statement)
    op.add_column("zones", sa.Column("site_id", sa.Integer(), nullable=True))
    op.create_foreign_key("fk_zones_site", "zones", "parking_sites", ["site_id"], ["id"])
    for statement in EXPANSION_INDEX_SQL:
        op.execute(statement)
    op.drop_constraint("ck_payment_method", "payments", type_="check")
    op.create_check_constraint("ck_payment_method", "payments", "method IN ('cash', 'transfer', 'legacy_unknown', 'demo')")
    op.create_check_constraint("ck_payment_demo_unassigned", "payments", "method != 'demo' OR shift_id IS NULL")
    op.execute(LEGACY_SITE_BACKFILL_SQL)
    op.execute(SITE_POSTGRES_GUARD_SQL)
    op.execute(DEMO_POSTGRES_GUARD_SQL)


def downgrade():
    raise RuntimeError("Expansion data and payment history cannot be dropped automatically; roll back the application image while retaining this schema.")
