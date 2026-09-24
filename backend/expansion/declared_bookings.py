"""Optional customer declarations reserve capacity without claiming a vehicle."""
from datetime import timedelta

from fastapi import HTTPException
from sqlalchemy import and_, exists, func, select, text, update

from core.clock import BUSINESS_TZ
from core.vehicle_identity import admission_identity, canonical_identity, identity_expression, lock_identity, resolve_vehicle
from crud.parking_session import server_now
from crud.vehicle_type import require_active_vehicle_type
from expansion.simplified_customer_models import DeclaredParkingReservation as Booking
from expansion.site_scope import require_public_site
from expansion.ticket_payment_access import customer_only
from models.parking_slot import ParkingSlot
from models.parking_session import ParkingSession
from models.user import User
from models.vehicle import Vehicle
from models.zone import Zone


def live_declared(now):
    return and_(Booking.status == 'confirmed', Booking.arrival_deadline > now, Booking.end_at > now)


def commitment(slot_id, now):
    return exists().where(Booking.slot_id == slot_id, live_declared(now))


def overlaps(db, slot_id, start, end, now):
    return db.scalar(select(Booking.id).where(Booking.slot_id == slot_id, live_declared(now),
        Booking.start_at < end, Booking.end_at > start).limit(1)) is not None


def rows_for_slot(db, slot_id, now):
    return db.scalars(select(Booking).where(Booking.slot_id == slot_id, live_declared(now))
        .execution_options(populate_existing=True)).all()


def matches(row, vehicle, now):
    return vehicle is not None and row.normalized_plate == canonical_identity(vehicle.license_plate) \
        and row.vehicle_type_id == vehicle.vehicle_type_id and row.start_at <= now < row.arrival_deadline


def preferred_slot(db, vehicle, site_id, now):
    query = select(Booking.slot_id).where(Booking.normalized_plate == canonical_identity(vehicle.license_plate),
        Booking.vehicle_type_id == vehicle.vehicle_type_id, live_declared(now), Booking.start_at <= now)
    if site_id is not None:
        query = query.where(Booking.site_id == site_id)
    return db.scalar(query.order_by(Booking.start_at, Booking.id).limit(1))


def consume(db, session, site_id, vehicle):
    now = session.check_in_time
    row = db.scalar(select(Booking).where(Booking.site_id == site_id, live_declared(now), Booking.start_at <= now,
        Booking.vehicle_type_id == vehicle.vehicle_type_id,
        Booking.normalized_plate == canonical_identity(vehicle.license_plate)).with_for_update())
    if row is None:
        return
    if row.slot_id != session.parking_slot_id:
        raise HTTPException(409, 'Xe đã được giữ một vị trí khác. Hãy chọn tự xếp chỗ hoặc đúng vị trí đặt trước.')
    row.status, row.session_id = 'arrived', session.id
    db.flush()


def serialize(db, row):
    slot = db.get(ParkingSlot, row.slot_id)
    result = {key: getattr(row, key) for key in ('id', 'site_id', 'slot_id', 'license_plate', 'vehicle_type_id',
        'start_at', 'end_at', 'arrival_deadline', 'status', 'session_id', 'created_at')}
    for key in ('start_at', 'end_at', 'arrival_deadline', 'created_at'):
        result[key] = result[key].replace(tzinfo=BUSINESS_TZ)
    if row.status == 'confirmed' and row.arrival_deadline <= server_now():
        result['status'] = 'expired'
    result['slot_name'] = slot.slot_name if slot else None
    return result


def create(db, user, data):
    customer_only(user)
    require_public_site(db, data.site_id)
    from expansion.reservations import local_time, lock_slot, _overlaps
    # Serialize this account's limit and idempotent key, without creating a
    # Customer/Vehicle/Ownership row for an unverified declaration.
    if db.get_bind().dialect.name == 'sqlite':
        db.execute(update(User).where(User.id == user.id).values(id=User.id))
    db.scalar(select(User.id).where(User.id == user.id).with_for_update())
    start, end = local_time(data.start_at), local_time(data.end_at)
    old = db.scalar(select(Booking).where(Booking.user_id == user.id, Booking.request_id == data.request_id))
    if old:
        same_plate = not data.license_plate or canonical_identity(data.license_plate) == old.normalized_plate
        if not same_plate or (old.site_id, old.vehicle_type_id, old.start_at, old.end_at) != (data.site_id, data.vehicle_type_id, start, end):
            raise HTTPException(409, 'Mã yêu cầu đã dùng cho nội dung khác.')
        return old
    from models.vehicle_type import VehicleType
    vehicle_type = db.get(VehicleType, data.vehicle_type_id)
    if vehicle_type is None or not vehicle_type.is_active:
        raise HTTPException(409, 'Loại xe đã ngừng hoặc không tồn tại.')
    plate = admission_identity(vehicle_type, data.license_plate)
    normalized = canonical_identity(plate)
    lock_identity(db, vehicle_type.id, plate)
    vehicle = resolve_vehicle(db, plate)
    vehicle_type = require_active_vehicle_type(db, data.vehicle_type_id)
    now = server_now()
    if start < now or start > now + timedelta(days=30) or end <= start:
        raise HTTPException(422, 'Chọn giờ đến trong 30 ngày tới và giờ kết thúc sau giờ đến.')
    count = db.scalar(select(func.count()).select_from(Booking).where(Booking.user_id == user.id, live_declared(now)))
    if count >= 5:
        raise HTTPException(409, 'Mỗi tài khoản được giữ tối đa 5 đặt chỗ đang hoạt động.')
    if db.scalar(select(Booking.id).where(Booking.normalized_plate == normalized, live_declared(now),
        Booking.start_at < end, Booking.end_at > start).limit(1)):
        raise HTTPException(409, 'Biển số hoặc mã xe đã có đặt chỗ trong khoảng này.')
    # Refuse incompatible known declarations without exposing owner details.
    if vehicle is not None and vehicle.vehicle_type_id != vehicle_type.id:
        raise HTTPException(409, 'Biển số/mã xe và loại xe chưa phù hợp; hãy kiểm tra tại bãi.')
    from expansion.site_models import ParkingReservation, GuaranteedAllocation
    if vehicle is not None:
        for model, statuses in ((ParkingReservation, ('confirmed', 'arrived')), (GuaranteedAllocation, ('active',))):
            if db.scalar(select(model.id).where(model.vehicle_id == vehicle.id, model.status.in_(statuses),
                model.start_at < end, model.end_at > start).limit(1)):
                raise HTTPException(409, 'Xe đã có cam kết chỗ trong khoảng này; hãy kiểm tra đặt chỗ hiện có.')
    candidates = db.scalars(select(ParkingSlot.id).join(Zone).where(Zone.site_id == data.site_id,
        Zone.is_active.is_(True), ParkingSlot.is_active.is_(True), ParkingSlot.vehicle_type_id == data.vehicle_type_id)
        .order_by(ParkingSlot.id)).all()
    for identity in candidates:
        slot = lock_slot(db, identity)
        now = server_now()
        if start < now:
            raise HTTPException(409, 'Giờ đến đã qua trong khi xử lý; hãy chọn lại giờ.')
        if not slot.is_active or not slot.zone.is_active or _overlaps(db, slot, start, end,
            vehicle.id if vehicle else None, now, customer_id=None, allocation=True):
            continue
        row = Booking(site_id=data.site_id, slot_id=slot.id, user_id=user.id, license_plate=plate,
            normalized_plate=normalized, vehicle_type_id=data.vehicle_type_id, start_at=start, end_at=end,
            arrival_deadline=min(start + timedelta(minutes=15), end), request_id=data.request_id)
        db.add(row)
        db.flush()
        return row
    raise HTTPException(409, 'Không còn vị trí phù hợp trong khoảng đã chọn.')


def cancel(db, user, identity):
    customer_only(user)
    row = db.scalar(select(Booking).where(Booking.id == identity, Booking.user_id == user.id))
    if row is None:
        raise HTTPException(404, 'Không tìm thấy đặt chỗ của bạn.')
    from expansion.reservations import lock_slot
    lock_slot(db, row.slot_id)
    db.refresh(row)
    if row.status == 'cancelled':
        return row
    if row.status != 'confirmed' or row.arrival_deadline <= server_now():
        raise HTTPException(409, 'Đặt chỗ đã kết thúc hoặc đã nhận xe; không thể hủy.')
    row.status = 'cancelled'
    db.flush()
    return row
