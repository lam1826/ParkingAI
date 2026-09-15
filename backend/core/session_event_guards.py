"""Database backstops for append-only parking exception evidence."""

SESSION_EVENT_SQLITE_GUARDS = {
    "trg_session_event_immutable_update": "CREATE TRIGGER IF NOT EXISTS trg_session_event_immutable_update BEFORE UPDATE ON parking_session_events BEGIN SELECT RAISE(ABORT, 'parking exception event is immutable'); END",
    "trg_session_event_immutable_delete": "CREATE TRIGGER IF NOT EXISTS trg_session_event_immutable_delete BEFORE DELETE ON parking_session_events BEGIN SELECT RAISE(ABORT, 'parking exception event is immutable'); END",
    "trg_session_event_immutable_replace": "CREATE TRIGGER IF NOT EXISTS trg_session_event_immutable_replace BEFORE INSERT ON parking_session_events WHEN EXISTS (SELECT 1 FROM parking_session_events WHERE id=NEW.id OR (session_id=NEW.session_id AND request_id=NEW.request_id)) BEGIN SELECT RAISE(ABORT, 'parking exception event is immutable'); END",
    "trg_session_event_source": "CREATE TRIGGER IF NOT EXISTS trg_session_event_source BEFORE INSERT ON parking_session_events WHEN NOT EXISTS (SELECT 1 FROM parking_sessions s LEFT JOIN parking_slots p ON p.id=s.parking_slot_id LEFT JOIN zones z ON z.id=p.zone_id WHERE s.id=NEW.session_id AND z.site_id IS NEW.site_id AND ((NEW.action='lost_ticket' AND s.status='active') OR (NEW.action IN ('cancelled','plate_corrected') AND s.status='cancelled'))) BEGIN SELECT RAISE(ABORT, 'parking exception source or scope invalid'); END",
    "trg_session_event_session_delete": "CREATE TRIGGER IF NOT EXISTS trg_session_event_session_delete BEFORE DELETE ON parking_sessions WHEN EXISTS (SELECT 1 FROM parking_session_events e WHERE e.session_id=OLD.id OR e.replacement_session_id=OLD.id) BEGIN SELECT RAISE(ABORT, 'parking exception history cannot be deleted'); END",
    "trg_session_event_session_replace": "CREATE TRIGGER IF NOT EXISTS trg_session_event_session_replace BEFORE INSERT ON parking_sessions WHEN EXISTS (SELECT 1 FROM parking_session_events e WHERE e.session_id=NEW.id OR e.replacement_session_id=NEW.id) BEGIN SELECT RAISE(ABORT, 'parking exception history cannot be replaced'); END",
    "trg_session_event_replacement": "CREATE TRIGGER IF NOT EXISTS trg_session_event_replacement BEFORE INSERT ON parking_session_events WHEN NEW.action='plate_corrected' AND NOT EXISTS (SELECT 1 FROM parking_sessions s JOIN parking_sessions r ON r.id=NEW.replacement_session_id JOIN vehicles sv ON sv.id=s.vehicle_id JOIN vehicles rv ON rv.id=r.vehicle_id WHERE s.id=NEW.session_id AND s.status='cancelled' AND r.status='active' AND s.vehicle_id!=r.vehicle_id AND sv.vehicle_type_id=rv.vehicle_type_id AND s.monthly_pass_id IS NULL AND r.monthly_pass_id IS NULL AND s.parking_slot_id IS r.parking_slot_id AND s.check_in_time=r.check_in_time AND s.staff_in_id=r.staff_in_id AND s.billing_policy_version='entry-v1' AND r.billing_policy_version=s.billing_policy_version AND r.rate_config_id=s.rate_config_id AND r.rate_ticket_type=s.rate_ticket_type AND r.rate_unit_price=s.rate_unit_price AND r.rate_effective_date=s.rate_effective_date) BEGIN SELECT RAISE(ABORT, 'parking replacement must preserve admission and rate'); END",
}

SESSION_EVENT_POSTGRES_GUARD_SQL = """
CREATE OR REPLACE FUNCTION parking_session_event_guard() RETURNS trigger AS $$
BEGIN
    IF TG_TABLE_NAME = 'parking_sessions' THEN
        IF EXISTS (SELECT 1 FROM parking_session_events e WHERE e.session_id=OLD.id OR e.replacement_session_id=OLD.id) THEN
            RAISE EXCEPTION 'parking exception history cannot be deleted' USING ERRCODE = '23514';
        END IF;
        RETURN OLD;
    END IF;
    IF TG_OP != 'INSERT' THEN
        RAISE EXCEPTION 'parking exception event is immutable' USING ERRCODE = '23514';
    END IF;
    IF NOT EXISTS (SELECT 1 FROM parking_sessions s LEFT JOIN parking_slots p ON p.id=s.parking_slot_id
        LEFT JOIN zones z ON z.id=p.zone_id WHERE s.id=NEW.session_id AND z.site_id IS NOT DISTINCT FROM NEW.site_id
        AND ((NEW.action='lost_ticket' AND s.status='active') OR (NEW.action IN ('cancelled','plate_corrected') AND s.status='cancelled'))) THEN
        RAISE EXCEPTION 'parking exception source or scope invalid' USING ERRCODE = '23514';
    END IF;
    IF NEW.action='plate_corrected' AND NOT EXISTS (SELECT 1 FROM parking_sessions s
        JOIN parking_sessions r ON r.id=NEW.replacement_session_id JOIN vehicles sv ON sv.id=s.vehicle_id
        JOIN vehicles rv ON rv.id=r.vehicle_id WHERE s.id=NEW.session_id AND s.status='cancelled' AND r.status='active'
        AND s.vehicle_id!=r.vehicle_id AND sv.vehicle_type_id=rv.vehicle_type_id
        AND s.monthly_pass_id IS NULL AND r.monthly_pass_id IS NULL
        AND s.parking_slot_id IS NOT DISTINCT FROM r.parking_slot_id AND s.check_in_time=r.check_in_time
        AND s.staff_in_id=r.staff_in_id AND s.billing_policy_version='entry-v1'
        AND r.billing_policy_version=s.billing_policy_version AND r.rate_config_id=s.rate_config_id
        AND r.rate_ticket_type=s.rate_ticket_type AND r.rate_unit_price=s.rate_unit_price
        AND r.rate_effective_date=s.rate_effective_date) THEN
        RAISE EXCEPTION 'parking replacement must preserve admission and rate' USING ERRCODE = '23514';
    END IF;
    RETURN NEW;
END; $$ LANGUAGE plpgsql;
CREATE TRIGGER trg_session_event_guard BEFORE INSERT OR UPDATE OR DELETE ON parking_session_events
FOR EACH ROW EXECUTE FUNCTION parking_session_event_guard();
CREATE TRIGGER trg_session_event_session_delete BEFORE DELETE ON parking_sessions
FOR EACH ROW EXECUTE FUNCTION parking_session_event_guard();
"""
