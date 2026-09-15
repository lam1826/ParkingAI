"""payOS orchestration: commit identity, perform HTTP, then lock and apply evidence.

No network operation may run while this service owns a SQL transaction. Webhook
acceptance commits the immutable inbox before ACK; a separate processor verifies
provider status and fulfills through the shared portal ledger seam, never DEMO.

Portal ticket orders and immutable accrued-fee quotes share provider mappings,
signed evidence and reconciliation. Session payments create separate credits;
manual checkout applies them to the final fee without releasing a slot early.
"""
from datetime import timedelta
from types import SimpleNamespace
import hashlib
import json
import uuid
import secrets

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import object_session

from core.clock import BUSINESS_TZ, business_now
from core.money import MAX_EXACT_VND
from expansion import portal_service
from expansion.online_payment_models import OnlinePaymentInbox, OnlinePaymentLink, OnlinePaymentProcessing, OnlinePaymentReviewDecision
from expansion.online_payment_schemas import PaymentLinkView, get_online_payment_config
from expansion.payos_gateway import (
    CreateLinkRequest, CreatedPaymentLink, PaymentExpectation, PaymentLink,
    PayOSGatewayError, PayOSMismatchError, VerifiedWebhook,
)
from expansion.portal_models import PortalAccountLink, PortalOrder
from expansion.site_scope import require_public_site, require_site_access
from expansion.site_models import ParkingSite
from expansion.session_payment_models import SessionFeeQuote


def available_payment_modes(site_id, demo_enabled=False):
    modes = ["manual"] + (["demo"] if demo_enabled else [])
    try:
        config = get_online_payment_config()
    except (ValueError, HTTPException):
        return modes
    if config.PAYOS_ENABLED and config.PAYOS_SITE_ID == site_id:
        modes.append("payos")
    return modes


def require_online_order_config(db, site_id, config=None):
    config = config or get_online_payment_config()
    if not config.PAYOS_ENABLED:
        raise HTTPException(503, "Thanh toán payOS chưa được cấu hình tại bãi.")
    if site_id != config.PAYOS_SITE_ID:
        raise HTTPException(409, "Kênh thanh toán không thuộc bãi của đơn.")
    require_public_site(db, site_id)
    return config


def can_cancel_portal_order_locally(order, *, linked_order_ids=None):
    if order.payment_mode != "payos":
        return True
    if linked_order_ids is not None:
        return order.id not in linked_order_ids
    db = object_session(order)
    return db is not None and db.scalar(select(OnlinePaymentLink.id).where(
        OnlinePaymentLink.order_id == order.id).limit(1)) is None


def portal_cancel_guard(order):
    # The shared caller already holds the same order lock as create_link. If no
    # mapping exists, no provider request can have started and local cancel is safe.
    if not can_cancel_portal_order_locally(order):
        raise HTTPException(409, "Đơn payOS cần hủy liên kết thanh toán hoặc được quản lý đối soát.")


def _owned(db, user, order_id):
    order = db.scalar(select(PortalOrder).join(PortalAccountLink,
        PortalAccountLink.customer_id == PortalOrder.customer_id).where(
        PortalOrder.id == order_id, PortalOrder.user_id == user.id, PortalAccountLink.user_id == user.id))
    if order is None or not user.is_active:
        raise HTTPException(404, "Không tìm thấy đơn của bạn.")
    if order.payment_mode != "payos":
        raise HTTPException(409, "Đơn này không sử dụng payOS.")
    return order


def _link(db, source_id, *, session_fee=False):
    column = OnlinePaymentLink.session_quote_id if session_fee else OnlinePaymentLink.order_id
    return db.scalar(select(OnlinePaymentLink).where(column == source_id))


def _source_for_link(db, link):
    return db.get(SessionFeeQuote, link.session_quote_id) if link.session_quote_id else db.get(PortalOrder, link.order_id)


def _owned_source(db, user, identity, *, session_fee=False):
    if session_fee:
        from expansion.session_payment_service import authorize_quote
        return authorize_quote(db, user, identity)
    return _owned(db, user, identity)


def _lock_source(db, identity, *, session_fee=False):
    if session_fee:
        from expansion.session_payment_service import lock_quote_context
        return lock_quote_context(db, identity)
    return portal_service._lock_order_context(db, identity)


def _channel_matches(link, config):
    return (config.PAYOS_ENABLED and link.channel == config.channel
        and link.receiver_digest == config.receiver_digest and link.site_id == config.PAYOS_SITE_ID)


def _expectation(link):
    return PaymentExpectation(order_code=link.id, amount=link.amount, payment_link_id=link.payment_link_id)


def _source_payment_problem(order, now):
    db = object_session(order)
    if db is None:
        return "source_unavailable"
    if not db.scalar(select(ParkingSite.is_active).where(ParkingSite.id == order.site_id)):
        return "site_inactive"
    if isinstance(order, SessionFeeQuote):
        from expansion.session_payment_service import fulfillment_problem
        return fulfillment_problem(db, order, SimpleNamespace(received_at=now))
    return None


def _view(order, link, config):
    now = business_now()
    enabled = config.PAYOS_ENABLED and order.site_id == config.PAYOS_SITE_ID
    if link is not None:
        enabled = enabled and _channel_matches(link, config)
    busy = bool(link and link.operation_until and link.operation_until > now)
    payable = order.status == "pending" and order.expires_at > now
    source_problem = _source_payment_problem(order, now) if payable else None
    payable = payable and source_problem is None
    state = link.state if link else "not_created"
    if link is None and order.status in {"cancelled", "expired", "review"}:
        state = order.status
    messages = {
        "not_created": "Chưa tạo liên kết thanh toán.",
        "creating": "Đang xác nhận liên kết. Không tạo hoặc thanh toán một đơn thay thế.",
        "unknown": "Chưa xác nhận được kết quả. Hãy kiểm tra lại đơn hiện tại.",
        "ready": "Chỉ thanh toán đúng số tiền một lần. Hệ thống sẽ xác nhận từ cổng thanh toán.",
        "paid": "Thanh toán đã được đối soát và vé đã được cấp.",
        "cancelled": "Liên kết đã hủy. Khoản tiền đến sau sẽ được quản lý đối soát.",
        "expired": "Đơn hoặc liên kết đã hết hạn. Khoản tiền đến sau cần đối soát.",
        "review": "Có khoản thanh toán cần quản lý đối soát. Chưa cấp thêm vé hoặc tự hoàn tiền.",
    }
    message = messages[state] if enabled else "Thanh toán payOS chưa được bật cho bãi này."
    if isinstance(order, SessionFeeQuote) and state == "paid":
        message = "Đã ghi nhận tiền online cho lượt gửi. Nhân viên sẽ kiểm tra số dư và xác nhận xe ra."
    elif isinstance(order, SessionFeeQuote) and state == "review":
        message = "Khoản thanh toán cần quản lý đối soát; chưa ghi thêm tiền vào lượt gửi."
    if source_problem == "site_inactive":
        message = "Bãi đã tạm ngừng nhận thanh toán. Không chuyển thêm tiền; khoản đã chuyển vẫn được đối soát."
    elif source_problem == "session_no_longer_active":
        message = "Lượt gửi đã kết thúc hoặc không còn cho phép thanh toán. Không chuyển thêm tiền theo đề nghị này."
    elif source_problem:
        message = "Đề nghị cũ không còn phù hợp với lượt và số dư hiện tại. Không chuyển tiền; hãy kiểm tra lại lượt gửi."
    elif not payable and state in {"not_created", "ready"}:
        message = messages["expired"] if order.status != "cancelled" else messages["cancelled"]
    show_code = enabled and payable and state == "ready" and not busy
    qr_svg = None
    if show_code and link.qr_code:
        from expansion.gateway import DemoGateway
        try:
            qr_svg = DemoGateway.qr_svg(link.qr_code)
        except (ValueError, TypeError):
            # Keep the verified checkout URL available if a provider payload is
            # too large for the local renderer; never invent a replacement QR.
            pass
    common = dict(enabled=enabled, state=state,
        provider_status=link.provider_status if link else None, amount=order.amount,
        expires_at=order.expires_at.replace(tzinfo=BUSINESS_TZ), server_now=now.replace(tzinfo=BUSINESS_TZ),
        checkout_url=link.checkout_url if show_code else None, qr_code=link.qr_code if show_code else None, qr_svg=qr_svg,
        review_reason=link.review_reason if link else None, message=message,
        can_create=enabled and payable and link is None,
        can_refresh=bool(enabled and link and not busy and link.state != "paid"),
        can_cancel=bool(enabled and not busy and order.status in {"pending", "expired"}
            and ((link and link.state in {"ready", "unknown", "creating"})
                or (link is None and isinstance(order, SessionFeeQuote)))))
    if isinstance(order, SessionFeeQuote):
        from expansion.session_payment_schemas import SessionPaymentLinkView
        return SessionPaymentLinkView(quote_id=order.id, session_id=order.session_id,
            paid_through=order.paid_through.replace(tzinfo=BUSINESS_TZ), **common)
    return PaymentLinkView(order_id=order.id, **common)


def get_payment_link(db, user, order_id, config):
    order = _owned(db, user, order_id)
    return _view(order, _link(db, order_id), config)


def get_session_payment_link(db, user, quote_id, config):
    quote = _owned_source(db, user, quote_id, session_fee=True)
    return _view(quote, _link(db, quote_id, session_fee=True), config)


def _locked_link(db, link_id):
    source = db.get(OnlinePaymentLink, link_id)
    if source is None:
        raise HTTPException(404, "Không tìm thấy liên kết thanh toán.")
    order = _lock_source(db, source.session_quote_id or source.order_id, session_fee=source.session_quote_id is not None)
    return order, portal_service._locked(db, OnlinePaymentLink, link_id)


def _provider_state(link, result):
    if link.payment_link_id is None:
        link.payment_link_id = result.payment_link_id
    elif link.payment_link_id != result.payment_link_id:
        link.state, link.review_reason = "review", "link_mismatch"
        return
    link.provider_status = result.status
    link.last_checked_at = business_now()
    link.last_error = None
    if isinstance(result, CreatedPaymentLink):
        link.checkout_url, link.qr_code = result.checkout_url, result.qr_code
    if link.state in {"paid", "review"}:
        return
    if result.status in {"CANCELLED", "EXPIRED", "FAILED"}:
        link.state = "cancelled" if result.status == "CANCELLED" else "expired"
    elif result.status in {"PENDING", "PROCESSING"}:
        link.state = "ready" if link.checkout_url and link.qr_code else "unknown"
    elif result.status == "UNDERPAID":
        link.state, link.review_reason = "review", "partial_payment"
    # PAID is evidence awaiting atomic fulfillment, never a completed browser state.


def create_payment_link(db, user, order_id, config, gateway):
    _owned(db, user, order_id)
    order = portal_service._lock_order_context(db, order_id)
    _owned(db, user, order_id)  # Recheck account authority after waiting for locks.
    _create_source_link(db, order, config, gateway)
    return _authorized_view(db, user, order_id, config)


def create_session_payment_link(db, user, quote_id, config, gateway):
    _owned_source(db, user, quote_id, session_fee=True)
    quote = _lock_source(db, quote_id, session_fee=True)
    _owned_source(db, user, quote_id, session_fee=True)
    from expansion.session_payment_service import validate_quote_for_link
    if _link(db, quote_id, session_fee=True) is None:
        validate_quote_for_link(db, quote)
    _create_source_link(db, quote, config, gateway)
    return _authorized_view(db, user, quote_id, config, session_fee=True)


def _authorized_view(db, user, source_id, config, *, session_fee=False):
    # Provider work is already durable. Revoked authority must not expose the
    # newly created QR, even when ownership changed during a slow HTTP call.
    if user is not None:
        db.refresh(user)
        source = _owned_source(db, user, source_id, session_fee=session_fee)
    else:
        source = db.get(SessionFeeQuote if session_fee else PortalOrder, source_id)
    result = _view(source, _link(db, source_id, session_fee=session_fee), config)
    db.commit()
    return result


def _create_source_link(db, order, config, gateway):
    require_online_order_config(db, order.site_id, config)
    session_fee = isinstance(order, SessionFeeQuote)
    existing = _link(db, order.id, session_fee=session_fee)
    if existing is not None:
        result = _view(order, existing, config)
        db.commit()
        return result  # Never re-send create, even after timeout or process crash.
    if order.status != "pending" or order.expires_at <= business_now():
        raise HTTPException(409, "Đơn không còn chờ thanh toán.")
    token = str(uuid.uuid4())
    for _ in range(5):
        code = secrets.randbelow(MAX_EXACT_VND) + 1
        if db.get(OnlinePaymentLink, code) is not None:
            continue
        candidate = OnlinePaymentLink(id=code, order_id=None if session_fee else order.id,
            session_quote_id=order.id if session_fee else None, site_id=order.site_id, channel=config.channel,
            receiver_digest=config.receiver_digest, amount=order.amount, currency="VND",
            return_url=config.PAYOS_RETURN_URL, cancel_url=config.PAYOS_CANCEL_URL, expires_at=order.expires_at,
            operation_token=token, operation_until=business_now() + timedelta(seconds=45), state="creating")
        try:
            with db.begin_nested():
                db.add(candidate)
                db.flush()
            link = candidate
            break
        except IntegrityError:
            if db.get(OnlinePaymentLink, code) is None:
                raise
    else:
        raise HTTPException(409, "Chưa cấp được mã thanh toán duy nhất; hãy thử lại.")
    link_id = link.id
    request = CreateLinkRequest(order_code=link_id, amount=link.amount, description=link.description,
        return_url=link.return_url, cancel_url=link.cancel_url,
        expires_at=int(link.expires_at.replace(tzinfo=BUSINESS_TZ).timestamp()))
    db.commit()  # Durable mapping is visible to concurrent webhook before HTTP starts.
    try:
        provider = gateway.create_link(request)
    except PayOSGatewayError as error:
        order, link = _locked_link(db, link_id)
        if link.operation_token == token:
            link.operation_token = link.operation_until = None
            if link.state not in {"paid", "review"}:
                link.state = "unknown"
            link.last_error = error.code
            if isinstance(error, PayOSMismatchError):
                link.state, link.review_reason = "review", error.reason
        result = _view(order, link, config)
        db.commit()
        return result
    order, link = _locked_link(db, link_id)
    if link.operation_token == token:
        link.operation_token = link.operation_until = None
        _provider_state(link, provider)
    result = _view(order, link, config)
    db.commit()
    return result


def _digest(value):
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _evidence_key(row):
    return (row.order_code, row.payment_link_id, row.amount, row.currency, row.receiver_digest)


def _related_evidence(db, evidence):
    others = list(db.scalars(select(OnlinePaymentInbox).where(OnlinePaymentInbox.channel == evidence.channel,
        OnlinePaymentInbox.reference == evidence.reference, OnlinePaymentInbox.id != evidence.id)))
    exact = [row for row in others if _evidence_key(row) == _evidence_key(evidence)]
    return min([evidence] + exact, key=lambda row: row.received_at), len(exact) != len(others)


def _record(db, *, config, data, source, verification_issue=None):
    """Flush-only. Caller owns commit; do not mutate even duplicate evidence."""
    existing = db.scalar(select(OnlinePaymentInbox).where(OnlinePaymentInbox.channel == config.channel,
        OnlinePaymentInbox.reference == data.reference, OnlinePaymentInbox.payload_digest == data.payload_digest))
    if existing:
        return existing
    link = db.get(OnlinePaymentLink, data.order_code)
    if link is not None and (link.channel != config.channel or link.site_id != config.PAYOS_SITE_ID):
        link = None
    row = OnlinePaymentInbox(link_id=link.id if link else None, site_id=config.PAYOS_SITE_ID,
        channel=config.channel, source=source, order_code=data.order_code, payment_link_id=data.payment_link_id,
        reference=data.reference, amount=data.amount, currency=data.currency,
        receiver_digest=_digest(data.account_number), transaction_time=data.transaction_date_time,
        payload_digest=data.payload_digest, verification_issue=verification_issue)
    db.add(row)
    db.flush()
    reason = "unknown_order" if link is None else None
    db.add(OnlinePaymentProcessing(id=row.id, status="review" if reason else "received", reason=reason,
        processed_at=business_now() if reason else None))
    db.flush()
    return row


def accept_webhook(db, raw_payload, config, gateway):
    # Keep accepting signed evidence when an operator pauses the lot. An inactive
    # site blocks fulfillment, not preservation of incoming funds.
    if not config.PAYOS_ENABLED or db.get(ParkingSite, config.PAYOS_SITE_ID) is None:
        raise HTTPException(503, "Kênh thanh toán chưa được cấu hình.")
    problem = None
    try:
        data = gateway.verify_webhook(raw_payload)
    except PayOSMismatchError as error:
        data, problem = error.verified_data, error.reason
    try:
        row = _record(db, config=config, data=data, source="webhook", verification_issue=problem)
        identity = row.id
        db.commit()  # This is the only point after which HTTP may acknowledge receipt.
        return identity
    except IntegrityError:
        db.rollback()
        row = db.scalar(select(OnlinePaymentInbox).where(OnlinePaymentInbox.channel == config.channel,
            OnlinePaymentInbox.reference == data.reference, OnlinePaymentInbox.payload_digest == data.payload_digest))
        if row is None:
            raise
        identity = row.id
        db.commit()
        return identity


def _record_snapshot(db, link, provider, config):
    identities = []
    for transaction in provider.transactions:
        wire = {"orderCode": provider.order_code, "paymentLinkId": provider.payment_link_id,
            "amount": transaction.amount, "currency": provider.currency or "VND",
            "accountNumber": transaction.account_number, "reference": transaction.reference,
            "description": transaction.description, "transactionDateTime": transaction.transaction_date_time,
            "code": "00", "desc": "Verified provider reconciliation"}
        wire["payloadDigest"] = _digest(json.dumps(wire, sort_keys=True, ensure_ascii=False, separators=(",", ":")))
        evidence = VerifiedWebhook.model_validate(wire)
        issue = "account_mismatch" if _digest(transaction.account_number) != link.receiver_digest else None
        row = _record(db, config=config, data=evidence, source="reconcile", verification_issue=issue)
        identities.append(row.id)
    return identities


def _quarantine(db, order, link, processing, reason):
    processing.status, processing.reason, processing.processed_at = "review", reason, business_now()
    link.state, link.review_reason = "review", reason
    # A second transfer must not invalidate an already issued entitlement.
    if order.status not in {"fulfilled", "refunded"}:
        if not isinstance(order, SessionFeeQuote):
            from expansion.timed_parking_service import release_hold
            release_hold(db, order, expired=True)
        order.status, order.review_reason = "review", reason


def _may_retry_provider(source, evidence):
    deadline = source.expires_at
    if isinstance(source, SessionFeeQuote) and evidence.received_at < deadline:
        # This window only waits for a provider projection, not extra parking time.
        deadline += timedelta(minutes=5)
    return business_now() < deadline


def process_inbox(db, identity, config, gateway, *, provider_snapshot=None):
    """One receipt or durable review. Network GET occurs before any order locks."""
    evidence = db.get(OnlinePaymentInbox, identity)
    processing = db.get(OnlinePaymentProcessing, identity)
    if evidence is None or processing is None or processing.status != "received":
        db.commit()
        return
    link = db.get(OnlinePaymentLink, evidence.link_id) if evidence.link_id else None
    if link is None:
        processing.status, processing.reason = "review", "unknown_order"
        processing.processed_at = business_now()
        db.commit()
        return
    if not _channel_matches(link, config):
        processing.status, processing.reason = "review", "channel_changed"
        processing.processed_at = business_now()
        db.commit()
        return
    if evidence.verification_issue:
        order, link = _locked_link(db, link.id)
        processing = portal_service._locked(db, OnlinePaymentProcessing, identity)
        if processing.status == "received":
            _quarantine(db, order, link, processing, evidence.verification_issue)
        db.commit()
        return
    expected, link_id = _expectation(link), link.id
    db.commit()
    try:
        provider = provider_snapshot if provider_snapshot is not None else gateway.get_link(expected)
    except PayOSGatewayError as error:
        order, link = _locked_link(db, link_id)
        processing = portal_service._locked(db, OnlinePaymentProcessing, identity)
        if processing.status == "received":
            earliest, conflict = _related_evidence(db, evidence)
            if isinstance(error, PayOSMismatchError):
                _quarantine(db, order, link, processing, error.reason)
            elif conflict:
                _quarantine(db, order, link, processing, "reference_conflict")
            elif not _may_retry_provider(order, earliest):
                _quarantine(db, order, link, processing, "provider_unavailable_after_expiry")
            else:
                processing.attempts += 1
                processing.reason = error.code
                processing.next_attempt_at = business_now() + timedelta(seconds=min(300, 2 ** min(processing.attempts, 8)))
        db.commit()
        return
    order, link = _locked_link(db, link_id)
    processing = portal_service._locked(db, OnlinePaymentProcessing, identity)
    if processing.status != "received":
        db.commit()
        return
    evidence = db.get(OnlinePaymentInbox, identity)
    earliest, conflict = _related_evidence(db, evidence)
    reason = None
    if (not _channel_matches(link, config) or evidence.receiver_digest != link.receiver_digest
            or evidence.currency != link.currency or evidence.amount != link.amount):
        reason = "payment_identity_mismatch"
    elif provider.order_code != link.id or provider.amount != link.amount or provider.payment_link_id != evidence.payment_link_id:
        reason = "provider_identity_mismatch"
    elif link.payment_link_id and evidence.payment_link_id != link.payment_link_id:
        reason = "link_mismatch"
    elif conflict:
        reason = "reference_conflict"
    elif link.settled_reference:
        if link.settled_reference == evidence.reference:
            processing.status, processing.receipt_id = "duplicate", link.receipt_id
            processing.processed_at = business_now()
            db.commit()
            return
        reason = "additional_payment"
    elif (provider.status in {"PENDING", "PROCESSING"} and provider.amount_paid <= link.amount
            and order.status in {"pending", "expired"} and _may_retry_provider(order, earliest)):
        # A signed transfer notification can reach us before the provider's GET
        # projection catches up. Preserve it and retry, without closing the order.
        processing.attempts += 1
        processing.reason = "provider_settlement_pending"
        processing.next_attempt_at = business_now() + timedelta(seconds=min(30, 2 ** min(processing.attempts, 5)))
        _provider_state(link, provider)
        db.commit()
        return
    elif not provider.is_fully_paid or len(provider.transactions) != 1:
        reason = "payment_total_requires_review"
    elif (provider.transactions[0].reference != evidence.reference
            or provider.transactions[0].amount != evidence.amount
            or _digest(provider.transactions[0].account_number) != link.receiver_digest):
        reason = "transaction_mismatch"
    elif isinstance(order, SessionFeeQuote):
        from expansion.session_payment_service import fulfillment_problem
        reason = fulfillment_problem(db, order, earliest)
    elif order.status != "pending" or evidence.received_at >= order.expires_at or business_now() >= order.expires_at:
        reason = "late_or_closed_order"
    else:
        reason = portal_service._fulfillment_problem(db, order, paid_at=evidence.received_at)
    _provider_state(link, provider)
    if reason:
        _quarantine(db, order, link, processing, reason)
    else:
        if isinstance(order, SessionFeeQuote):
            from expansion.session_payment_service import fulfill
            fulfill(db, order)
        else:
            portal_service._fulfill(db, order, method="transfer", collector=None)
        db.flush()  # Order receipt/entitlement source precedes the mapping backstop.
        link.receipt_id, link.settled_reference, link.state = order.receipt_id, evidence.reference, "paid"
        link.review_reason = None
        db.flush([link])
        processing.status, processing.receipt_id = "processed", order.receipt_id
        processing.processed_at = business_now()
    db.commit()


def reconcile_payment_link(db, user, order_id, config, gateway, *, cancel_reason=None):
    return _reconcile_link(db, order_id, config, gateway, user=user, cancel_reason=cancel_reason)


def reconcile_session_payment_link(db, user, quote_id, config, gateway, *, cancel_reason=None):
    return _reconcile_link(db, quote_id, config, gateway, user=user, cancel_reason=cancel_reason, session_fee=True)


def reconcile_link_for_worker(db, link_id, config, gateway):
    link = db.get(OnlinePaymentLink, link_id)
    if link is None:
        db.commit()
        return None
    return _reconcile_link(db, link.session_quote_id or link.order_id, config, gateway,
        session_fee=link.session_quote_id is not None)


def _reconcile_link(db, order_id, config, gateway, *, user=None, cancel_reason=None, session_fee=False):
    """GET/cancel once under a committed lease, preserving any concurrent paid event."""
    if user is not None:
        _owned_source(db, user, order_id, session_fee=session_fee)
    order = _lock_source(db, order_id, session_fee=session_fee)
    if user is not None:
        _owned_source(db, user, order_id, session_fee=session_fee)
        require_online_order_config(db, order.site_id, config)
    elif order is None or order.payment_mode != "payos" or not config.PAYOS_ENABLED:
        raise HTTPException(409, "Đơn không thể đối soát qua payOS.")
    link = _link(db, order_id, session_fee=session_fee)
    if link is None and session_fee and cancel_reason and order.status in {"pending", "expired", "cancelled"}:
        order.status = "cancelled"
        result = _view(order, None, config)
        db.commit()
        return result
    if link is None or not _channel_matches(link, config):
        raise HTTPException(409, "Không có liên kết của kênh thanh toán đang cấu hình.")
    now = business_now()
    if link.operation_until and link.operation_until > now:
        raise HTTPException(409, "Một lần đối soát đang thực hiện. Vui lòng thử lại sau.")
    if not cancel_reason and link.last_checked_at and link.last_checked_at > now - timedelta(seconds=10):
        db.commit()
        return _authorized_view(db, user, order_id, config, session_fee=session_fee)
    if cancel_reason and (link.state in {"paid", "review"} or order.status not in {"pending", "expired"}):
        raise HTTPException(409, "Đơn đã có kết quả; cần quản lý đối soát.")
    token, link_id, expected = str(uuid.uuid4()), link.id, _expectation(link)
    link.operation_token, link.operation_until = token, now + timedelta(seconds=45)
    db.commit()
    try:
        provider = gateway.cancel_link(expected, reason=cancel_reason) if cancel_reason else gateway.get_link(expected)
    except PayOSGatewayError as error:
        order, link = _locked_link(db, link_id)
        if link.operation_token == token:
            link.operation_token = link.operation_until = None
            link.last_error, link.last_checked_at = error.code, business_now()
            if isinstance(error, PayOSMismatchError):
                link.state, link.review_reason = "review", error.reason
            elif link.state not in {"paid", "review"}:
                link.state = "unknown"
        db.commit()
        return _authorized_view(db, user, order_id, config, session_fee=session_fee)
    order, link = _locked_link(db, link_id)
    if link.operation_token != token:
        db.commit()
        return _authorized_view(db, user, order_id, config, session_fee=session_fee)
    link.operation_token = link.operation_until = None
    _provider_state(link, provider)
    events = _record_snapshot(db, link, provider, config)
    if provider.status in {"CANCELLED", "EXPIRED", "FAILED"} and not provider.amount_paid and order.status == "pending":
        if not session_fee:
            from expansion.timed_parking_service import release_hold
            release_hold(db, order, expired=provider.status != "CANCELLED")
        order.status = "cancelled" if provider.status == "CANCELLED" else "expired"
    db.commit()
    for identity in events:
        process_inbox(db, identity, config, gateway, provider_snapshot=provider)
    return _authorized_view(db, user, order_id, config, session_fee=session_fee)


def list_review(db, actor, site_id, *, limit=50, offset=0):
    require_site_access(db, actor, site_id, "manager")
    rows = db.execute(select(OnlinePaymentInbox, OnlinePaymentProcessing).join(OnlinePaymentProcessing,
        OnlinePaymentProcessing.id == OnlinePaymentInbox.id).where(OnlinePaymentInbox.site_id == site_id,
        OnlinePaymentProcessing.status == "review").order_by(OnlinePaymentInbox.received_at.desc(),
        OnlinePaymentInbox.id).limit(limit).offset(offset)).all()
    decisions = {}
    links = {}
    session_ids = {}
    if rows:
        link_ids = {row.link_id for row, _ in rows if row.link_id is not None}
        links = {row.id: row for row in db.scalars(select(OnlinePaymentLink).where(OnlinePaymentLink.id.in_(link_ids)))} if link_ids else {}
        quote_ids = {link.session_quote_id for link in links.values() if link.session_quote_id}
        session_ids = dict(db.execute(select(SessionFeeQuote.id, SessionFeeQuote.session_id)
            .where(SessionFeeQuote.id.in_(quote_ids))).all()) if quote_ids else {}
        for decision in db.scalars(select(OnlinePaymentReviewDecision).where(
                OnlinePaymentReviewDecision.inbox_id.in_([row.id for row, _ in rows]))
                .order_by(OnlinePaymentReviewDecision.created_at, OnlinePaymentReviewDecision.id)):
            decisions.setdefault(decision.inbox_id, []).append(serialize_review_decision(decision))
    return {"items": [{"id": row.id, "order_id": links[row.link_id].order_id if row.link_id in links else None,
        "quote_id": links[row.link_id].session_quote_id if row.link_id in links else None,
        "session_id": session_ids.get(links[row.link_id].session_quote_id) if row.link_id in links else None,
        "reference": row.reference, "amount": row.amount, "currency": row.currency, "source": row.source,
        "received_at": row.received_at.replace(tzinfo=BUSINESS_TZ), "provider_transaction_time": row.transaction_time,
        "reason": processing.reason, "status": processing.status,
        "decisions": decisions.get(row.id, []),
        "resolution": "external_refund_recorded" if any(d["action"] == "confirmed_external_refund"
            for d in decisions.get(row.id, [])) else "open",
        "resolution_note": "Chỉ ghi nhận việc quản lý xác nhận đã hoàn ngoài hệ thống; không tự chuyển tiền."
        } for row, processing in rows]}


def serialize_review_decision(row):
    return {"id": row.id, "inbox_id": row.inbox_id, "action": row.action, "request_id": row.request_id,
        "reason": row.reason, "actor_id": row.actor_id, "actor_username": row.actor_username,
        "refund_amount": row.refund_amount, "external_reference": row.external_reference,
        "created_at": row.created_at.replace(tzinfo=BUSINESS_TZ)}


def record_review_decision(db, actor, site_id, identity, data):
    require_site_access(db, actor, site_id, "manager")
    evidence = db.get(OnlinePaymentInbox, identity)
    if evidence is None or evidence.site_id != site_id:
        raise HTTPException(404, "Không tìm thấy bằng chứng thanh toán tại bãi.")
    if evidence.link_id:
        order, link = _locked_link(db, evidence.link_id)
        portal_service._require_independent_reviewer(db, actor, customer_id=order.customer_id)
    else:
        portal_service._locked(db, ParkingSite, site_id)
    processing = portal_service._locked(db, OnlinePaymentProcessing, identity)
    require_site_access(db, actor, site_id, "manager")
    existing = db.scalar(select(OnlinePaymentReviewDecision).where(OnlinePaymentReviewDecision.inbox_id == identity,
        OnlinePaymentReviewDecision.request_id == data.request_id))
    if existing:
        if any(getattr(existing, key) != getattr(data, key) for key in ("action", "reason", "refund_amount", "external_reference")):
            raise HTTPException(409, "Mã yêu cầu đã dùng cho quyết định khác.")
        result = serialize_review_decision(existing)
        db.commit()
        return result
    if processing.status != "review":
        raise HTTPException(409, "Chỉ ghi quyết định cho khoản đang cần đối soát.")
    if data.action == "confirmed_external_refund":
        if (data.refund_amount != evidence.amount or evidence.currency != "VND"
                or evidence.verification_issue in {"account_mismatch", "currency_mismatch"}):
            raise HTTPException(409, "Số tiền hoàn phải khớp khoản đã nhận vào đúng tài khoản VND.")
        if db.scalar(select(OnlinePaymentLink.id).where(OnlinePaymentLink.channel == evidence.channel,
                OnlinePaymentLink.settled_reference == evidence.reference)):
            raise HTTPException(409, "Khoản này đã cấp vé; cần nghiệp vụ hoàn chứng từ và thu hồi quyền sử dụng vé.")
        if db.scalar(select(OnlinePaymentReviewDecision.id).where(OnlinePaymentReviewDecision.channel == evidence.channel,
                OnlinePaymentReviewDecision.payment_reference == evidence.reference,
                OnlinePaymentReviewDecision.action == "confirmed_external_refund")):
            raise HTTPException(409, "Khoản chuyển này đã được ghi nhận hoàn ngoài hệ thống.")
    decision = OnlinePaymentReviewDecision(inbox_id=identity, channel=evidence.channel,
        payment_reference=evidence.reference, action=data.action, request_id=data.request_id,
        reason=data.reason, actor_id=actor.id, actor_username=actor.username,
        refund_amount=data.refund_amount, external_reference=data.external_reference)
    db.add(decision)
    try:
        db.flush()
        result = serialize_review_decision(decision)
        db.commit()
        return result
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "Quyết định đối soát đã thay đổi; hãy tải lại danh sách.") from None
