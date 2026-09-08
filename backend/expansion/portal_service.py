"""Customer authority, frozen subscriptions and atomic demo collection.

Public write functions own commit/rollback. Payment events are committed before
fulfillment so a crash never discards an accepted simulator result.
"""
from datetime import timedelta
import uuid

from fastapi import HTTPException
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError

from core.clock import business_now
from expansion.gateway import DemoGateway
from expansion.portal_models import (
    PortalAccountLink, PortalLinkRequest, PortalVehicleRequest, PortalVehicleOwnership,
    PortalSessionGrant, SubscriptionPlan, PortalOrder, PortalPaymentEvent,
    PortalNotification, PortalRefundRequest,
)
from expansion.site_models import ParkingSite
from expansion.site_scope import require_site_access, require_public_site, is_global_admin
from models.customer import Customer
from models.vehicle import Vehicle
from models.vehicle_type import VehicleType
from models.monthly_pass import MonthlyPass
from models.parking_card import ParkingCard
from models.parking_session import ParkingSession
from models.payment import Payment
from models.user import User
from services.auth_service import check_permission
from services.payment_service import PaymentService, lock_cash_operator
from services.monthly_subscription_service import _lock_vehicle


def get_linked_customer(db, user):
    customer = db.scalar(select(Customer).join(PortalAccountLink,
        PortalAccountLink.customer_id == Customer.id).where(PortalAccountLink.user_id == user.id))
    if customer is None:
        raise HTTPException(409, "Hồ sơ chưa được liên kết. Hãy tạo hồ sơ mới hoặc gửi yêu cầu xác minh.")
    return customer


def require_owned_vehicle(db, user, vehicle_id):
    customer = get_linked_customer(db, user)
    vehicle = db.scalar(select(Vehicle).join(PortalVehicleOwnership,
        PortalVehicleOwnership.vehicle_id == Vehicle.id).where(Vehicle.id == vehicle_id,
        Vehicle.customer_id == customer.id, PortalVehicleOwnership.customer_id == customer.id))
    if vehicle is None:
        raise HTTPException(404, "Không tìm thấy xe đã được duyệt trong hồ sơ của bạn.")
    return vehicle


def capture_session_ownership(db, session):
    """Call after check-in flush, before commit. Never backfill earlier sessions."""
    if db.get(PortalSessionGrant, session.id) is not None:
        return
    owner = db.scalar(select(PortalVehicleOwnership).join(Vehicle,
        Vehicle.id == PortalVehicleOwnership.vehicle_id).where(
        Vehicle.id == session.vehicle_id, Vehicle.customer_id == PortalVehicleOwnership.customer_id,
        PortalVehicleOwnership.approved_at <= session.check_in_time))
    if owner is not None:
        db.add(PortalSessionGrant(parking_session_id=session.id, customer_id=owner.customer_id))
        db.flush()


def _notify(db, customer_id, key, message):
    if not db.scalar(select(PortalNotification.id).where(PortalNotification.event_key == key)):
        db.add(PortalNotification(customer_id=customer_id, event_key=key, message=message))


def _locked(db, model, identity):
    if db.get_bind().dialect.name == "sqlite":
        db.execute(update(model).where(model.id == identity).values(id=model.id))
    return db.scalar(select(model).where(model.id == identity).with_for_update().execution_options(populate_existing=True))


def _require_independent_reviewer(db, actor, *, requester_user_id=None, customer_id=None, phone_number=None):
    if requester_user_id == actor.id:
        raise HTTPException(403, "Người gửi yêu cầu không được tự duyệt yêu cầu của mình.")
    query = select(PortalAccountLink.id).where(PortalAccountLink.user_id == actor.id)
    if customer_id is not None:
        query = query.where(PortalAccountLink.customer_id == customer_id)
    elif phone_number is not None:
        query = query.join(Customer, Customer.id == PortalAccountLink.customer_id).where(
            Customer.phone_number == phone_number,
        )
    else:
        return
    if db.scalar(query.limit(1)) is not None:
        raise HTTPException(403, "Người có liên kết với hồ sơ không được tự duyệt yêu cầu này.")


def create_profile(db, user, data):
    lock_cash_operator(db, user.id)
    if db.scalar(select(PortalAccountLink.id).where(PortalAccountLink.user_id == user.id)):
        raise HTTPException(409, "Tài khoản đã có hồ sơ được liên kết.")
    if db.scalar(select(Customer.id).where(Customer.phone_number == data.phone_number)):
        raise HTTPException(409, "Không thể tạo hồ sơ với thông tin này. Hãy gửi yêu cầu xác minh liên kết.")
    try:
        customer = Customer(**data.model_dump())
        db.add(customer)
        db.flush()
        db.add(PortalAccountLink(user_id=user.id, customer_id=customer.id, verification="new_empty_profile"))
        db.commit()
        return customer
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(409, "Không thể tạo hồ sơ với thông tin này. Hãy gửi yêu cầu xác minh liên kết.") from exc


def request_link(db, user, data):
    lock_cash_operator(db, user.id)
    if db.scalar(select(PortalAccountLink.id).where(PortalAccountLink.user_id == user.id)):
        raise HTTPException(409, "Tài khoản đã được liên kết.")
    existing = db.scalar(select(PortalLinkRequest).where(PortalLinkRequest.user_id == user.id,
        PortalLinkRequest.status == "pending"))
    if existing:
        return existing
    item = PortalLinkRequest(user_id=user.id, **data.model_dump())
    db.add(item)
    db.commit()
    return item


def resolve_link(db, actor, identity, approve):
    check_permission(actor, "manager")
    item = db.get(PortalLinkRequest, identity)
    if item is None:
        raise HTTPException(404, "Không tìm thấy yêu cầu.")
    _require_independent_reviewer(
        db,
        actor,
        requester_user_id=item.user_id,
        phone_number=item.phone_number,
    )
    lock_cash_operator(db, item.user_id)
    item = _locked(db, PortalLinkRequest, identity)
    if item.status != "pending":
        if (item.status == "approved") != approve:
            raise HTTPException(409, "Yêu cầu đã được xử lý.")
        return item
    try:
        if approve:
            customer = db.scalar(select(Customer).where(Customer.phone_number == item.phone_number).with_for_update())
            if customer is None:
                raise HTTPException(409, "Chưa có hồ sơ tương ứng để xác minh; hãy yêu cầu khách tạo hồ sơ mới.")
            if db.scalar(select(PortalAccountLink.id).where(
                (PortalAccountLink.user_id == item.user_id) | (PortalAccountLink.customer_id == customer.id))):
                raise HTTPException(409, "Hồ sơ hoặc tài khoản đã có liên kết; không thể chuyển quyền tự động.")
            db.add(PortalAccountLink(user_id=item.user_id, customer_id=customer.id,
                verified_by_id=actor.id, verification="manager_approved"))
            _notify(db, customer.id, f"link:{item.id}", "Yêu cầu liên kết hồ sơ đã được quản lý duyệt.")
        item.status = "approved" if approve else "rejected"
        item.reviewed_by_id = actor.id
        db.commit()
        return item
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(409, "Hồ sơ hoặc tài khoản đã được liên kết bởi yêu cầu khác.") from exc


def request_vehicle(db, user, data):
    lock_cash_operator(db, user.id)
    customer = get_linked_customer(db, user)
    vehicle_type = db.get(VehicleType, data.vehicle_type_id)
    if vehicle_type is None or not vehicle_type.is_active:
        raise HTTPException(404, "Loại xe không hoạt động.")
    existing = db.scalar(select(PortalVehicleRequest).where(PortalVehicleRequest.customer_id == customer.id,
        PortalVehicleRequest.license_plate == data.license_plate, PortalVehicleRequest.status == "pending"))
    if existing:
        return existing
    item = PortalVehicleRequest(customer_id=customer.id, **data.model_dump())
    db.add(item)
    db.commit()
    return item


def resolve_vehicle(db, actor, identity, approve):
    check_permission(actor, "manager")
    # Serialize managers before FK writes and plate creation. The unique plate is
    # the final cross-manager race guard; no approval ever reassigns another owner.
    item = db.get(PortalVehicleRequest, identity)
    if item is None:
        raise HTTPException(404, "Không tìm thấy yêu cầu.")
    _require_independent_reviewer(db, actor, customer_id=item.customer_id)
    lock_cash_operator(db, actor.id)
    item = _locked(db, PortalVehicleRequest, identity)
    if item.status != "pending":
        if (item.status == "approved") != approve:
            raise HTTPException(409, "Yêu cầu đã được xử lý.")
        return item
    try:
        if approve:
            vehicle = db.scalar(select(Vehicle).where(Vehicle.license_plate == item.license_plate).with_for_update())
            if vehicle is None:
                vehicle = Vehicle(license_plate=item.license_plate, vehicle_type_id=item.vehicle_type_id,
                    customer_id=item.customer_id)
                db.add(vehicle)
                db.flush()
            elif vehicle.customer_id not in {None, item.customer_id} or vehicle.vehicle_type_id != item.vehicle_type_id:
                raise HTTPException(409, "Xe đang thuộc hồ sơ khác hoặc sai loại; cần quy trình chuyển chủ riêng.")
            vehicle.customer_id = item.customer_id
            if not db.scalar(select(PortalVehicleOwnership.id).where(
                PortalVehicleOwnership.customer_id == item.customer_id, PortalVehicleOwnership.vehicle_id == vehicle.id)):
                db.add(PortalVehicleOwnership(customer_id=item.customer_id, vehicle_id=vehicle.id, approved_by_id=actor.id))
        item.status = "approved" if approve else "rejected"
        item.reviewed_by_id = actor.id
        _notify(db, item.customer_id, f"vehicle-request:{item.id}",
            "Yêu cầu phương tiện đã được duyệt." if approve else "Yêu cầu phương tiện bị từ chối; hãy liên hệ quản lý.")
        db.commit()
        return item
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(409, "Phương tiện vừa được cập nhật bởi yêu cầu khác; hãy tải lại.") from exc


def unlink_account(db, actor, user_id):
    check_permission(actor, "admin")
    lock_cash_operator(db, user_id)
    if db.get_bind().dialect.name == "sqlite":
        db.execute(update(PortalAccountLink).where(
            PortalAccountLink.user_id == user_id,
        ).values(id=PortalAccountLink.id))
    link = db.scalar(select(PortalAccountLink).where(
        PortalAccountLink.user_id == user_id,
    ).with_for_update().execution_options(populate_existing=True))
    if link is None:
        raise HTTPException(404, "Tài khoản chưa có liên kết hồ sơ.")
    db.delete(link)
    db.commit()


def create_plan(db, actor, data):
    check_permission(actor, "manager")
    if data.site_id is None:
        if not is_global_admin(actor):
            raise HTTPException(403, "Chỉ quản trị viên được tạo gói chưa gán bãi.")
    else:
        require_site_access(db, actor, data.site_id, "manager")
    kind = db.get(VehicleType, data.vehicle_type_id)
    if kind is None or not kind.is_active:
        raise HTTPException(404, "Loại xe không hoạt động.")
    plan = SubscriptionPlan(**data.model_dump())
    db.add(plan)
    db.commit()
    return plan


def owned_order(db, user, identity):
    customer = get_linked_customer(db, user)
    order = db.scalar(select(PortalOrder).where(PortalOrder.id == identity,
        PortalOrder.user_id == user.id, PortalOrder.customer_id == customer.id))
    if order is None:
        raise HTTPException(404, "Không tìm thấy đơn của bạn.")
    if order.status == "pending" and order.expires_at < business_now():
        order = _lock_order_context(db, identity)
        if _expire_order_if_due(db, order):
            db.commit()
    return order


def _expire_order_if_due(db, order, now=None):
    now = now or business_now()
    if order.status != "pending" or order.expires_at >= now:
        return False
    has_event = db.scalar(select(PortalPaymentEvent.id).where(
        PortalPaymentEvent.order_id == order.id,
    ).limit(1))
    if has_event is not None:
        return False
    order.status = "expired"
    db.flush()
    return True


def create_order(db, user, data):
    gateway = DemoGateway()
    if data.payment_mode == "demo":
        gateway.require_enabled()
    lock_cash_operator(db, user.id)
    vehicle = require_owned_vehicle(db, user, data.vehicle_id)
    _lock_vehicle(db, vehicle.id)
    db.refresh(vehicle)
    customer = get_linked_customer(db, user)
    if vehicle.customer_id != customer.id:
        raise HTTPException(409, "Quyền sở hữu phương tiện vừa thay đổi.")
    existing = db.scalar(select(PortalOrder).where(PortalOrder.user_id == user.id,
        PortalOrder.idempotency_key == data.idempotency_key))
    if existing:
        if (existing.plan_id, existing.vehicle_id, existing.payment_mode) != (data.plan_id, data.vehicle_id, data.payment_mode):
            raise HTTPException(409, "Mã yêu cầu đã được sử dụng cho đơn khác.")
        return existing
    plan = db.get(SubscriptionPlan, data.plan_id)
    if plan is None or not plan.is_active or plan.site_id is None or plan.vehicle_type_id != vehicle.vehicle_type_id:
        raise HTTPException(409, "Gói không hoạt động, chưa gán bãi hoặc không phù hợp loại xe.")
    require_public_site(db, plan.site_id)
    now = business_now()
    pending = db.scalar(select(PortalOrder).where(PortalOrder.vehicle_id == vehicle.id,
        PortalOrder.status.in_(["pending", "review"])).order_by(PortalOrder.created_at, PortalOrder.id))
    if pending is not None and pending.status == "pending":
        _expire_order_if_due(db, pending, now)
    if pending is not None and pending.status in {"pending", "review"}:
        raise HTTPException(409, "Xe còn đơn đang chờ xử lý; hãy hoàn tất hoặc hủy trước khi tạo đơn mới.")
    latest = db.scalar(select(MonthlyPass).where(MonthlyPass.vehicle_id == vehicle.id,
        MonthlyPass.is_active.is_(True)).order_by(MonthlyPass.end_date.desc()).limit(1))
    if latest and latest.end_date >= now.date() and latest.customer_id != customer.id:
        raise HTTPException(409, "Xe còn kỳ vé của chủ trước; quản lý cần xử lý trước khi cấp kỳ mới.")
    start = max(now.date(), latest.end_date + timedelta(days=1)) if latest else now.date()
    card = db.scalar(select(ParkingCard).where(ParkingCard.customer_id == customer.id,
        ParkingCard.vehicle_id == vehicle.id).order_by(ParkingCard.id.desc()).limit(1))
    order = PortalOrder(id=str(uuid.uuid4()), user_id=user.id, customer_id=customer.id,
        vehicle_id=vehicle.id, plan_id=plan.id, site_id=plan.site_id, card_id=card.id if card else None,
        amount=plan.price, start_date=start, end_date=start + timedelta(days=plan.duration_days - 1),
        payment_mode=data.payment_mode, idempotency_key=data.idempotency_key,
        expires_at=now + timedelta(minutes=gateway.settings.PORTAL_ORDER_TTL_MINUTES))
    if data.payment_mode == "demo":
        order.demo_token, _ = gateway.issue(order.id)
    db.add(order)
    db.commit()
    return order


def serialize_order(order, *, owner=False):
    fields = ["id", "status", "user_id", "customer_id", "vehicle_id", "plan_id", "site_id", "amount",
        "start_date", "end_date", "payment_mode", "expires_at", "created_at", "monthly_pass_id", "receipt_id", "review_reason"]
    data = {field: getattr(order, field) for field in fields}
    data["payment_label"] = "DEMO — không chuyển tiền thật" if order.payment_mode == "demo" else "Thu tiền tại bãi"
    if owner and order.demo_token and order.status == "pending":
        data["demo_token"] = order.demo_token
        data["demo_payload"] = DemoGateway.payload(order.id, order.demo_token)
        data["demo_qr_svg"] = DemoGateway.qr_svg(data["demo_payload"])
    return data


def _lock_order_context(db, identity):
    order = db.get(PortalOrder, identity)
    if order is None:
        raise HTTPException(404, "Không tìm thấy đơn.")
    lock_cash_operator(db, order.user_id)
    _lock_vehicle(db, order.vehicle_id)
    return _locked(db, PortalOrder, identity)


def _fulfillment_problem(db, order, *, paid_at=None):
    """`paid_at` is when the payment result was received; a result inside the order's
    validity window may cross midnight without turning the start date into a problem."""
    vehicle = db.get(Vehicle, order.vehicle_id)
    site = db.get(ParkingSite, order.site_id)
    if vehicle.customer_id != order.customer_id:
        return "vehicle_owner_changed"
    if site is None or not site.is_active:
        return "site_inactive"
    paid_at = paid_at or business_now()
    if paid_at.date() > order.start_date and paid_at > order.expires_at:
        return "start_date_passed"
    overlap = db.scalar(select(MonthlyPass.id).where(MonthlyPass.vehicle_id == order.vehicle_id,
        MonthlyPass.is_active.is_(True), MonthlyPass.start_date <= order.end_date, MonthlyPass.end_date >= order.start_date))
    return "period_overlap" if overlap else None


def _fulfill(db, order, *, method, collector):
    card = db.get(ParkingCard, order.card_id) if order.card_id else None
    if card is None:
        card = ParkingCard(code="PORTAL-" + uuid.uuid4().hex.upper(), customer_id=order.customer_id,
            vehicle_id=order.vehicle_id)
        db.add(card)
        db.flush()
        order.card_id = card.id
    period = MonthlyPass(customer_id=order.customer_id, vehicle_id=order.vehicle_id, card_id=card.id,
        pass_code="KY-" + uuid.uuid4().hex.upper(), renewal_key="portal:" + order.id,
        price=order.amount, start_date=order.start_date, end_date=order.end_date, is_active=True)
    db.add(period)
    db.flush()
    receipt = PaymentService.record_receipt(db, source_type="monthly_pass", source_id=str(period.id),
        amount=order.amount, collected_by_id=collector, method=method)
    order.monthly_pass_id, order.receipt_id, order.status = period.id, receipt.id, "fulfilled"
    _notify(db, order.customer_id, f"order:{order.id}:fulfilled",
        "Đã kích hoạt kỳ vé bằng thanh toán DEMO; không có tiền thật được chuyển." if method == "demo" else "Đã thu tiền và kích hoạt kỳ vé.")


def process_event(db, event_id):
    event = db.get(PortalPaymentEvent, event_id)
    if event is None:
        return None
    order = _lock_order_context(db, event.order_id)
    event = _locked(db, PortalPaymentEvent, event_id)
    if event.status != "received":
        db.commit()
        return order
    if order.status in {"fulfilled", "refunded"}:
        event.status = "processed"
    elif event.outcome != "success":
        order.status = event.outcome
        event.status = "processed"
    else:
        problem = "late_payment" if event.received_at > order.expires_at else _fulfillment_problem(db, order, paid_at=event.received_at)
        if event.amount != order.amount:
            problem = "amount_mismatch"
        if problem:
            event.status, event.error_code = "review", problem
            order.status, order.review_reason = "review", problem
            _notify(db, order.customer_id, f"order:{order.id}:review", "Kết quả DEMO cần quản lý kiểm tra; kỳ vé chưa được kích hoạt.")
        else:
            _fulfill(db, order, method="demo", collector=None)
            event.status = "processed"
    db.commit()
    return order


def simulate(db, user, identity, data):
    DemoGateway().require_enabled()
    owned_order(db, user, identity)
    order = _lock_order_context(db, identity)
    if order.payment_mode != "demo" or not DemoGateway.verify(order.demo_token or "", data.token):
        raise HTTPException(403, "Mã mô phỏng không hợp lệ cho đơn này.")
    event = db.scalar(select(PortalPaymentEvent).where(PortalPaymentEvent.provider == "demo",
        PortalPaymentEvent.reference == "demo:" + order.id))
    if event:
        if event.outcome != data.outcome:
            raise HTTPException(409, "Mã mô phỏng đã được dùng với kết quả khác.")
    else:
        if order.status not in {"pending", "expired"}:
            raise HTTPException(409, "Đơn đã được xử lý.")
        event = PortalPaymentEvent(order_id=order.id, reference="demo:" + order.id,
            outcome=data.outcome, amount=order.amount)
        db.add(event)
        db.commit()  # durable inbox before fulfillment, including crash recovery
    event_id = event.id
    try:
        return process_event(db, event_id)
    except Exception:
        db.rollback()
        event = db.get(PortalPaymentEvent, event_id)
        if event and event.status == "received":
            event.attempts += 1
            event.error_code = "fulfillment_retry"
            event.next_attempt_at = business_now() + timedelta(seconds=min(300, 2 ** min(event.attempts, 8)))
            db.commit()
        raise HTTPException(503, "Đã lưu kết quả DEMO; hệ thống sẽ thử xử lý lại. Không tạo thanh toán mới.") from None


def collect_manual(db, actor, identity, method):
    check_permission(actor, "manager")
    order = db.get(PortalOrder, identity)
    if order is None:
        raise HTTPException(404, "Không tìm thấy đơn.")
    require_site_access(db, actor, order.site_id, "manager")
    lock_cash_operator(db, actor.id)
    order = _lock_order_context(db, identity)
    if order.payment_mode != "manual":
        raise HTTPException(409, "Đơn DEMO không thể ghi nhận thành thu tiền thật.")
    if order.status == "fulfilled":
        receipt = db.get(Payment, order.receipt_id)
        if receipt.method != method or receipt.collected_by_id != actor.id:
            raise HTTPException(409, "Đơn đã được thu với thông tin khác.")
        return order
    if order.status != "pending" or business_now() > order.expires_at:
        raise HTTPException(409, "Đơn không còn chờ thu hoặc đã hết hạn.")
    problem = _fulfillment_problem(db, order)
    if problem:
        raise HTTPException(409, "Thông tin xe hoặc kỳ vé đã thay đổi; cần tạo đơn mới trước khi thu.")
    _fulfill(db, order, method=method, collector=actor.id)
    db.commit()
    return order


def request_refund(db, user, identity, reason):
    owned_order(db, user, identity)
    order = _lock_order_context(db, identity)
    if order.status != "fulfilled" or order.payment_mode != "demo":
        raise HTTPException(409, "Chỉ hỗ trợ yêu cầu hoàn mô phỏng cho đơn DEMO đã kích hoạt.")
    existing = db.scalar(select(PortalRefundRequest).where(PortalRefundRequest.order_id == identity))
    if existing:
        return existing
    item = PortalRefundRequest(order_id=identity, customer_id=order.customer_id, reason=reason)
    db.add(item)
    db.commit()
    return item


def resolve_refund(db, actor, identity, data):
    check_permission(actor, "manager")
    item = db.get(PortalRefundRequest, identity)
    if item is None:
        raise HTTPException(404, "Không tìm thấy yêu cầu.")
    order = db.get(PortalOrder, item.order_id)
    require_site_access(db, actor, order.site_id, "manager")
    lock_cash_operator(db, actor.id)
    order = _lock_order_context(db, item.order_id)
    item = _locked(db, PortalRefundRequest, identity)
    if item.status != "pending":
        if (item.status == "approved") != data.approve:
            raise HTTPException(409, "Yêu cầu đã được xử lý.")
        return item
    if data.approve:
        if order.payment_mode != "demo" or order.status != "fulfilled":
            raise HTTPException(409, "Đơn không đủ điều kiện hoàn mô phỏng.")
        if db.scalar(select(ParkingSession.id).where(
            (ParkingSession.monthly_pass_id == order.monthly_pass_id) |
            ((ParkingSession.vehicle_id == order.vehicle_id) & (ParkingSession.monthly_coverage_end >= order.start_date)),
            ParkingSession.status.in_(["active", "checking_out"]))):
            raise HTTPException(409, "Kỳ vé đang được dùng cho xe trong bãi; hãy hoàn tất lượt gửi trước.")
        refund = PaymentService.refund(db, order.receipt_id, actor, amount=order.amount, method="demo",
            reason="DEMO: " + item.reason[:490], idempotency_key="portal-" + item.id)
        db.get(MonthlyPass, order.monthly_pass_id).is_active = False
        order.status = "refunded"
        item.refund_payment_id = refund.id
    item.status = "approved" if data.approve else "rejected"
    item.note, item.reviewed_by_id = data.note, actor.id
    _notify(db, item.customer_id, f"refund:{item.id}",
        "Đã hoàn mô phỏng và dừng kỳ vé; không có tiền thật được chuyển." if data.approve else "Yêu cầu hoàn mô phỏng bị từ chối.")
    db.commit()
    return item


def update_plan(db, actor, identity, data):
    check_permission(actor, "manager")
    plan = _locked(db, SubscriptionPlan, identity)
    if plan is None:
        raise HTTPException(404, "Không tìm thấy gói vé.")
    if plan.site_id is None:
        if not is_global_admin(actor):
            raise HTTPException(403, "Chỉ quản trị viên được sửa gói chưa gán bãi.")
    else:
        require_site_access(db, actor, plan.site_id, "manager")
    changes = data.model_dump(exclude_unset=True)
    if not changes or any(value is None for value in changes.values()):
        raise HTTPException(422, "Cần ít nhất một giá trị cập nhật không rỗng.")
    for name, value in changes.items():
        setattr(plan, name, value)
    db.commit()
    return plan


def cancel_order(db, user, identity):
    owned_order(db, user, identity)
    order = _lock_order_context(db, identity)
    if order.status == "cancelled":
        db.commit()
        return order
    if order.status not in {"pending", "expired"} or db.scalar(select(PortalPaymentEvent.id).where(PortalPaymentEvent.order_id == identity)):
        raise HTTPException(409, "Đơn đã có kết quả thanh toán; không thể hủy trực tiếp.")
    order.status = "cancelled"
    db.commit()
    return order


def resolve_review(db, actor, identity, data):
    check_permission(actor, "manager")
    order = db.get(PortalOrder, identity)
    if order is None:
        raise HTTPException(404, "Không tìm thấy đơn.")
    require_site_access(db, actor, order.site_id, "manager")
    lock_cash_operator(db, actor.id)
    order = _lock_order_context(db, identity)
    if order.status != "review" or order.payment_mode != "demo":
        raise HTTPException(409, "Đơn không đang chờ xét duyệt DEMO.")
    if not data.note.strip():
        raise HTTPException(422, "Cần ghi lý do xét duyệt.")
    event = db.scalar(select(PortalPaymentEvent).where(PortalPaymentEvent.order_id == order.id,
        PortalPaymentEvent.outcome == "success").with_for_update())
    if event is None:
        raise HTTPException(409, "Chưa có kết quả mô phỏng thành công.")
    if data.approve:
        if event.amount != order.amount or _fulfillment_problem(db, order, paid_at=event.received_at):
            raise HTTPException(409, "Số tiền, quyền sở hữu hoặc kỳ vé không còn phù hợp; hãy từ chối để tạo đơn mới.")
        _fulfill(db, order, method="demo", collector=None)
    else:
        order.status = "cancelled"
    event.status = "processed"
    # No bank refund is implied by rejection of a simulated transaction.
    order.review_reason = f"manager:{actor.id}:" + data.note[:70]
    _notify(db, order.customer_id, f"order:{order.id}:review-resolved",
        "Quản lý đã xử lý kết quả DEMO. " + ("Kỳ vé đã được kích hoạt." if data.approve else "Đơn mô phỏng đã hủy, không có hoàn tiền ngân hàng."))
    db.commit()
    return order
