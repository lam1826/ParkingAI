"""Slot-row serialization makes reservations and both legacy admissions compete fairly."""
from datetime import timedelta

from fastapi import HTTPException
from sqlalchemy import and_, exists, or_, select, update

from core.clock import BUSINESS_TZ
from crud import parking_session as session_crud
from expansion.site_models import GuaranteedAllocation, ParkingReservation, SiteWaitlist
from expansion.site_scope import require_public_site, require_site_access
from models.parking_session import ParkingSession
from models.parking_slot import ParkingSlot
from models.vehicle import Vehicle
from models.zone import Zone


def local_time(value):
    return value.astimezone(BUSINESS_TZ).replace(tzinfo=None) if value.tzinfo else value


def serialize(row):
    result = {}
    for column in row.__table__.columns:
        value = getattr(row, column.name)
        if hasattr(value, "tzinfo") and value.tzinfo is None:
            value = value.replace(tzinfo=BUSINESS_TZ)
        result[column.name] = value
    return result


def lock_slot(db, slot_id):
    if db.get_bind().dialect.name == "sqlite":
        db.execute(update(ParkingSlot).where(ParkingSlot.id == slot_id).values(id=ParkingSlot.id))
    return db.scalar(select(ParkingSlot).where(ParkingSlot.id == slot_id).with_for_update()
                     .execution_options(populate_existing=True))


def expire_slot(db, slot_id, now):
    """Caller holds the slot lock. Repeating expiry never changes arrived/cancelled rows."""
    return db.execute(update(ParkingReservation).where(
        ParkingReservation.slot_id == slot_id, ParkingReservation.status == "confirmed",
        ParkingReservation.arrival_deadline <= now,
    ).values(status="expired")).rowcount


def _slot_rows(db, slot_id, now):
    reservations = db.scalars(select(ParkingReservation).where(
        ParkingReservation.slot_id == slot_id,
        ParkingReservation.status.in_(["confirmed", "arrived"]),
        ParkingReservation.end_at > now,
        or_(ParkingReservation.status == "arrived", ParkingReservation.arrival_deadline > now),
    ).execution_options(populate_existing=True)).all()
    allocations = db.scalars(select(GuaranteedAllocation).where(
        GuaranteedAllocation.slot_id == slot_id, GuaranteedAllocation.status == "active",
        GuaranteedAllocation.end_at > now,
    ).execution_options(populate_existing=True)).all()
    return reservations, allocations


def admission_allowed(db, slot_id, *, vehicle_id=None, at=None, lock=True):
    """An unscheduled stay has no departure bound, so future commitments also protect it.

    A reserved/allotted admission may precede a later booking. Its actual occupied
    slot remains authoritative if the driver overstays; no new car replaces it.
    """
    now = at if at is not None else session_crud.server_now()
    if lock:
        slot = lock_slot(db, slot_id)
        if slot is None:
            return False
        expire_slot(db, slot_id, now)
    reservations, allocations = _slot_rows(db, slot_id, now)
    vehicle = db.get(Vehicle, vehicle_id) if vehicle_id is not None else None
    owner_id = vehicle.customer_id if vehicle is not None else None
    eligible = [r for r in reservations if r.status == "confirmed" and r.vehicle_id == vehicle_id
                and owner_id is not None and r.customer_id == owner_id
                and r.start_at <= now < r.arrival_deadline]
    own_allocations = [r for r in allocations if r.vehicle_id == vehicle_id and r.customer_id == owner_id
                       and owner_id is not None and r.start_at <= now < r.end_at]
    entitlement = eligible + own_allocations
    end = max((r.end_at for r in entitlement), default=None)
    for row in reservations + allocations:
        if row in entitlement:
            continue
        if row.vehicle_id == vehicle_id and row.customer_id == owner_id and end is not None:
            continue
        if end is None or row.start_at < end:
            return False
    return True


def record_admission(db, session):
    """Called before the existing check-in commit; session and arrival stay atomic."""
    if session.parking_slot_id is None:
        return
    now = session.check_in_time
    row = db.scalar(select(ParkingReservation).where(
        ParkingReservation.slot_id == session.parking_slot_id,
        ParkingReservation.vehicle_id == session.vehicle_id,
        ParkingReservation.status == "confirmed", ParkingReservation.start_at <= now,
        ParkingReservation.arrival_deadline > now,
    ).with_for_update())
    if row is not None:
        db.flush()
        row.status = "arrived"
        row.session_id = session.id
        db.flush()


def _vehicle(db, actor, vehicle_id, site_id, *, customer=False):
    require_public_site(db, site_id)
    vehicle = db.get(Vehicle, vehicle_id)
    if vehicle is None:
        raise HTTPException(404, "Không tìm thấy xe.")
    if customer:
        from expansion.portal_service import require_owned_vehicle
        vehicle = require_owned_vehicle(db, actor, vehicle_id)
    else:
        require_site_access(db, actor, site_id)
    if vehicle.customer_id is None:
        raise HTTPException(409, "Xe cần được liên kết với khách hàng đã xác minh trước khi giữ chỗ.")
    return vehicle


def _check_window(data, now):
    start, end = local_time(data.start_at), local_time(data.end_at)
    if start < now or end <= start:
        raise HTTPException(422, "Chỉ được đặt khoảng thời gian hiện tại hoặc tương lai.")
    return start, end


def _same_request(row, data, actor_id, start, end):
    return (row.site_id, row.vehicle_id, row.start_at, row.end_at, row.created_by_id) == (
        data.site_id, data.vehicle_id, start, end, actor_id,
    ) and (getattr(data, "slot_id", None) is None or row.slot_id == data.slot_id)


def _existing(db, model, data, actor, start, end):
    row = db.scalar(select(model).where(model.request_id == data.request_id))
    if row is not None and not _same_request(row, data, actor.id, start, end):
        raise HTTPException(409, "Mã yêu cầu đã dùng cho nội dung khác.")
    return row


def _physical_slot(db, slot_id, site_id, vehicle_type_id):
    slot = lock_slot(db, slot_id)
    zone = db.get(Zone, slot.zone_id) if slot else None
    if (slot is None or not slot.is_active or zone is None or not zone.is_active
            or zone.site_id != site_id or slot.vehicle_type_id != vehicle_type_id):
        raise HTTPException(404, "Vị trí không thuộc bãi hoặc không phù hợp loại xe.")
    return slot


def _overlaps(db, slot, start, end, vehicle_id, now, *, customer_id, allocation=False):
    # Occupancy is unbounded until checkout; a future promise cannot assume exit.
    occupied = slot.is_occupied or db.scalar(select(exists().where(
        ParkingSession.parking_slot_id == slot.id, ParkingSession.status.in_(["active", "checking_out"]),
    )))
    if occupied:
        return True
    reservations, allocations = _slot_rows(db, slot.id, now)
    for row in reservations + allocations:
        if row.start_at < end and row.end_at > start:
            if (not allocation and isinstance(row, GuaranteedAllocation)
                    and row.vehicle_id == vehicle_id and row.customer_id == customer_id):
                # A reserved arrival can consume its existing dedicated allocation.
                if row.start_at <= start and row.end_at >= end:
                    continue
            return True
    return False


def reserve(db, actor, data, *, customer=False, allocation=False, _now=None):
    vehicle = _vehicle(db, actor, data.vehicle_id, data.site_id, customer=customer)
    if allocation:
        require_site_access(db, actor, data.site_id, "manager")
    # Internal callers may share their transaction's server instant. In particular,
    # an offer whose original start passed must not become "past" on a second read.
    # This value is never accepted in the API body.
    now = session_crud.server_now() if _now is None else _now
    start, end = local_time(data.start_at), local_time(data.end_at)
    model = GuaranteedAllocation if allocation else ParkingReservation
    # Serialize overlapping requests for the same vehicle across different slots/sites.
    # NO KEY UPDATE on PostgreSQL remains compatible with session FK reads.
    if db.get_bind().dialect.name == "sqlite":
        db.execute(update(Vehicle).where(Vehicle.id == vehicle.id).values(id=Vehicle.id))
    db.scalar(select(Vehicle.id).where(Vehicle.id == vehicle.id).with_for_update(key_share=True))
    old = _existing(db, model, data, actor, start, end)
    if old is not None:
        return old
    _check_window(data, now)
    # A booking made by a previous owner keeps holding its slot (slot-level checks below),
    # but it must not stop the verified current owner from booking elsewhere.
    if db.scalar(select(ParkingReservation.id).where(
        ParkingReservation.vehicle_id == vehicle.id,
        ParkingReservation.customer_id == vehicle.customer_id,
        ParkingReservation.status.in_(["confirmed", "arrived"]),
        ParkingReservation.start_at < end, ParkingReservation.end_at > start,
        or_(ParkingReservation.status == "arrived", ParkingReservation.arrival_deadline > now),
    ).limit(1)):
        raise HTTPException(409, "Xe đã có đặt chỗ trong khoảng thời gian này.")
    query = select(ParkingSlot.id).join(Zone).where(
        Zone.site_id == data.site_id, Zone.is_active.is_(True), ParkingSlot.is_active.is_(True),
        ParkingSlot.vehicle_type_id == vehicle.vehicle_type_id,
    ).order_by(ParkingSlot.id)
    if data.slot_id is not None:
        query = query.where(ParkingSlot.id == data.slot_id)
    candidates = db.scalars(query).all()
    if not candidates:
        raise HTTPException(404, "Không có vị trí phù hợp tại bãi.")
    for slot_id in candidates:
        slot = _physical_slot(db, slot_id, data.site_id, vehicle.vehicle_type_id)
        expire_slot(db, slot.id, now)
        # Check again after acquiring the serialization lock (concurrent retry).
        old = _existing(db, model, data, actor, start, end)
        if old is not None:
            return old
        if _overlaps(db, slot, start, end, vehicle.id, now,
                     customer_id=vehicle.customer_id, allocation=allocation):
            continue
        row = model(site_id=data.site_id, slot_id=slot.id, customer_id=vehicle.customer_id,
                    vehicle_id=vehicle.id, start_at=start, end_at=end,
                    request_id=data.request_id, created_by_id=actor.id)
        if not allocation:
            row.arrival_deadline = min(start + timedelta(minutes=15), end)
        db.add(row)
        db.flush()
        return row
    raise HTTPException(409, "Không còn vị trí phù hợp trong khoảng đã chọn. Có thể tham gia danh sách chờ.")


def cancel(db, actor, row, *, customer=False):
    lock_slot(db, row.slot_id)
    db.refresh(row)
    if customer:
        from expansion.portal_service import get_linked_customer
        owner = get_linked_customer(db, actor)
        if owner is None or row.customer_id != owner.id:
            raise HTTPException(404, "Không tìm thấy đặt chỗ của tài khoản.")
    else:
        require_site_access(db, actor, row.site_id,
                            "manager" if isinstance(row, GuaranteedAllocation) else "staff")
    if row.status == "arrived":
        raise HTTPException(409, "Xe đã vào bãi; hãy sử dụng nghiệp vụ xe ra.")
    if row.status in {"cancelled", "expired"}:
        return row
    row.status = "cancelled"
    db.flush()
    return row


def arrive(db, actor, row):
    require_site_access(db, actor, row.site_id)
    lock_slot(db, row.slot_id)
    db.refresh(row)
    if row.status == "arrived":
        return row
    now = session_crud.server_now()
    if row.status != "confirmed" or not row.start_at <= now < row.arrival_deadline:
        raise HTTPException(409, "Đặt chỗ chưa đến giờ, đã hết hạn hoặc đã hủy.")
    vehicle = db.get(Vehicle, row.vehicle_id)
    if vehicle is None or vehicle.customer_id != row.customer_id:
        raise HTTPException(409, "Chủ xe đã thay đổi; cần xác minh lại đặt chỗ.")
    from services.parking_service import ParkingService
    admission = ParkingService(db).check_in(
        vehicle.license_plate, vehicle.vehicle_type_id, actor.id,
        parking_slot_id=row.slot_id, _check_in_time=now,
        _expected_site_id=row.site_id, _commit=False,
    )
    db.refresh(row)
    if row.status != "arrived" or row.session_id != admission["session_id"]:
        raise HTTPException(409, "Chưa ghi nhận được lượt vào; hãy tra cứu phiên gửi.")
    return row


def join_waitlist(db, actor, data, *, customer=False):
    vehicle = _vehicle(db, actor, data.vehicle_id, data.site_id, customer=customer)
    now = session_crud.server_now()
    start, end = local_time(data.start_at), local_time(data.end_at)
    old = _existing(db, SiteWaitlist, data, actor, start, end)
    if old:
        return old
    _check_window(data, now)
    row = SiteWaitlist(site_id=data.site_id, customer_id=vehicle.customer_id, vehicle_id=vehicle.id,
                       start_at=start, end_at=end, request_id=data.request_id, created_by_id=actor.id)
    db.add(row)
    db.flush()
    return row


def offer_waitlist(db, actor, row):
    require_site_access(db, actor, row.site_id)
    # A no-op write serializes SQLite; PostgreSQL locks only this request row.
    if db.get_bind().dialect.name == "sqlite":
        db.execute(update(SiteWaitlist).where(SiteWaitlist.id == row.id).values(id=SiteWaitlist.id))
    db.refresh(row, with_for_update=True)
    if row.status == "offered":
        return db.get(ParkingReservation, row.reservation_id)
    if row.status != "waiting":
        raise HTTPException(409, "Yêu cầu không còn trong danh sách chờ.")
    from expansion.site_schemas import ReservationCreate
    now = session_crud.server_now()
    start = max(row.start_at, now)
    if start >= row.end_at:
        raise HTTPException(409, "Khoảng thời gian chờ đã kết thúc; cần tạo yêu cầu mới.")
    vehicle = db.get(Vehicle, row.vehicle_id)
    if vehicle is None or vehicle.customer_id != row.customer_id:
        raise HTTPException(409, "Chủ xe đã thay đổi; cần xác minh lại yêu cầu.")
    data = ReservationCreate(site_id=row.site_id, vehicle_id=row.vehicle_id,
                             start_at=start.replace(tzinfo=BUSINESS_TZ), end_at=row.end_at.replace(tzinfo=BUSINESS_TZ),
                             request_id="waitlist-" + row.id)
    reservation = reserve(db, actor, data, _now=now)
    row.status, row.reservation_id = "offered", reservation.id
    db.flush()
    return reservation


def cancel_waitlist(db, actor, row, *, customer=False):
    if customer:
        from expansion.portal_service import get_linked_customer
        if row.customer_id != get_linked_customer(db, actor).id:
            raise HTTPException(404, "Không tìm thấy yêu cầu chờ của tài khoản.")
    else:
        require_site_access(db, actor, row.site_id)
    if db.get_bind().dialect.name == "sqlite":
        db.execute(update(SiteWaitlist).where(SiteWaitlist.id == row.id).values(id=SiteWaitlist.id))
    db.refresh(row, with_for_update=True)
    if row.status == "offered":
        raise HTTPException(409, "Đã cấp đặt chỗ; hãy hủy đặt chỗ tương ứng.")
    row.status = "cancelled"
    db.flush()
    return row
