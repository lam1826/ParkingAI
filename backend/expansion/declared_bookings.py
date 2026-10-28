"""Optional customer declarations reserve capacity without claiming a vehicle.

Review 28/10/2026 (R2-01): a declaration acts for a vehicle only when the plate
is not verified to any profile, or when the declarer is the account linked to
that profile. Another account's declaration of a verified plate is refused at
creation, released when ownership is assigned (portal approval, account link
approval or a staff vehicle edit), and is never consumed by, matched to or
shown the stay of the owner's car. A row left from before the fix still blocks
the owner's bookings of the plate (plate exclusivity) until the deploy step
``expansion.release_foreign_declarations`` releases it.
"""
from datetime import timedelta

from fastapi import HTTPException
from sqlalchemy import and_, exists, func, select, text, true, update
from sqlalchemy.orm import object_session

from core.clock import BUSINESS_TZ
from core.vehicle_identity import admission_identity, canonical_identity, identity_expression, lock_identity, resolve_vehicle
from crud.parking_session import server_now
from crud.vehicle_type import require_active_vehicle_type
from expansion.portal_models import PortalAccountLink
from expansion.simplified_customer_models import DeclaredParkingReservation as Booking
from expansion.site_scope import require_public_site
from expansion.ticket_payment_access import customer_only
from models.parking_slot import ParkingSlot
from models.parking_session import ParkingSession
from models.user import User
from models.vehicle import Vehicle
from models.zone import Zone

# One answer for every type and window: it reveals neither the registered type
# nor the owner's commitments.
DECLARATION_REFUSED = ("Không thể đặt trước cho biển số/mã xe này với loại xe đã chọn. Hãy kiểm tra lại biển số, "
    "loại xe hoặc liên hệ bãi để được hỗ trợ.")
FOREIGN_RECEPTION = "Đặt trước này không thuộc tài khoản của chủ xe đã xác minh. Hãy tiếp nhận xe như lượt vào thường."


def live_declared(now):
    return and_(Booking.status == 'confirmed', Booking.arrival_deadline > now, Booking.end_at > now)


def speaks_for(vehicle):
    """SQL: the declaration may act for this vehicle (unverified plate, or declared by the owner's account)."""
    if vehicle.customer_id is None:
        return true()
    return Booking.user_id.in_(select(PortalAccountLink.user_id).where(PortalAccountLink.customer_id == vehicle.customer_id))


def speaks_for_row(db, row, vehicle):
    """The same test as ``speaks_for`` on a loaded row."""
    if vehicle.customer_id is None:
        return True
    return db.scalar(select(PortalAccountLink.id).where(PortalAccountLink.customer_id == vehicle.customer_id,
        PortalAccountLink.user_id == row.user_id)) is not None


def commitment(slot_id, now):
    return exists().where(Booking.slot_id == slot_id, live_declared(now))


def overlaps(db, slot_id, start, end, now):
    return db.scalar(select(Booking.id).where(Booking.slot_id == slot_id, live_declared(now),
        Booking.start_at < end, Booking.end_at > start).limit(1)) is not None


def rows_for_slot(db, slot_id, now):
    return db.scalars(select(Booking).where(Booking.slot_id == slot_id, live_declared(now))
        .execution_options(populate_existing=True)).all()


def matches(row, vehicle, now):
    # Another account's declaration of a verified plate grants the owner's car
    # nothing: admission treats it as someone else's commitment.
    return vehicle is not None and row.normalized_plate == canonical_identity(vehicle.license_plate) \
        and row.vehicle_type_id == vehicle.vehicle_type_id and row.start_at <= now < row.arrival_deadline \
        and speaks_for_row(object_session(row), row, vehicle)


def preferred_slot(db, vehicle, site_id, now):
    query = select(Booking.slot_id).where(Booking.normalized_plate == canonical_identity(vehicle.license_plate),
        Booking.vehicle_type_id == vehicle.vehicle_type_id, live_declared(now), Booking.start_at <= now,
        speaks_for(vehicle))
    if site_id is not None:
        query = query.where(Booking.site_id == site_id)
    return db.scalar(query.order_by(Booking.start_at, Booking.id).limit(1))


def consume(db, session, site_id, vehicle):
    now = session.check_in_time
    # A foreign row is never selected: it never becomes 'arrived' or learns the owner's session.
    row = db.scalar(select(Booking).where(Booking.site_id == site_id, live_declared(now), Booking.start_at <= now,
        Booking.vehicle_type_id == vehicle.vehicle_type_id,
        Booking.normalized_plate == canonical_identity(vehicle.license_plate), speaks_for(vehicle)).with_for_update())
    if row is None:
        return
    if row.slot_id != session.parking_slot_id:
        raise HTTPException(409, 'Xe đã được giữ một vị trí khác. Hãy chọn tự xếp chỗ hoặc đúng vị trí đặt trước.')
    row.status, row.session_id = 'arrived', session.id
    db.flush()


def serialize(db, row, *, include_session=False):
    """Customer views omit the session id; staff reception passes ``include_session=True``."""
    slot = db.get(ParkingSlot, row.slot_id)
    keys = ('id', 'site_id', 'slot_id', 'license_plate', 'vehicle_type_id', 'start_at', 'end_at',
        'arrival_deadline', 'status', 'created_at') + (('session_id',) if include_session else ())
    result = {key: getattr(row, key) for key in keys}
    for key in ('start_at', 'end_at', 'arrival_deadline', 'created_at'):
        result[key] = result[key].replace(tzinfo=BUSINESS_TZ)
    if row.status == 'confirmed' and row.arrival_deadline <= server_now():
        result['status'] = 'expired'
    result['slot_name'] = slot.slot_name if slot else None
    return result


def create(db, user, data):
    customer_only(user)
    require_public_site(db, data.site_id)
    from expansion.reservations import live_reservation, local_time, lock_slot, _overlaps
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
    # Before any window, limit, collision or commitment check: a plate verified to
    # another profile, or a known plate with another type, gets one answer for
    # every type and window, so the refusal reveals neither the type nor times.
    declarer = db.scalar(select(PortalAccountLink.customer_id).where(PortalAccountLink.user_id == user.id))
    if vehicle is not None and ((vehicle.customer_id is not None and vehicle.customer_id != declarer)
            or vehicle.vehicle_type_id != vehicle_type.id):
        raise HTTPException(409, DECLARATION_REFUSED)
    now = server_now()
    if start < now or start > now + timedelta(days=30) or end <= start:
        raise HTTPException(422, 'Chọn giờ đến trong 30 ngày tới và giờ kết thúc sau giờ đến.')
    count = db.scalar(select(func.count()).select_from(Booking).where(Booking.user_id == user.id, live_declared(now)))
    if count >= 5:
        raise HTTPException(409, 'Mỗi tài khoản được giữ tối đa 5 đặt chỗ đang hoạt động.')
    if db.scalar(select(Booking.id).where(Booking.normalized_plate == normalized, live_declared(now),
        Booking.start_at < end, Booking.end_at > start).limit(1)):
        raise HTTPException(409, 'Biển số hoặc mã xe đã có đặt chỗ trong khoảng này.')
    from expansion.site_models import ParkingReservation, GuaranteedAllocation
    from expansion.timed_parking_models import ParkingCapacityHold, TimedParkingPass
    if vehicle is not None:
        # Expiry can be evaluated before a slot writer updates stored status;
        # an arrived row remains history after checkout. Share capacity's live
        # predicate while preserving the separate recurring allocation right.
        for model, live in ((ParkingReservation, live_reservation(now)),
                            (GuaranteedAllocation, GuaranteedAllocation.status == 'active'),
                            (ParkingCapacityHold, and_(ParkingCapacityHold.status == 'held', ParkingCapacityHold.expires_at > now)),
                            (TimedParkingPass, and_(TimedParkingPass.status == 'ready', TimedParkingPass.arrival_deadline > now))):
            if db.scalar(select(model.id).where(model.vehicle_id == vehicle.id, live,
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


def plate_overlaps(db, vehicle, start, end, now):
    return db.scalar(select(Booking.id).where(Booking.normalized_plate == canonical_identity(vehicle.license_plate),
        live_declared(now), Booking.start_at < end, Booking.end_at > start).limit(1)) is not None


def release_foreign(db, vehicle, now=None):
    """Cancel other accounts' live declarations once the plate is verified to a profile.

    The caller holds ``lock_identity`` for the plate and takes no slot lock after
    this call in the same transaction: one bulk update that only frees capacity.
    The owner's own declarations stay. Call only where ownership is assigned
    (portal approval, account link approval, staff vehicle create/update, the
    deploy step ``expansion.release_foreign_declarations``), never from
    admission or a booking path. Returns the number of rows released.
    """
    if vehicle.customer_id is None:
        return 0
    now = server_now() if now is None else now
    owner = db.scalar(select(PortalAccountLink.user_id).where(PortalAccountLink.customer_id == vehicle.customer_id))
    query = update(Booking).where(Booking.normalized_plate == canonical_identity(vehicle.license_plate), live_declared(now))
    if owner is not None:
        query = query.where(Booking.user_id != owner)
    released = db.execute(query.values(status='cancelled').execution_options(synchronize_session='fetch')).rowcount
    db.flush()
    return released


def require_arrival_window(db, vehicle, site_id, now, booking_id, *, lock=False):
    """Validate only the declaration explicitly selected for reception."""
    query = select(Booking).where(Booking.id == booking_id, Booking.site_id == site_id)
    if lock:
        query = query.with_for_update()
    row = db.scalar(query.execution_options(populate_existing=True))
    if row is None:
        raise HTTPException(404, "Không tìm thấy đặt trước tại bãi này.")
    if (row.normalized_plate != canonical_identity(vehicle.license_plate)
            or row.vehicle_type_id != vehicle.vehicle_type_id):
        raise HTTPException(409, "Xe thực tế không khớp đặt trước đã chọn. Hãy kiểm tra lại.")
    if not speaks_for_row(db, row, vehicle):
        raise HTTPException(409, FOREIGN_RECEPTION)
    if row.status != 'confirmed' or row.arrival_deadline <= now or row.end_at <= now:
        raise HTTPException(409, "Đặt trước đã kết thúc hoặc đã nhận xe. Hãy tra lịch sử xe.")
    if row.start_at > now:
        raise HTTPException(409, "Đặt trước chưa đến giờ hẹn. Hãy tiếp nhận theo đúng lịch đã chọn.")
    return row
