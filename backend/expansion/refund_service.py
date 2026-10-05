"""Receipt-based refund requests for DEMO, counter and online payments.

The server decides everything financial: which receipt is the original, how
much was actually collected, how much was already refunded and how much may
still be refunded. Approval is a decision record; money only moves when a
compensating ``payments`` row is written through ``PaymentService.refund``
(DEMO immediately, actual channels when a manager records the external
refund with a reference). Existing entitlement guards are reused: an unused
timed ticket is revoked, a monthly pass is deactivated, a session credit is
only refundable for the part that was not applied to the parking fee.

Review 05/10/2026: approving a counter/online refund of a prepaid hour/day
ticket revokes the ticket at the decision, so the approved amount stays
recordable after the window starts and the ticket cannot be used meanwhile.
An approved monthly refund stays recordable when the manager stops the pass
first. Direct manager refunds (Site Finance / legacy ledger) never bypass an
open request. Ready portal tickets before their start and active portal
monthly periods go through this workflow. A started unused ticket is revoked
atomically with a direct refund; terminal tickets have no entitlement to stop.
"""
from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from core.clock import BUSINESS_TZ, business_now
from core.money import sum_exact_vnd
from expansion import customer_ownership as ownership
from expansion.online_payment_models import OnlinePaymentLink
from expansion.portal_models import PortalOrder, PortalRefundRequest
from expansion.portal_service import _locked, _notify, _require_independent_reviewer, get_linked_customer
from expansion.session_payment_models import SessionFeeCredit
from expansion.site_scope import is_global_admin, require_site_access
from expansion.support_models import PaymentRefundRequest, REFUND_OPEN_STATES
from expansion.timed_parking_models import TimedParkingPass
from models.customer import Customer
from models.monthly_pass import MonthlyPass
from models.parking_session import ParkingSession
from models.payment import Payment
from services.auth_service import check_permission
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
    "nothing_collected": "Khoản thu 0 ₫: không có tiền để hoàn.",
    "site_unknown": "Chứng từ chưa gắn bãi xe nên không gửi yêu cầu hoàn trực tuyến được; hãy liên hệ quản lý tại quầy.",
    "site_inactive": "Bãi xe của chứng từ đã ngừng hoạt động; hãy liên hệ quản lý để được hỗ trợ.",
}
# Why a manager may not refund a receipt directly from Site Finance / the ledger.
DIRECT_REFUND_LABELS = {
    "request_open": "Khoản thu đang có yêu cầu hoàn của khách. Hãy xử lý trong mục Yêu cầu hoàn tiền để không hoàn trùng.",
    "portal_ticket": "Vé giờ/ngày chưa sử dụng và chưa tới giờ bắt đầu: hãy xử lý qua yêu cầu hoàn tiền của khách để thu hồi vé và chỗ giữ.",
    "portal_monthly": "Vé tháng mua qua cổng khách chỉ hoàn qua yêu cầu hoàn tiền của khách để dừng kỳ vé.",
    "pass_in_use": "Kỳ vé đang được dùng cho xe trong bãi; hãy hoàn tất lượt gửi trước khi hoàn hết khoản thu.",
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


def _site_block(db, receipt):
    """A new request must reach a manager queue: the receipt needs an active site."""
    if receipt.site_id is None:
        return "site_unknown"
    from expansion.site_models import ParkingSite
    site = db.get(ParkingSite, receipt.site_id)
    return None if site is not None and site.is_active else "site_inactive"


def _pass_in_use(db, period):
    return db.scalar(select(ParkingSession.id).where(
        (ParkingSession.monthly_pass_id == period.id) |
        ((ParkingSession.vehicle_id == period.vehicle_id) & (ParkingSession.monthly_coverage_end >= period.start_date)),
        ParkingSession.status.in_(["active", "checking_out"])).limit(1)) is not None


def refund_state(db, receipt, *, except_request=None, decision=None):
    """Server-side truth about how much of a receipt may still be refunded and why not.

    ``decision`` evaluates an existing open request: ``"approve"`` for its
    decision and ``"record"`` for recording the money of an approved request.
    The decision owns the entitlement from then on: a pass the manager stopped
    meanwhile, or a ticket revoked at approval, no longer blocks it.
    """
    refunded = refunded_sum(db, receipt.id)
    remaining = receipt.amount - refunded
    link = _online_link(db, receipt)
    state = {"receipt_id": receipt.id, "amount": receipt.amount, "refunded_amount": refunded,
        "refundable_amount": 0, "payment_channel": payment_channel(db, receipt, link),
        "blocked_reason": None, "open_request_id": None, "eligible": False}
    blocked, refundable = None, remaining
    if receipt.kind != "receipt":
        blocked = "not_a_receipt"
    elif receipt.amount == 0 and refunded == 0:
        # A 0 ₫ balancing receipt collected nothing; it was never refunded.
        blocked = "nothing_collected"
    elif remaining <= 0:
        blocked = "fully_refunded"
    elif receipt.method == "legacy_unknown":
        blocked = "legacy_receipt"
    elif decision is None and (site_problem := _site_block(db, receipt)):
        blocked = site_problem
    elif receipt.source_type == "portal_order":
        order = db.get(PortalOrder, receipt.source_id)
        ticket = db.get(TimedParkingPass, order.timed_pass_id) if order and order.timed_pass_id else None
        if ticket is None:
            blocked = "ticket_missing"
        elif decision == "record":
            # The approval froze eligibility (and revoked the ticket). Only a
            # ticket used under an approval made before that rule blocks it.
            if ticket.status == "consumed":
                blocked = "ticket_used"
        elif ticket.status != "ready":
            blocked = {"consumed": "ticket_used", "expired": "ticket_expired"}.get(ticket.status, "ticket_revoked")
        elif business_now() >= ticket.start_at or ticket.arrival_deadline <= business_now():
            blocked = "ticket_window_started"
    elif receipt.source_type == "monthly_pass":
        period = db.get(MonthlyPass, int(receipt.source_id))
        if period is None or (not period.is_active and decision is None):
            blocked = "pass_inactive"
        elif _pass_in_use(db, period):
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
        # Only unresolved review evidence on the link blocks; an extra transfer whose
        # external refund a manager recorded no longer freezes the original receipt.
        from expansion.online_payment_service import link_under_reconciliation
        if link_under_reconciliation(db, link):
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
    # Same row lock as a direct manager refund: a request and a direct refund
    # of one receipt never interleave.
    db.execute(select(Payment.id).where(Payment.id == receipt.id).with_for_update())
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
    item = db.scalar(select(PaymentRefundRequest).where(PaymentRefundRequest.id == identity))
    # Requests filed before receipts had a site (site_id NULL) are decided by a
    # global admin from any site queue; nobody else can reach them.
    if item is None or (item.site_id != site_id and not (item.site_id is None and is_global_admin(actor))):
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
    if item.status == "approved" and _ticket_revoked_by_approval(db, item):
        raise HTTPException(409, "Vé đã được thu hồi khi duyệt hoàn; hãy ghi nhận đã hoàn tiền cho khách thay vì từ chối.")
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
    state = refund_state(db, receipt, except_request=item.id, decision="approve")
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
        if receipt.source_type == "portal_order":
            # The decision stops the prepaid ticket now (still unused and before
            # its window, as checked above), so the approved amount remains
            # recordable whenever the external payout happens.
            from expansion.timed_parking_service import revoke
            revoke(db, db.get(PortalOrder, receipt.source_id))
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
    state = refund_state(db, receipt, except_request=item.id, decision="record")
    if not state["eligible"] or item.approved_amount > state["refundable_amount"]:
        raise HTTPException(409, state["blocked_label"] or "Số tiền duyệt vượt quá số còn có thể hoàn.")
    _execute_refund(db, actor, item, receipt, method=method, external_reference=reference)
    _notify(db, item.customer_id, f"refund:{item.id}:refunded",
        "Quản lý đã ghi nhận hoàn tiền " + ("bằng chuyển khoản" if method == "transfer" else "bằng tiền mặt") + ". Xem chứng từ hoàn trong Lịch sử & chứng từ.")
    db.commit()
    return item


def _ticket_revoked_by_approval(db, item):
    if item.source_type != "portal_order":
        return False
    order = db.get(PortalOrder, item.source_id)
    ticket = db.get(TimedParkingPass, order.timed_pass_id) if order and order.timed_pass_id else None
    return ticket is not None and ticket.status == "revoked"


def _revoke_unused_ticket(db, order):
    from expansion.site_models import ParkingReservation
    from expansion.timed_parking_service import revoke
    ticket = db.get(TimedParkingPass, order.timed_pass_id)
    if ticket.status != "ready":
        return  # Already revoked by the approval decision.
    if business_now() < ticket.start_at:
        revoke(db, order)
        return
    # A started ticket is still unused: stop it without the customer time rule
    # for a direct manager refund or a previously approved external refund.
    ticket.status = "revoked"
    reservation = db.get(ParkingReservation, ticket.reservation_id)
    if reservation is not None and reservation.status == "confirmed":
        reservation.status = "cancelled"
    db.flush()


def _execute_refund(db, actor, item, receipt, *, method, external_reference):
    if receipt.source_type == "portal_order":
        order = db.get(PortalOrder, receipt.source_id)
        _revoke_unused_ticket(db, order)
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
    scope = PaymentRefundRequest.site_id == site_id
    if is_global_admin(actor):
        # Site-less historical requests have no site queue of their own.
        scope = scope | PaymentRefundRequest.site_id.is_(None)
    query = select(PaymentRefundRequest, Customer).join(Customer, Customer.id == PaymentRefundRequest.customer_id).where(scope)
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
    decision = "record" if item.status == "approved" else "approve" if item.status in REFUND_OPEN_STATES else None
    data["refund_state"] = refund_state(db, receipt, except_request=item.id, decision=decision)
    data["entitlement_revoked"] = item.status == "approved" and _ticket_revoked_by_approval(db, item)
    return data


def _portal_period_order(db, receipt):
    """The portal order that sold this monthly period, or None for a counter period."""
    from sqlalchemy import literal
    return db.scalar(select(PortalOrder).join(MonthlyPass, MonthlyPass.renewal_key == literal("portal:") + PortalOrder.id)
        .where(MonthlyPass.id == int(receipt.source_id)))


def direct_refund_block(db, receipt):
    """Why Site Finance / the legacy ledger must not refund this receipt directly.

    Open requests must be settled exactly once in their workflow. A ready
    ticket before its start uses that workflow; once it starts the customer's
    request path is closed, so a manager may refund and stop it directly.
    Terminal tickets have no entitlement left to stop.
    A portal period the manager already stopped ("Ngừng vé") has no
    entitlement left and the customer can no longer request it
    (``pass_inactive``), so the direct refund stays the way to return its money.
    """
    if receipt.kind != "receipt":
        return None
    if _open_request(db, receipt.id) is not None:
        return "request_open"
    if receipt.source_type == "portal_order":
        order = db.get(PortalOrder, receipt.source_id)
        ticket = db.get(TimedParkingPass, order.timed_pass_id) if order and order.timed_pass_id else None
        if ticket is not None and ticket.status == "ready" and business_now() < ticket.start_at:
            return "portal_ticket"
    if receipt.source_type == "monthly_pass":
        period = db.get(MonthlyPass, int(receipt.source_id))
        if period is not None and period.is_active and _portal_period_order(db, receipt) is not None:
            return "portal_monthly"
    return None


def direct_refund_state(db, receipt):
    reason = direct_refund_block(db, receipt)
    open_request = _open_request(db, receipt.id) if reason == "request_open" else None
    revokes_ticket = False
    if reason is None and receipt.kind == "receipt" and receipt.source_type == "portal_order":
        order = db.get(PortalOrder, receipt.source_id)
        ticket = db.get(TimedParkingPass, order.timed_pass_id) if order and order.timed_pass_id else None
        revokes_ticket = ticket is not None and ticket.status == "ready" and business_now() >= ticket.start_at
    return {"direct_refund_blocked_reason": reason, "direct_refund_blocked_label": DIRECT_REFUND_LABELS.get(reason),
        "open_refund_request_id": open_request.id if open_request is not None else None,
        "direct_refund_revokes_ticket": revokes_ticket}


def direct_refund(db, actor, payment_id, *, amount, method, reason, idempotency_key):
    """Manager refund outside the customer workflow; caller commits.

    Without an open request, a started unused portal ticket is stopped even
    for a partial refund; a full refund also marks its order refunded.
    Terminal tickets only get ledger rows. Monthly behaviour stays unchanged:
    a full refund stops an active counter period or marks a stopped portal
    period's order refunded.
    """
    check_permission(actor, "manager")
    lock_cash_operator(db, actor.id)
    receipt = db.scalar(select(Payment).where(Payment.id == payment_id).with_for_update())
    if receipt is None:
        raise HTTPException(404, "Không tìm thấy phiếu thu.")
    if receipt.site_id is not None:
        require_site_access(db, actor, receipt.site_id, "manager")
    replay = db.scalar(select(Payment.id).where(Payment.idempotency_key == f"refund:{idempotency_key}")) is not None
    stop_period = settle_order = revoke_order = None
    if not replay:
        period = None
        if receipt.kind == "receipt" and receipt.source_type == "monthly_pass":
            # Serialize with a concurrent re-activation of the period (PUT locks the same row).
            period = db.scalar(select(MonthlyPass).where(MonthlyPass.id == int(receipt.source_id))
                .with_for_update().execution_options(populate_existing=True))
        if receipt.kind == "receipt" and receipt.source_type == "portal_order":
            order = db.get(PortalOrder, receipt.source_id)
            # Admission locks this same ticket. Re-read after waiting so a
            # concurrent consumption is never overwritten by revocation.
            ticket = db.scalar(select(TimedParkingPass).where(TimedParkingPass.id == order.timed_pass_id)
                .with_for_update().execution_options(populate_existing=True)) if order and order.timed_pass_id else None
            if ticket is not None and ticket.status == "ready":
                revoke_order = order
                if refunded_sum(db, receipt.id) + amount >= receipt.amount:
                    settle_order = order
        problem = direct_refund_block(db, receipt)
        if problem:
            raise HTTPException(409, DIRECT_REFUND_LABELS[problem])
        if period is not None and refunded_sum(db, receipt.id) + amount >= receipt.amount:
            if period.is_active:
                # Only a counter period reaches here active (an active portal period is refused above).
                if _pass_in_use(db, period):
                    raise HTTPException(409, DIRECT_REFUND_LABELS["pass_in_use"])
                stop_period = period
            else:
                order = _portal_period_order(db, receipt)
                settle_order = order if order is not None and order.status == "fulfilled" else None
    refund = PaymentService.refund(db, payment_id, actor, amount=amount, method=method, reason=reason,
        idempotency_key=idempotency_key)
    if revoke_order is not None:
        _revoke_unused_ticket(db, revoke_order)
    if stop_period is not None:
        stop_period.is_active = False
    if settle_order is not None:
        settle_order.status = "refunded"
    db.flush()
    return refund


def open_request_count(db, site_id):
    return db.scalar(select(func.count(PaymentRefundRequest.id)).where(PaymentRefundRequest.site_id == site_id,
        PaymentRefundRequest.status.in_(REFUND_OPEN_STATES))) or 0
