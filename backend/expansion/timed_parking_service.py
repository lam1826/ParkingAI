"""One transaction for capacity, prepaid rights and the existing payment ledger.

Public portal methods own commits. Helpers here never commit and take slot locks
before order/ticket locks. No clock supplied by the customer authorizes admission.
"""
import uuid
from datetime import timedelta

from fastapi import HTTPException
from sqlalchemy import exists, func, select, update
from sqlalchemy.orm import object_session

from core.clock import BUSINESS_TZ, business_now
from core.billing import PREPAID_POLICY_VERSION
from crud.vehicle_type import require_active_vehicle_type
from expansion.portal_models import PortalOrder
from expansion.site_models import ParkingReservation, GuaranteedAllocation, ParkingSite
from expansion.timed_parking_models import ParkingCapacityHold, TimedParkingPass
from models.parking_slot import ParkingSlot
from models.parking_session import ParkingSession
from models.vehicle import Vehicle
from models.zone import Zone

HOLD_TTL = timedelta(minutes=10)


def live_hold(slot_id, now):
    return (ParkingCapacityHold.slot_id == slot_id) & (ParkingCapacityHold.status == "held") & (ParkingCapacityHold.expires_at > now)


def hold_overlaps(db, slot_id, start, end, now, *, except_order=None):
    query = select(ParkingCapacityHold.id).where(live_hold(slot_id, now),
        ParkingCapacityHold.start_at < end, ParkingCapacityHold.end_at > start)
    if except_order is not None:
        query = query.where(ParkingCapacityHold.order_id != except_order)
    return db.scalar(query.limit(1)) is not None


def require_paid_booking_policy(db, site_id, vehicle, start, end, slot_id=None):
    site = db.get(ParkingSite, site_id)
    if site.customer_booking_mode != "paid_packages":
        return
    query = select(GuaranteedAllocation.id).where(GuaranteedAllocation.site_id == site_id,
        GuaranteedAllocation.vehicle_id == vehicle.id, GuaranteedAllocation.customer_id == vehicle.customer_id,
        GuaranteedAllocation.status == "active", GuaranteedAllocation.start_at <= start,
        GuaranteedAllocation.end_at >= end)
    if slot_id is not None:
        query = query.where(GuaranteedAllocation.slot_id == slot_id)
    if db.scalar(query.limit(1)) is None:
        raise HTTPException(409, "Bãi này nhận đặt chỗ qua đơn vé giờ/ngày. Hãy chọn gói vé để giữ chỗ.")


def prepare_order(db, user, vehicle, plan, data):
    """Caller holds account/customer/vehicle. Lock tariff and slot before snapshot."""
    from expansion.reservations import local_time, lock_slot, expire_slot, _overlaps, live_reservation
    from crud.parking_session import resolve_check_in_billing_snapshot
    if data.start_at is None:
        raise HTTPException(422, "Vé giờ/ngày cần thời gian bắt đầu có múi giờ.")
    start = local_time(data.start_at)
    require_active_vehicle_type(db, vehicle.vehicle_type_id)
    now = business_now()
    rate = resolve_check_in_billing_snapshot(db, vehicle.vehicle_type_id, now)
    if start < now or start > now + timedelta(days=30):
        raise HTTPException(422, "Chọn giờ bắt đầu trong 30 ngày tới.")
    end = start + timedelta(minutes=plan.duration_minutes)
    count = db.scalar(select(func.count()).select_from(ParkingCapacityHold).where(
        ParkingCapacityHold.customer_id == vehicle.customer_id, ParkingCapacityHold.status == "held",
        ParkingCapacityHold.expires_at > now))
    count += db.scalar(select(func.count()).select_from(ParkingReservation).where(
        ParkingReservation.customer_id == vehicle.customer_id, live_reservation(now),
        ParkingReservation.end_at > now))
    if count >= 5:
        raise HTTPException(409, "Mỗi khách có tối đa 5 đặt chỗ hoặc đơn giữ chỗ đang hoạt động.")
    for model, state in ((ParkingCapacityHold, "held"), (ParkingReservation, "confirmed"), (TimedParkingPass, "ready")):
        query = select(model.id).where(model.vehicle_id == vehicle.id, model.status == state,
            model.start_at < end, model.end_at > start)
        query = query.where(model.expires_at > now) if model is ParkingCapacityHold else query.where(model.arrival_deadline > now)
        if db.scalar(query.limit(1)):
            raise HTTPException(409, "Xe đã có quyền giữ chỗ trong khoảng thời gian này.")
    query = select(ParkingSlot.id).join(Zone).where(Zone.site_id == plan.site_id,
        Zone.is_active.is_(True), ParkingSlot.is_active.is_(True),
        ParkingSlot.vehicle_type_id == vehicle.vehicle_type_id).order_by(ParkingSlot.id)
    if data.zone_id is not None:
        query = query.where(Zone.id == data.zone_id)
    for slot_id in db.scalars(query).all():
        slot = lock_slot(db, slot_id)
        now = business_now()  # the slot may have been locked across a deadline
        if start < now:
            raise HTTPException(409, "Giờ bắt đầu đã qua trong khi xử lý. Hãy chọn lại giờ.")
        expire_slot(db, slot.id, now)
        if not slot.is_active or _overlaps(db, slot, start, end, vehicle.id, now, customer_id=vehicle.customer_id, allocation=True):
            continue
        if hold_overlaps(db, slot.id, start, end, now):
            continue
        deadline = min(start + timedelta(minutes=15), end)
        return dict(start_at=start, end_at=end, start_date=start.date(), end_date=end.date(),
            arrival_deadline=deadline, expires_at=min(now + HOLD_TTL, deadline),
            slot_id=slot.id, zone_id=slot.zone_id, requested_zone_id=data.zone_id,
            **{key: value for key, value in rate.items() if key != "billing_policy_version"})
    raise HTTPException(409, "Không còn vị trí phù hợp cho khoảng thời gian đã chọn.")


def add_hold(db, order):
    db.add(ParkingCapacityHold(order_id=order.id, site_id=order.site_id, slot_id=order.slot_id,
        vehicle_id=order.vehicle_id, customer_id=order.customer_id, start_at=order.start_at,
        end_at=order.end_at, expires_at=order.expires_at))
    db.flush()


def release_hold(db, order, *, expired=False):
    db.execute(update(ParkingCapacityHold).where(ParkingCapacityHold.order_id == order.id,
        ParkingCapacityHold.status == "held").values(status="expired" if expired else "released"))


def fulfillment_problem(db, order):
    hold = db.scalar(select(ParkingCapacityHold).where(ParkingCapacityHold.order_id == order.id).with_for_update())
    now = business_now()  # sample after every lock, including a delayed hold row
    if hold is None or hold.status != "held" or now >= hold.expires_at:
        return "capacity_hold_expired"
    if order.status not in {"pending", "review"}:
        return "order_not_payable"
    slot = db.get(ParkingSlot, order.slot_id)
    zone = db.get(Zone, order.zone_id)
    vehicle = db.get(Vehicle, order.vehicle_id)
    if (not slot.is_active or not zone.is_active or slot.is_occupied
            or slot.vehicle_type_id != vehicle.vehicle_type_id):
        return "capacity_unavailable"
    if db.scalar(select(ParkingSession.id).where(ParkingSession.parking_slot_id == slot.id,
            ParkingSession.status.in_(["active", "checking_out"])).limit(1)):
        return "capacity_unavailable"
    return None


def fulfill(db, order, *, method, collector):
    from services.payment_service import PaymentService
    problem = fulfillment_problem(db, order)
    if problem:
        raise HTTPException(409, "Chỗ giữ đã hết hạn hoặc không còn hợp lệ; cần kiểm tra giao dịch.")
    hold = db.scalar(select(ParkingCapacityHold).where(ParkingCapacityHold.order_id == order.id))
    reservation = ParkingReservation(id=str(uuid.uuid4()), site_id=order.site_id, slot_id=order.slot_id,
        customer_id=order.customer_id, vehicle_id=order.vehicle_id, start_at=order.start_at,
        end_at=order.end_at, arrival_deadline=order.arrival_deadline, request_id="order:" + order.id,
        order_id=order.id, created_by_id=order.user_id)
    db.add(reservation)
    db.flush()
    ticket = TimedParkingPass(id=str(uuid.uuid4()), order_id=order.id, reservation_id=reservation.id,
        site_id=order.site_id, slot_id=order.slot_id, customer_id=order.customer_id,
        vehicle_id=order.vehicle_id, vehicle_type_id=db.get(Vehicle, order.vehicle_id).vehicle_type_id,
        start_at=order.start_at, end_at=order.end_at, arrival_deadline=order.arrival_deadline,
        amount=order.amount, rate_config_id=order.rate_config_id, rate_ticket_type=order.rate_ticket_type,
        rate_unit_price=order.rate_unit_price, rate_effective_date=order.rate_effective_date)
    db.add(ticket)
    db.flush()
    receipt = PaymentService.record_receipt(db, source_type="portal_order", source_id=order.id,
        amount=order.amount, collected_by_id=collector, method=method)
    order.timed_pass_id, order.receipt_id, order.status = ticket.id, receipt.id, "fulfilled"
    hold.status, hold.reservation_id = "converted", reservation.id
    db.flush()


def admission_snapshot(db, vehicle, slot_id, at):
    """After vehicle/type/slot serialization, before session INSERT."""
    if slot_id is None:
        return None
    from expansion.reservations import lock_slot
    from crud.parking_session import server_now
    lock_slot(db, slot_id)
    site_id = db.scalar(select(Zone.site_id).join(ParkingSlot).where(ParkingSlot.id == slot_id))
    tickets = db.scalars(select(TimedParkingPass).where(TimedParkingPass.vehicle_id == vehicle.id,
        TimedParkingPass.customer_id == vehicle.customer_id, TimedParkingPass.site_id == site_id,
        TimedParkingPass.status == "ready", TimedParkingPass.start_at <= at,
        TimedParkingPass.arrival_deadline > at).order_by(TimedParkingPass.id).with_for_update()
        .execution_options(populate_existing=True)).all()
    if not tickets:
        return None
    ticket = tickets[0]
    if not ticket.start_at <= server_now() < ticket.arrival_deadline:
        raise HTTPException(409, "Vé trả trước chưa đến giờ hoặc đã hết hạn trong khi nhận xe.")
    order = db.get(PortalOrder, ticket.order_id)
    reservation = db.get(ParkingReservation, ticket.reservation_id)
    if (ticket.slot_id != slot_id or ticket.vehicle_type_id != vehicle.vehicle_type_id
            or order.status != "fulfilled" or not order.receipt_id or reservation.status != "confirmed"):
        raise HTTPException(409, "Vé trả trước phải được nhận đúng chỗ và còn hiệu lực.")
    return dict(billing_policy_version=PREPAID_POLICY_VERSION, rate_config_id=ticket.rate_config_id,
        rate_ticket_type=ticket.rate_ticket_type, rate_unit_price=ticket.rate_unit_price,
        rate_effective_date=ticket.rate_effective_date, timed_pass_id=ticket.id,
        prepaid_start_at=ticket.start_at, prepaid_end_at=ticket.end_at)


def consume(db, session):
    if session.timed_pass_id is None:
        return
    ticket = db.get(TimedParkingPass, session.timed_pass_id)
    if ticket.status != "ready" or ticket.session_id is not None:
        raise HTTPException(409, "Vé trả trước đã được sử dụng.")
    ticket.status, ticket.session_id = "consumed", session.id
    db.flush()


def revoke(db, order):
    ticket = db.get(TimedParkingPass, order.timed_pass_id)
    if ticket.status != "ready" or business_now() >= ticket.start_at:
        raise HTTPException(409, "Chỉ được hoàn vé chưa sử dụng và chưa đến giờ hẹn.")
    ticket.status = "revoked"
    db.get(ParkingReservation, ticket.reservation_id).status = "cancelled"
    db.flush()


def aware(value):
    return value.replace(tzinfo=BUSINESS_TZ) if value is not None and value.tzinfo is None else value


def prepaid(session):
    if session.timed_pass_id is None:
        return None
    db = object_session(session)
    ticket = db.get(TimedParkingPass, session.timed_pass_id)
    order = db.get(PortalOrder, ticket.order_id)
    return _prepaid_from(ticket, order)


def _prepaid_from(ticket, order):
    return dict(order_id=order.id, timed_pass_id=ticket.id, amount=order.amount,
        start_at=aware(ticket.start_at), end_at=aware(ticket.end_at), payment_mode=order.payment_mode,
        receipt_id=order.receipt_id)


def prepaid_many(db, sessions):
    ids = {row.timed_pass_id for row in sessions if row.timed_pass_id is not None}
    if not ids:
        return {}
    items = {ticket.id: _prepaid_from(ticket, order) for ticket, order in db.execute(
        select(TimedParkingPass, PortalOrder).join(PortalOrder, PortalOrder.id == TimedParkingPass.order_id)
        .where(TimedParkingPass.id.in_(ids)))}
    return {row.id: items.get(row.timed_pass_id) for row in sessions}


def ticket_status(ticket, now):
    return "expired" if ticket.status == "ready" and ticket.arrival_deadline <= now else ticket.status


def order_details_many(db, orders):
    ticket_ids = {row.timed_pass_id for row in orders if row.timed_pass_id is not None}
    slot_ids = {row.slot_id for row in orders if row.slot_id is not None}
    tickets = {row.id: row for row in db.scalars(select(TimedParkingPass).where(TimedParkingPass.id.in_(ticket_ids)))} if ticket_ids else {}
    slots = {slot.id: (slot, zone) for slot, zone in db.execute(select(ParkingSlot, Zone).join(Zone)
        .where(ParkingSlot.id.in_(slot_ids)))} if slot_ids else {}
    online_ids = [row.id for row in orders if row.payment_mode == "payos"]
    linked = set()
    if online_ids:
        from expansion.online_payment_models import OnlinePaymentLink
        linked = set(db.scalars(select(OnlinePaymentLink.order_id).where(OnlinePaymentLink.order_id.in_(online_ids))))
    return {row.id: order_details(row, related=(tickets, slots, linked)) for row in orders}


def order_details(order, *, related=None):
    db = object_session(order)
    now = business_now()
    if related is not None:
        ticket = related[0].get(order.timed_pass_id)
        slot, zone = related[1].get(order.slot_id, (None, None))
    else:
        ticket = db.get(TimedParkingPass, order.timed_pass_id) if order.timed_pass_id else None
        slot = db.get(ParkingSlot, order.slot_id) if order.slot_id else None
        zone = db.get(Zone, order.zone_id) if order.zone_id else None
    actions = []
    from expansion.online_payment_service import can_cancel_portal_order_locally
    if order.status in {"pending", "expired"} and can_cancel_portal_order_locally(order,
            linked_order_ids=related[2] if related is not None and len(related) > 2 else None):
        actions.append("cancel")
    if order.status == "pending" and order.payment_mode == "demo" and now < order.expires_at:
        actions.append("simulate")
    if order.status == "fulfilled" and order.receipt_id is not None and (ticket is None or ticket.status == "ready" and now < ticket.start_at):
        actions.append("request_refund")
    return dict(product_kind=order.product_kind, plan_name=order.plan_name, duration_minutes=order.duration_minutes,
        duration_days=order.duration_days, start_at=aware(order.start_at), end_at=aware(order.end_at),
        hold_expires_at=aware(order.expires_at) if order.product_kind != "monthly" else None,
        arrival_deadline=aware(order.arrival_deadline), reservation_id=ticket.reservation_id if ticket else None,
        timed_pass_id=order.timed_pass_id, entitlement_status=ticket_status(ticket, now) if ticket else None,
        slot=dict(id=slot.id, name=slot.slot_name, zone_id=zone.id, zone_name=zone.name) if slot else None,
        overstay_basis=dict(policy_version=PREPAID_POLICY_VERSION, rate_id=order.rate_config_id,
            ticket_type=order.rate_ticket_type, unit_price=order.rate_unit_price,
            effective_date=order.rate_effective_date) if order.rate_config_id else None,
        allowed_actions=actions, server_now=aware(now))
