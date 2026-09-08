"""Site management and fleet visibility for one operator managing multiple lots."""
from fastapi import HTTPException
from sqlalchemy import case, func, select

from core.money import require_exact_vnd
from core.clock import day_bounds
from crud import parking_session as session_crud
from expansion.reservations import has_slot_commitment, serialize
from expansion.site_models import (
    FleetVehicle, Organization, OrganizationMembership, ParkingSite, SiteMembership,
)
from expansion.site_scope import allowed_site_ids, is_global_admin, require_public_site, require_site_access
from models.parking_session import ParkingSession
from models.parking_slot import ParkingSlot
from models.user import User
from models.vehicle import Vehicle
from models.zone import Zone


def create_site(db, actor, data):
    if not is_global_admin(actor):
        raise HTTPException(403, "Chỉ quản trị viên hệ thống được tạo bãi.")
    row = ParkingSite(**data.model_dump())
    db.add(row)
    db.flush()
    return row


def set_member(db, actor, site_id, data):
    # Membership grants are centrally administered, preventing local privilege escalation.
    if not is_global_admin(actor):
        raise HTTPException(403, "Chỉ quản trị viên hệ thống được cấp quyền theo bãi.")
    require_public_site(db, site_id)
    user = db.get(User, data.user_id)
    if user is None or not user.is_active or user.role.name not in {"staff", "manager"}:
        raise HTTPException(422, "Thành viên vận hành cần tài khoản nhân viên hoặc quản lý đang hoạt động.")
    row = db.scalar(select(SiteMembership).where(SiteMembership.site_id == site_id,
                                                SiteMembership.user_id == user.id))
    if row is None:
        row = SiteMembership(site_id=site_id, user_id=user.id, role=data.role)
        db.add(row)
    else:
        row.role = data.role
    db.flush()
    return row


def availability(db, site_id):
    require_public_site(db, site_id)
    now = session_crud.server_now()
    rows = db.execute(select(ParkingSlot, Zone.name, has_slot_commitment(ParkingSlot.id, now)).join(Zone).where(
        Zone.site_id == site_id, Zone.is_active.is_(True), ParkingSlot.is_active.is_(True),
    ).order_by(ParkingSlot.id)).all()
    slots = []
    for slot, zone_name, committed in rows:
        available = not slot.is_occupied and not committed
        slots.append({"id": slot.id, "slot_name": slot.slot_name, "zone_id": slot.zone_id,
                      "zone_name": zone_name, "vehicle_type_id": slot.vehicle_type_id,
                      "is_occupied": slot.is_occupied, "available_now": available,
                      "reserved": not slot.is_occupied and not available})
    return {"site_id": site_id, "total": len(slots), "occupied": sum(s["is_occupied"] for s in slots),
            "available_now": sum(s["available_now"] for s in slots),
            "reserved_slots": sum(s["reserved"] for s in slots), "slots": slots}


def scoped_session(db, actor, site_id, session_id):
    require_site_access(db, actor, site_id)
    session = db.scalar(select(ParkingSession).join(ParkingSlot).join(Zone).where(
        ParkingSession.id == session_id, Zone.site_id == site_id,
    ))
    if session is None:
        raise HTTPException(404, "Không tìm thấy lượt gửi tại bãi.")
    return session


def site_sessions(db, actor, site_id, *, limit=100, offset=0, license_plate=None, status=None, date_from=None, date_to=None):
    require_site_access(db, actor, site_id)
    if date_from and date_to and date_from > date_to:
        raise HTTPException(422, "Ngày bắt đầu phải trước hoặc bằng ngày kết thúc.")
    query = select(ParkingSession, Vehicle.license_plate, ParkingSlot.slot_name).join(
        Vehicle, Vehicle.id == ParkingSession.vehicle_id,
    ).join(ParkingSlot, ParkingSlot.id == ParkingSession.parking_slot_id).join(Zone).where(
        Zone.site_id == site_id,
    )
    if license_plate:
        query = query.where(Vehicle.license_plate == license_plate.strip().upper())
    if status:
        query = query.where(ParkingSession.status == status)
    try:
        if date_from:
            query = query.where(ParkingSession.check_in_time >= day_bounds(date_from)[0])
        if date_to:
            query = query.where(ParkingSession.check_in_time < day_bounds(date_to)[1])
    except (ValueError, OverflowError) as error:
        raise HTTPException(422, "Ngày nằm ngoài phạm vi tra cứu được hỗ trợ.") from error
    rows = db.execute(query.order_by(ParkingSession.check_in_time.desc(), ParkingSession.id).offset(offset).limit(limit)).all()
    return [{**serialize(session), "license_plate": plate, "slot_name": slot_name}
            for session, plate, slot_name in rows]


def require_organization(db, actor, organization_id, *, manage=False):
    organization = db.get(Organization, organization_id)
    if organization is None or not organization.is_active:
        raise HTTPException(404, "Không tìm thấy nhóm xe.")
    require_public_site(db, organization.site_id)
    if is_global_admin(actor):
        return organization
    if actor.role.name in {"staff", "manager"}:
        require_site_access(db, actor, organization.site_id, "manager" if manage else "staff")
        return organization
    if manage or not db.scalar(select(OrganizationMembership.id).where(
        OrganizationMembership.organization_id == organization.id, OrganizationMembership.user_id == actor.id,
    )):
        raise HTTPException(403, "Bạn không có quyền với nhóm xe này.")
    return organization


FLEET_SESSION_FIELDS = ("id", "vehicle_id", "check_in_time", "check_out_time", "status", "parking_fee")
FLEET_FEE_NOTE = ("Tổng phí các lượt gửi đã hoàn tất, chưa trừ hoàn tiền và không gồm thanh toán vé tháng "
                  "(chứng từ DEMO là chứng từ vé tháng, không xuất hiện ở đây).")
FLEET_PAGE_MAX = 100


def _fleet_sessions(organization, *columns):
    """One join/filter set for the list and the totals, so both see the same authorized rows.

    Joining a fleet never reveals the vehicle's history before association.
    """
    return select(*columns).select_from(ParkingSession).join(
        FleetVehicle, FleetVehicle.vehicle_id == ParkingSession.vehicle_id,
    ).join(Vehicle, Vehicle.id == ParkingSession.vehicle_id).join(
        ParkingSlot, ParkingSlot.id == ParkingSession.parking_slot_id,
    ).join(Zone).where(
        FleetVehicle.organization_id == organization.id,
        ParkingSession.check_in_time >= FleetVehicle.created_at,
        Zone.site_id == organization.site_id,
    )


def _fleet_session(session, license_plate, slot_name):
    # Same timestamp convention as ``serialize``; only the reporting fields cross the boundary.
    row = serialize(session)
    return {**{name: row[name] for name in FLEET_SESSION_FIELDS},
            "license_plate": license_plate, "slot_name": slot_name}


def fleet_summary(db, actor, organization_id, *, limit=50, offset=0):
    if not isinstance(limit, int) or not 1 <= limit <= FLEET_PAGE_MAX:
        raise HTTPException(422, f"limit phải từ 1 đến {FLEET_PAGE_MAX}.")
    if not isinstance(offset, int) or offset < 0:
        raise HTTPException(422, "offset phải là số nguyên không âm.")
    organization = require_organization(db, actor, organization_id)
    vehicles = db.execute(select(FleetVehicle, Vehicle).join(Vehicle).where(
        FleetVehicle.organization_id == organization_id,
    ).order_by(Vehicle.license_plate)).all()
    completed = ParkingSession.status == "completed"
    total, active, done, fees = db.execute(_fleet_sessions(
        organization, func.count(ParkingSession.id),
        func.coalesce(func.sum(case((ParkingSession.status == "active", 1), else_=0)), 0),
        func.coalesce(func.sum(case((completed, 1), else_=0)), 0),
        func.coalesce(func.sum(case((completed, ParkingSession.parking_fee), else_=None)), 0),
    )).one()
    rows = db.execute(_fleet_sessions(organization, ParkingSession, Vehicle.license_plate, ParkingSlot.slot_name)
                      .order_by(ParkingSession.check_in_time.desc(), ParkingSession.id.desc())
                      .offset(offset).limit(limit)).all()
    return {"organization": serialize(organization),
            "vehicles": [{"id": link.id, "vehicle_id": vehicle.id, "license_plate": vehicle.license_plate,
                          "vehicle_type_id": vehicle.vehicle_type_id, "joined_at": serialize(link)["created_at"]}
                         for link, vehicle in vehicles],
            "total_sessions": int(total), "active_sessions": int(active), "completed_sessions": int(done),
            "parking_fees": require_exact_vnd(fees, label="Tổng phí lượt gửi"),
            "fee_note": FLEET_FEE_NOTE, "limit": limit, "offset": offset,
            "sessions": [_fleet_session(session, plate, slot_name) for session, plate, slot_name in rows]}
