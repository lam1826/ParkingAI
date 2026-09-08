"""Site authorization and physical-space commitments, separate from paid passes."""
import uuid
from datetime import datetime

from sqlalchemy import Boolean, CheckConstraint, DDL, DateTime, ForeignKey, Index, String, UniqueConstraint, event
from sqlalchemy.orm import Mapped, mapped_column

from core.clock import business_now
from database import Base


class ParkingSite(Base):
    __tablename__ = "parking_sites"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100), unique=True)
    address: Mapped[str] = mapped_column(String(250), default="")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=business_now)


class SiteMembership(Base):
    __tablename__ = "site_memberships"
    __table_args__ = (UniqueConstraint("site_id", "user_id", name="uq_site_member"),
                      CheckConstraint("role IN ('staff', 'manager')", name="ck_site_member_role"))
    id: Mapped[int] = mapped_column(primary_key=True)
    site_id: Mapped[int] = mapped_column(ForeignKey("parking_sites.id"), index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    role: Mapped[str] = mapped_column(String(12))


class ParkingReservation(Base):
    __tablename__ = "parking_reservations"
    __table_args__ = (
        CheckConstraint("end_at > start_at", name="ck_reservation_interval"),
        CheckConstraint("arrival_deadline >= start_at AND arrival_deadline <= end_at", name="ck_reservation_arrival"),
        CheckConstraint("status IN ('confirmed','arrived','cancelled','expired')", name="ck_reservation_status"),
        Index("ix_reservation_slot_interval", "slot_id", "start_at", "end_at"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    site_id: Mapped[int] = mapped_column(ForeignKey("parking_sites.id"), index=True)
    slot_id: Mapped[int] = mapped_column(ForeignKey("parking_slots.id"))
    customer_id: Mapped[int] = mapped_column(ForeignKey("customers.id"), index=True)
    vehicle_id: Mapped[int] = mapped_column(ForeignKey("vehicles.id"), index=True)
    start_at: Mapped[datetime] = mapped_column(DateTime)
    end_at: Mapped[datetime] = mapped_column(DateTime)
    arrival_deadline: Mapped[datetime] = mapped_column(DateTime)
    status: Mapped[str] = mapped_column(String(12), default="confirmed")
    request_id: Mapped[str] = mapped_column(String(64), unique=True)
    created_by_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    session_id: Mapped[str | None] = mapped_column(ForeignKey("parking_sessions.id"), unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=business_now)


class GuaranteedAllocation(Base):
    __tablename__ = "guaranteed_allocations"
    __table_args__ = (
        CheckConstraint("end_at > start_at", name="ck_allocation_interval"),
        CheckConstraint("status IN ('active','cancelled')", name="ck_allocation_status"),
        Index("ix_allocation_slot_interval", "slot_id", "start_at", "end_at"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    site_id: Mapped[int] = mapped_column(ForeignKey("parking_sites.id"), index=True)
    slot_id: Mapped[int] = mapped_column(ForeignKey("parking_slots.id"))
    customer_id: Mapped[int] = mapped_column(ForeignKey("customers.id"))
    vehicle_id: Mapped[int] = mapped_column(ForeignKey("vehicles.id"))
    start_at: Mapped[datetime] = mapped_column(DateTime)
    end_at: Mapped[datetime] = mapped_column(DateTime)
    status: Mapped[str] = mapped_column(String(12), default="active")
    request_id: Mapped[str] = mapped_column(String(64), unique=True)
    created_by_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=business_now)


class SiteWaitlist(Base):
    __tablename__ = "site_waitlist"
    __table_args__ = (
        CheckConstraint("end_at > start_at", name="ck_waitlist_interval"),
        CheckConstraint("status IN ('waiting','offered','cancelled')", name="ck_waitlist_status"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    site_id: Mapped[int] = mapped_column(ForeignKey("parking_sites.id"), index=True)
    customer_id: Mapped[int] = mapped_column(ForeignKey("customers.id"))
    vehicle_id: Mapped[int] = mapped_column(ForeignKey("vehicles.id"))
    start_at: Mapped[datetime] = mapped_column(DateTime)
    end_at: Mapped[datetime] = mapped_column(DateTime)
    status: Mapped[str] = mapped_column(String(12), default="waiting")
    request_id: Mapped[str] = mapped_column(String(64), unique=True)
    reservation_id: Mapped[str | None] = mapped_column(ForeignKey("parking_reservations.id"), unique=True)
    created_by_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=business_now)


class Organization(Base):
    __tablename__ = "organizations"
    id: Mapped[int] = mapped_column(primary_key=True)
    site_id: Mapped[int] = mapped_column(ForeignKey("parking_sites.id"), index=True)
    name: Mapped[str] = mapped_column(String(150))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=business_now)


class OrganizationMembership(Base):
    __tablename__ = "organization_memberships"
    __table_args__ = (UniqueConstraint("organization_id", "user_id", name="uq_organization_member"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    organization_id: Mapped[int] = mapped_column(ForeignKey("organizations.id"), index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))


class FleetVehicle(Base):
    __tablename__ = "fleet_vehicles"
    __table_args__ = (UniqueConstraint("organization_id", "vehicle_id", name="uq_fleet_vehicle"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    organization_id: Mapped[int] = mapped_column(ForeignKey("organizations.id"), index=True)
    vehicle_id: Mapped[int] = mapped_column(ForeignKey("vehicles.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=business_now)


# Exported registry is also installed by the additive rollout for existing databases.
# Slot locks in the service serialize API requests; these guards preserve source,
# interval and identity invariants when data is maintained outside that service.
SITE_SQLITE_GUARDS = {}
for _table, _initial in (("parking_reservations", "confirmed"), ("guaranteed_allocations", "active")):
    _match = (
        "EXISTS (SELECT 1 FROM parking_slots s JOIN zones z ON z.id=s.zone_id "
        "JOIN vehicles v ON v.id=NEW.vehicle_id JOIN parking_sites p ON p.id=z.site_id "
        "WHERE s.id=NEW.slot_id AND z.site_id=NEW.site_id AND v.customer_id=NEW.customer_id "
        "AND s.vehicle_type_id=v.vehicle_type_id AND s.is_active=1 AND z.is_active=1 AND p.is_active=1)"
    )
    _res_conflict = ("EXISTS (SELECT 1 FROM parking_reservations r WHERE r.slot_id=NEW.slot_id "
                     "AND r.status IN ('confirmed','arrived') AND r.start_at<NEW.end_at AND r.end_at>NEW.start_at)")
    _alloc_conflict = ("EXISTS (SELECT 1 FROM guaranteed_allocations a WHERE a.slot_id=NEW.slot_id "
                       "AND a.status='active' AND a.start_at<NEW.end_at AND a.end_at>NEW.start_at")
    if _table == "parking_reservations":
        _alloc_conflict += " AND NOT (a.vehicle_id=NEW.vehicle_id AND a.start_at<=NEW.start_at AND a.end_at>=NEW.end_at)"
    _alloc_conflict += ")"
    _name = f"trg_{_table}_insert_guard"
    SITE_SQLITE_GUARDS[_name] = (
        f"CREATE TRIGGER IF NOT EXISTS {_name} BEFORE INSERT ON {_table} WHEN NEW.status!='{_initial}' "
        f"OR NOT {_match} OR EXISTS (SELECT 1 FROM parking_slots WHERE id=NEW.slot_id AND is_occupied=1) "
        f"OR {_res_conflict} OR {_alloc_conflict} BEGIN SELECT RAISE(ABORT, 'reservation capacity or source invalid'); END"
    )
    _immutable = ["site_id", "slot_id", "customer_id", "vehicle_id", "start_at", "end_at", "request_id", "created_by_id", "created_at"]
    if _table == "parking_reservations":
        _immutable.append("arrival_deadline")
    _changes = " OR ".join(f"NEW.{name} IS NOT OLD.{name}" for name in _immutable)
    _changes += f" OR (OLD.status!='{_initial}' AND NEW.status!=OLD.status)"
    if _table == "parking_reservations":
        _changes += (
            " OR (NEW.session_id IS NOT OLD.session_id AND (OLD.status!='confirmed' OR NEW.status!='arrived'))"
            " OR (NEW.status='arrived' AND NOT EXISTS (SELECT 1 FROM parking_sessions s WHERE s.id=NEW.session_id "
            "AND s.vehicle_id=NEW.vehicle_id AND s.parking_slot_id=NEW.slot_id AND s.check_in_time>=NEW.start_at "
            "AND s.check_in_time<NEW.arrival_deadline))"
        )
    _name = f"trg_{_table}_update_guard"
    SITE_SQLITE_GUARDS[_name] = f"CREATE TRIGGER IF NOT EXISTS {_name} BEFORE UPDATE ON {_table} WHEN {_changes} BEGIN SELECT RAISE(ABORT, 'reservation identity or state invalid'); END"

_future = ("EXISTS (SELECT 1 FROM parking_reservations r WHERE r.slot_id=OLD.id AND r.status IN ('confirmed','arrived') "
           "AND r.end_at>datetime('now','+7 hours')) OR EXISTS (SELECT 1 FROM guaranteed_allocations a WHERE a.slot_id=OLD.id "
           "AND a.status='active' AND a.end_at>datetime('now','+7 hours'))")
SITE_SQLITE_GUARDS["trg_slot_commitment_guard"] = (
    "CREATE TRIGGER IF NOT EXISTS trg_slot_commitment_guard BEFORE UPDATE ON parking_slots "
    "WHEN (NEW.zone_id IS NOT OLD.zone_id OR NEW.vehicle_type_id IS NOT OLD.vehicle_type_id OR NEW.is_active=0) "
    f"AND ({_future}) BEGIN SELECT RAISE(ABORT, 'slot has parking commitments'); END"
)
SITE_SQLITE_GUARDS["trg_zone_site_immutable"] = (
    "CREATE TRIGGER IF NOT EXISTS trg_zone_site_immutable BEFORE UPDATE OF site_id ON zones "
    "WHEN OLD.site_id IS NOT NULL AND NEW.site_id IS NOT OLD.site_id "
    "BEGIN SELECT RAISE(ABORT, 'zone site identity is immutable'); END"
)

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

for _sql in SITE_SQLITE_GUARDS.values():
    event.listen(Base.metadata, "after_create", DDL(_sql).execute_if(dialect="sqlite"))
event.listen(Base.metadata, "after_create", DDL(SITE_POSTGRES_GUARD_SQL).execute_if(dialect="postgresql"))
