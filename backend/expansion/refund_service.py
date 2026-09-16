"""Receipt-based refund requests for DEMO, counter and online payments.

The server decides everything financial: which receipt is the original, how
much was actually collected, how much was already refunded and how much may
still be refunded. Approval is a decision record; money only moves when a
compensating ``payments`` row is written through ``PaymentService.refund``
(DEMO immediately, actual channels when a manager records the external
refund with a reference). Existing entitlement guards are reused: an unused
timed ticket is revoked, a monthly pass is deactivated, a session credit is
only refundable for the part that was not applied to the parking fee.
"""
from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from core.clock import BUSINESS_TZ, business_now
from core.money import sum_exact_vnd
from expansion import customer_ownership as ownership
from expansion.online_payment_models import OnlinePaymentInbox, OnlinePaymentLink, OnlinePaymentProcessing
from expansion.portal_models import PortalOrder, PortalRefundRequest
from expansion.portal_service import _locked, _notify, _require_independent_reviewer, get_linked_customer
from expansion.session_payment_models import SessionFeeCredit
from expansion.site_scope import require_site_access
from expansion.support_models import PaymentRefundRequest, REFUND_OPEN_STATES
from expansion.timed_parking_models import TimedParkingPass
from models.customer import Customer
from models.monthly_pass import MonthlyPass
from models.parking_session import ParkingSession
from models.payment import Payment
from services.payment_service import PaymentService, lock_cash_operator

BLOCKED_LABELS = {
    "not_a_receipt": "Chỉ phiếu thu gốc mới có thể hoàn.",
    "fully_refunded": "Khoản thu này đã được hoàn hết.",
    "request_open": "Đang có yêu cầu hoàn chưa xử lý cho khoản thu này.",
    "ticket_missing": "Không tìm thấy vé tương ứng với khoản thu.",
    "ticket_used": "Vé đã được sử dụng nên không hoàn.",
    "ticket_expired": "Vé đã hết hiệu lực nên không hoàn.",
    "ticket_revoked": "Vé đã bị thu hồi.",
    "ticket_window_started": "Đã tới giờ hẹn của vé; không hoàn sau khi khung giờ bắt đầu.",
    "pass_inactive": "Kỳ vé tháng không còn hiệu lực.",
    "pass_in_use": "Kỳ vé đang được dùng cho xe trong bãi; hãy hoàn tất lượt gửi trước.",
    "session_not_completed": "Lượt gửi chưa kết thúc; chỉ hoàn sau khi xe đã ra.",
    "credit_applied": "Khoản trả online đã được áp dụng vào phí lượt gửi; không còn phần dư để hoàn.",
    "under_reconciliation": "Khoản thanh toán đang được đối soát với ngân hàng; hãy chờ kết quả.",
    "legacy_receipt": "Chứng từ lịch sử không hoàn qua cổng khách; hãy liên hệ quản lý.",
}
STATUS_LABELS = {"pending": "Đã tiếp nhận", "reviewing": "Đang xem xét", "approved": "Được duyệt, chờ hoàn",
    "rejected": "Bị từ chối", "refunded": "Đã hoàn tiền"}


def _aware(value):
    return value.replace(tzinfo=BUSINESS_TZ) if value is not None and value.tzinfo is None else value


def refunded_sum(db, receipt_id):
    return sum_exact_vnd(db.execute(select(Payment.amount).where(
        Payment.original_payment_id == receipt_id, Payment.kind == "refund")).scalars())


def _online_link(db, receipt):
    return db.scalar(select(OnlinePaymentLink).where(OnlinePaymentLink.receipt_id == receipt.id))


def payment_channel(db, receipt, link=None):
    if receipt.method == "demo":
        return "demo"
    if receipt.method == "legacy_unknown":
        return "legacy"
    link = link if link is not None else _online_link(db, receipt)
    return "online" if link is not None else "counter"


def _credit_surplus(db, credit):
    """Part of the online credits that exceeded the final parking fee of a completed session."""
    session = db.get(ParkingSession, credit.session_id)
    if session is None or session.status != "completed" or session.parking_fee is None:
        return None, "session_not_completed"
    credits = list(db.scalars(select(SessionFeeCredit).where(SessionFeeCredit.session_id == session.id,
        SessionFeeCredit.receipt_id.is_not(None))))
    total = sum_exact_vnd(row.amount for row in credits)
    already = sum_exact_vnd(refunded_sum(db, row.receipt_id) for row in credits)
    surplus = total - session.parking_fee - already
    return max(surplus, 0), None


def refund_state(db, receipt, *, except_request=None):
    """Server-side truth about how much of a receipt may still be refunded and why not."""
    refunded = refunded_sum(db, receipt.id)
    remaining = receipt.amount - refunded
    link = _online_link(db, receipt)
    state = {"receipt_id": receipt.id, "amount": receipt.amount, "refunded_amount": refunded,
        "refundable_amount": 0, "payment_channel": payment_channel(db, receipt, link),
        "blocked_reason": None, "open_request_id": None, "eligible": False}
    blocked, refundable = None, remaining
    if receipt.kind != "receipt":
        blocked = "not_a_receipt"
    elif remaining <= 0:
        blocked = "fully_refunded"
    elif receipt.method == "legacy_unknown":
        blocked = "legacy_receipt"
    elif receipt.source_type == "portal_order":
        order = db.get(PortalOrder, receipt.source_id)
        ticket = db.get(TimedParkingPass, order.timed_pass_id) if order and order.timed_pass_id else None
        if ticket is None:
            blocked = "ticket_missing"
        elif ticket.status != "ready":
            blocked = {"consumed": "ticket_used", "expired": "ticket_expired"}.get(ticket.status, "ticket_revoked")
        elif business_now() >= ticket.start_at or ticket.arrival_deadline <= business_now():
            blocked = "ticket_window_started"
    elif receipt.source_type == "monthly_pass":
        period = db.get(MonthlyPass, int(receipt.source_id))
        if period is None or not period.is_active:
            blocked = "pass_inactive"
        elif db.scalar(select(ParkingSession.id).where(
                (ParkingSession.monthly_pass_id == period.id) |
                ((ParkingSession.vehicle_id == period.vehicle_id) & (ParkingSession.monthly_coverage_end >= period.start_date)),
                ParkingSession.status.in_(["active", "checking_out"])).limit(1)):
            blocked = "pass_in_use"
    elif receipt.source_type == "session_credit":
        credit = db.get(SessionFeeCredit, receipt.source_id)
        surplus, problem = _credit_surplus(db, credit) if credit else (None, "session_not_completed")
        if problem:
            blocked = problem
        else:
            refundable = min(remaining, surplus)
            if refundable <= 0:
                blocked = "credit_applied"
    elif receipt.source_type == "parking_session":
        session = db.get(ParkingSession, receipt.source_id)
        if session is None or session.status != "completed":
            blocked = "session_not_completed"
    if blocked is None and link is not None:
        reviewing = link.state == "review" or db.scalar(select(OnlinePaymentProcessing.id).join(OnlinePaymentInbox,
            OnlinePaymentInbox.id == OnlinePaymentProcessing.id).where(OnlinePaymentInbox.link_id == link.id,
            OnlinePaymentProcessing.status == "review").limit(1)) is not None
        if reviewing:
            blocked = "under_reconciliation"
    open_query = select(PaymentRefundRequest).where(PaymentRefundRequest.receipt_id == receipt.id,
        PaymentRefundRequest.status.in_(REFUND_OPEN_STATES))
    if except_request is not None:
        open_query = open_query.where(PaymentRefundRequest.id != except_request)
    open_request = db.scalar(open_query)
    if open_request is not None:
        state["open_request_id"] = open_request.id
        blocked = blocked or "request_open"
    state["refundable_amount"] = refundable if blocked is None else 0
    state["blocked_reason"] = blocked
    state["blocked_label"] = BLOCKED_LABELS.get(blocked) if blocked else None
    state["eligible"] = blocked is None
    return state


def refund_states_many(db, user, customer, receipts):
    return {row.id: refund_state(db, row) for row in receipts}


def _open_request(db, receipt_id):
    return db.scalar(select(PaymentRefundRequest).where(PaymentRefundRequest.receipt_id == receipt_id,
        PaymentRefundRequest.status.in_(REFUND_OPEN_STATES)))


def create_request(db, user, receipt_id, reason):
    customer = get_linked_customer(db, user)
    receipt = ownership.owned_receipt(db, user, customer, receipt_id)
    if receipt is None:
        raise HTTPException(404, "Không tìm thấy chứng từ của bạn.")
    lock_cash_operator(db, user.id)
    existing = _open_request(db, receipt.id)
    if existing is not None:
        return existing
    state = refund_state(db, receipt)
    if not state["eligible"]:
        raise HTTPException(409, state["blocked_label"] or "Khoản thu này không đủ điều kiện hoàn.")
    now = business_now()
    item = PaymentRefundRequest(receipt_id=receipt.id, site_id=receipt.site_id, customer_id=customer.id, user_id=user.id,
        source_type=receipt.source_type, source_id=receipt.source_id, payment_channel=state["payment_channel"],
        receipt_method=receipt.method, reason=reason.strip(), requested_amount=state["refundable_amount"],
        created_at=now, updated_at=now)
    db.add(item)
    try:
        db.commit()
    except IntegrityError:
        # Two simultaneous requests for one receipt: the partial unique index keeps a single open request.
        db.rollback()
        existing = _open_request(db, receipt.id)
        if existing is None:
            raise HTTPException(409, "Không thể tạo yêu cầu hoàn lúc này; hãy tải lại và thử lại.") from None
        return existing
    return item


def _managed(db, actor, site_id, identity):
    require_site_access(db, actor, site_id, "manager")
    item = db.scalar(select(PaymentRefundRequest).where(PaymentRefundRequest.id == identity,
        PaymentRefundRequest.site_id == site_id))
    if item is None:
        raise HTTPException(404, "Không tìm thấy yêu cầu hoàn tại bãi này.")
    _require_independent_reviewer(db, actor, customer_id=item.customer_id)
    return item


def start_review(db, actor, site_id, identity, note=""):
    _managed(db, actor, site_id, identity)
    lock_cash_operator(db, actor.id)
    item = _locked(db, PaymentRefundRequest, identity)
    if item.status == "pending":
        item.status, item.reviewed_by_id, item.updated_at = "reviewing", actor.id, business_now()
        if note.strip():
            item.decision_note = note.strip()
        _notify(db, item.customer_id, f"refund:{item.id}:reviewing", "Yêu cầu hoàn tiền của bạn đang được quản lý xem xét.")
    elif item.status != "reviewing":
        raise HTTPException(409, "Yêu cầu đã có quyết định.")
    db.commit()
    return item


def reject(db, actor, site_id, identity, note):
    if len(note.strip()) < 3:
        raise HTTPException(422, "Cần ghi lý do từ chối.")
    _managed(db, actor, site_id, identity)
    lock_cash_operator(db, actor.id)
    item = _locked(db, PaymentRefundRequest, identity)
    if item.status == "rejected":
        db.commit()
        return item
    if item.status not in {"pending", "reviewing", "approved"}:
        raise HTTPException(409, "Yêu cầu đã hoàn tiền; không thể từ chối.")
    now = business_now()
    item.status, item.decision_note, item.reviewed_by_id, item.reviewed_at, item.updated_at = "rejected", note.strip(), actor.id, now, now
    _notify(db, item.customer_id, f"refund:{item.id}:rejected", "Yêu cầu hoàn tiền của bạn bị từ chối. Lý do: " + note.strip()[:200])
    db.commit()
    return item


def approve(db, actor, site_id, identity, *, amount=None, note=""):
    _managed(db, actor, site_id, identity)
    lock_cash_operator(db, actor.id)
    item = _locked(db, PaymentRefundRequest, identity)
    if item.status == "refunded" or (item.status == "approved" and amount in (None, item.approved_amount)):
        db.commit()
        return item
    if item.status not in {"pending", "reviewing"}:
        raise HTTPException(409, "Yêu cầu đã có quyết định khác.")
    receipt = db.get(Payment, item.receipt_id)
    state = refund_state(db, receipt, except_request=item.id)
    if not state["eligible"]:
        raise HTTPException(409, state["blocked_label"] or "Khoản thu không còn đủ điều kiện hoàn.")
    approved = state["refundable_amount"] if amount is None else amount
    if approved <= 0 or approved > state["refundable_amount"] or approved > item.requested_amount:
        raise HTTPException(409, "Số tiền duyệt vượt quá số còn có thể hoàn của khoản thu.")
    now = business_now()
    item.approved_amount, item.decision_note, item.reviewed_by_id, item.reviewed_at, item.updated_at = approved, note.strip(), actor.id, now, now
    if item.payment_channel == "demo":
        # Simulated money: the compensating DEMO ledger row is written at approval time.
        _execute_refund(db, actor, item, receipt, method="demo", external_reference=None)
        _notify(db, item.customer_id, f"refund:{item.id}:refunded",
            "Đã hoàn mô phỏng DEMO và dừng quyền sử dụng liên quan; không có tiền thật được chuyển.")
    else:
        item.status = "approved"
        _notify(db, item.customer_id, f"refund:{item.id}:approved",
            "Yêu cầu hoàn tiền đã được duyệt. Tiền sẽ được hoàn theo hình thức quản lý ghi nhận; duyệt chưa có nghĩa tiền đã về tài khoản.")
    db.commit()
    return item


def record_refund(db, actor, site_id, identity, *, method, external_reference=None):
    _managed(db, actor, site_id, identity)
    if method not in {"cash", "transfer"}:
        raise HTTPException(422, "Hình thức hoàn phải là tiền mặt hoặc chuyển khoản.")
    reference = (external_reference or "").strip() or None
    if method == "transfer" and (reference is None or len(reference) < 3):
        raise HTTPException(422, "Hoàn bằng chuyển khoản cần mã tham chiếu của giao dịch ngân hàng.")
    lock_cash_operator(db, actor.id)
    item = _locked(db, PaymentRefundRequest, identity)
    if item.status == "refunded":
        if item.refund_method != method or (item.external_reference or None) != reference:
            raise HTTPException(409, "Khoản hoàn đã được ghi nhận với thông tin khác.")
        db.commit()
        return item
    if item.status != "approved":
        raise HTTPException(409, "Chỉ ghi nhận hoàn cho yêu cầu đã được duyệt.")
    if item.payment_channel == "demo":
        raise HTTPException(409, "Khoản DEMO được hoàn mô phỏng ngay khi duyệt.")
    receipt = db.get(Payment, item.receipt_id)
    state = refund_state(db, receipt, except_request=item.id)
    if not state["eligible"] or item.approved_amount > state["refundable_amount"]:
        raise HTTPException(409, state["blocked_label"] or "Số tiền duyệt vượt quá số còn có thể hoàn.")
    _execute_refund(db, actor, item, receipt, method=method, external_reference=reference)
    _notify(db, item.customer_id, f"refund:{item.id}:refunded",
        "Quản lý đã ghi nhận hoàn tiền " + ("bằng chuyển khoản" if method == "transfer" else "bằng tiền mặt") + ". Xem chứng từ hoàn trong Lịch sử & chứng từ.")
    db.commit()
    return item


def _execute_refund(db, actor, item, receipt, *, method, external_reference):
    if receipt.source_type == "portal_order":
        from expansion.timed_parking_service import revoke
        order = db.get(PortalOrder, receipt.source_id)
        revoke(db, order)
        order.status = "refunded"
    elif receipt.source_type == "monthly_pass":
        period = db.get(MonthlyPass, int(receipt.source_id))
        period.is_active = False
        order = db.scalar(select(PortalOrder).where(PortalOrder.receipt_id == receipt.id))
        if order is not None:
            order.status = "refunded"
    refund = PaymentService.refund(db, receipt.id, actor, amount=item.approved_amount, method=method,
        reason=(f"Yêu cầu hoàn {item.id[:8]}: " + item.reason)[:500], idempotency_key="refund-request-" + item.id)
    now = business_now()
    item.status, item.refund_payment_id, item.refund_method = "refunded", refund.id, method
    item.external_reference, item.refunded_by_id, item.refunded_at, item.updated_at = external_reference, actor.id, now, now


def _order_ids(db, items):
    """Map receipt ids to the portal order that produced them (timed orders or monthly periods)."""
    receipt_ids = [row.receipt_id for row in items]
    if not receipt_ids:
        return {}
    return dict(db.execute(select(PortalOrder.receipt_id, PortalOrder.id).where(PortalOrder.receipt_id.in_(receipt_ids))).all())


def serialize(item, *, order_id=None, customer_name=None):
    return {"id": item.id, "receipt_id": item.receipt_id, "site_id": item.site_id, "customer_id": item.customer_id,
        "customer_name": customer_name, "order_id": order_id, "source_type": item.source_type, "source_id": item.source_id,
        "payment_channel": item.payment_channel, "receipt_method": item.receipt_method, "demo": item.payment_channel == "demo",
        "reason": item.reason, "requested_amount": item.requested_amount, "approved_amount": item.approved_amount,
        "status": item.status, "status_label": STATUS_LABELS.get(item.status, item.status),
        "note": item.decision_note, "decision_note": item.decision_note,
        "reviewed_at": _aware(item.reviewed_at), "refund_payment_id": item.refund_payment_id,
        "refund_method": item.refund_method, "external_reference": item.external_reference,
        "refunded_at": _aware(item.refunded_at), "created_at": _aware(item.created_at), "updated_at": _aware(item.updated_at),
        "legacy": False}


def serialize_legacy(row, *, customer_name=None):
    status = "refunded" if row.status == "approved" and row.refund_payment_id else row.status
    return {"id": row.id, "receipt_id": None, "site_id": None, "customer_id": row.customer_id, "customer_name": customer_name,
        "order_id": row.order_id, "source_type": "portal_order", "source_id": row.order_id, "payment_channel": "demo",
        "receipt_method": "demo", "demo": True, "reason": row.reason, "requested_amount": None, "approved_amount": None,
        "status": status, "status_label": STATUS_LABELS.get(status, status), "note": row.note, "decision_note": row.note,
        "reviewed_at": None, "refund_payment_id": row.refund_payment_id, "refund_method": "demo" if row.refund_payment_id else None,
        "external_reference": None, "refunded_at": None, "created_at": _aware(row.created_at), "updated_at": _aware(row.created_at),
        "legacy": True}


def customer_list(db, user, *, limit=100):
    customer = get_linked_customer(db, user)
    items = db.scalars(select(PaymentRefundRequest).where(PaymentRefundRequest.customer_id == customer.id)
        .order_by(PaymentRefundRequest.created_at.desc(), PaymentRefundRequest.id).limit(limit)).all()
    orders = _order_ids(db, items)
    legacy = db.scalars(select(PortalRefundRequest).where(PortalRefundRequest.customer_id == customer.id)
        .order_by(PortalRefundRequest.created_at.desc()).limit(limit)).all()
    rows = [serialize(row, order_id=orders.get(row.receipt_id)) for row in items] + [serialize_legacy(row) for row in legacy]
    rows.sort(key=lambda row: row["created_at"], reverse=True)
    return rows[:limit]


def manager_list(db, actor, site_id, *, status=None, limit=50, offset=0):
    require_site_access(db, actor, site_id, "manager")
    query = select(PaymentRefundRequest, Customer).join(Customer, Customer.id == PaymentRefundRequest.customer_id).where(
        PaymentRefundRequest.site_id == site_id)
    if status:
        query = query.where(PaymentRefundRequest.status == status)
    rows = db.execute(query.order_by(PaymentRefundRequest.created_at.desc(), PaymentRefundRequest.id)
        .offset(offset).limit(limit)).all()
    orders = _order_ids(db, [item for item, _ in rows])
    result = [serialize(item, order_id=orders.get(item.receipt_id), customer_name=customer.full_name) for item, customer in rows]
    if offset == 0 and status in (None, "", "pending"):
        legacy = db.execute(select(PortalRefundRequest, Customer).join(PortalOrder, PortalOrder.id == PortalRefundRequest.order_id)
            .join(Customer, Customer.id == PortalRefundRequest.customer_id)
            .where(PortalOrder.site_id == site_id, PortalRefundRequest.status == "pending")
            .order_by(PortalRefundRequest.created_at.desc()).limit(limit)).all()
        result.extend(serialize_legacy(row, customer_name=customer.full_name) for row, customer in legacy)
    return result


def manager_detail(db, actor, site_id, identity):
    item = _managed(db, actor, site_id, identity)
    receipt = db.get(Payment, item.receipt_id)
    customer = db.get(Customer, item.customer_id)
    data = serialize(item, order_id=_order_ids(db, [item]).get(item.receipt_id), customer_name=customer.full_name)
    data["receipt"] = {key: value for key, value in PaymentService.serialize(db, receipt).items() if key not in {"shift_id"}}
    data["refund_state"] = refund_state(db, receipt, except_request=item.id)
    return data


def open_request_count(db, site_id):
    return db.scalar(select(func.count(PaymentRefundRequest.id)).where(PaymentRefundRequest.site_id == site_id,
        PaymentRefundRequest.status.in_(REFUND_OPEN_STATES))) or 0
