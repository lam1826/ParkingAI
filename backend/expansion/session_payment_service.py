"""Accrued parking fees may be prepaid online while physical departure stays manual."""
from datetime import timedelta
import hashlib
import json

from fastapi import HTTPException
from fastapi.encoders import jsonable_encoder
from sqlalchemy import select, update

from core.billing import snapshot_basis
from core.clock import BUSINESS_TZ, business_now
from core.money import require_exact_vnd
from expansion.portal_models import PortalAccountLink, PortalSessionGrant
from expansion.session_payment_models import SessionFeeCredit, SessionFeeQuote
from expansion.session_payment_schemas import SessionFeeQuoteView, SessionPaymentConfig
from expansion.site_scope import require_site_access
from models.parking_session import ParkingSession
from models.parking_slot import ParkingSlot
from models.vehicle import Vehicle
from models.zone import Zone


def _aware(value):
    return value.replace(tzinfo=BUSINESS_TZ) if value is not None and value.tzinfo is None else value


def credit_snapshots_many(db, session_ids):
    ids = set(session_ids)
    result = {identity: {"credit_ids": [], "total": 0, "paid_through": None} for identity in ids}
    if not ids:
        return result
    rows = db.scalars(select(SessionFeeCredit).where(SessionFeeCredit.session_id.in_(ids), SessionFeeCredit.receipt_id.is_not(None))
        .order_by(SessionFeeCredit.id))
    for row in rows:
        value = result[row.session_id]
        value["credit_ids"].append(row.id)
        value["total"] = require_exact_vnd(value["total"] + row.amount)
        at = _aware(row.paid_through)
        value["paid_through"] = at if value["paid_through"] is None else max(value["paid_through"], at)
    return result


def credit_snapshot(db, session_id):
    return credit_snapshots_many(db, [session_id])[session_id]


def credit_claim(snapshot):
    return {"credit_ids": snapshot["credit_ids"], "total": snapshot["total"]}


def _hash(value):
    return hashlib.sha256(json.dumps(jsonable_encoder(value), sort_keys=True,
        separators=(",", ":"), ensure_ascii=True).encode()).hexdigest()


def _session_state(session, vehicle):
    from services.checkout_service import _state
    return _state(session, vehicle)


def _load_session(db, session_id):
    row = db.execute(select(ParkingSession, Vehicle, Zone.site_id).join(Vehicle,
        Vehicle.id == ParkingSession.vehicle_id).join(ParkingSlot,
        ParkingSlot.id == ParkingSession.parking_slot_id).join(Zone, Zone.id == ParkingSlot.zone_id)
        .where(ParkingSession.id == session_id).execution_options(populate_existing=True)).first()
    if row is None or row[2] is None:
        raise HTTPException(404, "Không tìm thấy lượt gửi có bãi xác định.")
    return row


def authorize_session(db, user, session_id, *, site_id=None):
    session, vehicle, actual_site = _load_session(db, session_id)
    if site_id is not None:
        if site_id != actual_site:
            raise HTTPException(404, "Không tìm thấy lượt gửi tại bãi.")
        require_site_access(db, user, site_id)
    else:
        customer_id = db.scalar(select(PortalAccountLink.customer_id).where(PortalAccountLink.user_id == user.id))
        grant = db.get(PortalSessionGrant, session_id)
        if (not user.is_active or customer_id is None or grant is None or grant.customer_id != customer_id
                or vehicle.customer_id != customer_id):
            from expansion.ticket_payment_access import valid_access
            if valid_access(db, user, session, vehicle) is None:
                raise HTTPException(404, "Không tìm thấy lượt gửi được xác nhận thuộc hồ sơ của bạn.")
    return session, vehicle, actual_site


def authorize_quote(db, user, quote_id):
    quote = db.get(SessionFeeQuote, quote_id)
    if quote is None:
        raise HTTPException(404, "Không tìm thấy đề nghị thanh toán phí gửi xe.")
    operational = user.role and user.role.name in {"staff", "manager", "admin"}
    session, vehicle, _ = authorize_session(db, user, quote.session_id, site_id=quote.site_id if operational else None)
    if not operational and quote.created_by_id != user.id:
        owner = db.scalar(select(PortalAccountLink.customer_id).where(PortalAccountLink.user_id == user.id))
        grant = db.get(PortalSessionGrant, session.id)
        if owner is None or grant is None or grant.customer_id != owner or vehicle.customer_id != owner:
            raise HTTPException(404, 'Không tìm thấy đề nghị thanh toán của bạn.')
    return quote


def lock_session(db, session_id):
    if db.get_bind().dialect.name == "sqlite":
        db.execute(update(ParkingSession).where(ParkingSession.id == session_id)
            .values(id=ParkingSession.id, updated_at=ParkingSession.updated_at))
    session = db.scalar(select(ParkingSession).where(ParkingSession.id == session_id)
        .with_for_update().execution_options(populate_existing=True))
    if session is None:
        raise HTTPException(404, "Không tìm thấy lượt gửi.")
    return session


def lock_quote_context(db, quote_id):
    quote = db.get(SessionFeeQuote, quote_id)
    if quote is None:
        raise HTTPException(404, "Không tìm thấy đề nghị thanh toán phí gửi xe.")
    lock_session(db, quote.session_id)
    return db.scalar(select(SessionFeeQuote).where(SessionFeeQuote.id == quote_id)
        .with_for_update().execution_options(populate_existing=True))


def _totals(db, session, vehicle, now):
    from services.checkout_service import CheckoutService
    snapshot = credit_snapshot(db, session.id)
    if session.status == "cancelled":
        fee, basis = 0, None
    elif session.status == "completed":
        fee = require_exact_vnd(session.parking_fee or 0)
        basis = snapshot_basis(session, session.check_out_time)
    else:
        fee = CheckoutService(db)._fee(session, vehicle, now)
        basis = snapshot_basis(session, now)
    return fee, snapshot, basis


def serialize_quote(quote):
    return SessionFeeQuoteView(id=quote.id, session_id=quote.session_id, gross_fee=quote.gross_fee,
        online_paid=quote.credited_amount, balance_due=quote.amount, quoted_at=_aware(quote.quoted_at),
        paid_through=_aware(quote.paid_through), expires_at=_aware(quote.expires_at), server_now=_aware(business_now()),
        status=quote.status, billing_basis=quote.billing_basis)


def _unresolved_quotes(session_id, now):
    from expansion.online_payment_models import OnlinePaymentLink, OnlinePaymentInbox, OnlinePaymentProcessing
    has_link = select(OnlinePaymentLink.id).where(OnlinePaymentLink.session_quote_id == SessionFeeQuote.id).exists()
    waiting_evidence = select(OnlinePaymentInbox.id).join(OnlinePaymentProcessing,
        OnlinePaymentProcessing.id == OnlinePaymentInbox.id).join(OnlinePaymentLink,
        OnlinePaymentLink.id == OnlinePaymentInbox.link_id).where(
        OnlinePaymentLink.session_quote_id == SessionFeeQuote.id, OnlinePaymentProcessing.status == "received").exists()
    return select(SessionFeeQuote).where(SessionFeeQuote.session_id == session_id,
        (SessionFeeQuote.status == "review") | waiting_evidence | ((SessionFeeQuote.status == "pending")
        & ((SessionFeeQuote.expires_at > now) | has_link)))


def payment_status(db, user, session_id, config, *, site_id=None):
    session, vehicle, actual_site = authorize_session(db, user, session_id, site_id=site_id)
    fee, credits, basis = _totals(db, session, vehicle, business_now())
    latest = db.scalar(select(SessionFeeQuote).where(SessionFeeQuote.session_id == session_id)
        .order_by(SessionFeeQuote.quoted_at.desc(), SessionFeeQuote.id.desc()).limit(1))
    unresolved = db.scalar(_unresolved_quotes(session_id, business_now()).limit(1))
    supported = basis is not None and session.billing_policy_version in {"entry-v1", "prepaid-window-v1"}
    enabled = config.PAYOS_ENABLED and config.PAYOS_SITE_ID == actual_site
    due = max(0, fee - credits["total"])
    message = "Xe chỉ ra bãi sau khi nhân viên xác nhận; phần phí phát sinh sẽ được tính lúc ra."
    if not supported:
        message = "Lượt cũ chưa chốt bảng giá bất biến; vui lòng thanh toán tại bãi."
    elif not enabled:
        message = "Thanh toán payOS chưa được bật; bạn vẫn có thể thanh toán tại bãi."
    elif unresolved:
        message = "Đã có đề nghị đang chờ hoặc cần đối soát. Hãy kiểm tra đề nghị hiện tại trước khi trả thêm."
    if session.status == "completed":
        message = "Lượt gửi đã kết thúc. Số liệu bên dưới là phí và các khoản thanh toán của lượt này."
    elif session.status == "cancelled":
        message = "Lượt gửi đã hủy; không tạo thêm đề nghị thanh toán."
    return {"session_id": session_id, "session_status": session.status, "enabled": enabled, "supported": supported,
        "gross_fee": fee, "online_paid": credits["total"], "balance_due": due,
        "paid_through": credits["paid_through"], "server_now": _aware(business_now()), "billing_basis": basis,
        "latest_quote": serialize_quote(latest) if latest else None,
        "can_quote": bool(enabled and supported and session.status == "active" and due > 0 and not unresolved),
        "message": message}


def create_quote(db, user, session_id, data, config, *, site_id=None, quote_settings=None):
    from services.payment_service import lock_cash_operator
    authorize_session(db, user, session_id, site_id=site_id)
    lock_cash_operator(db, user.id)
    lock_session(db, session_id)
    session, vehicle, actual_site = authorize_session(db, user, session_id, site_id=site_id)
    existing = db.scalar(select(SessionFeeQuote).where(SessionFeeQuote.session_id == session_id,
        SessionFeeQuote.created_by_id == user.id, SessionFeeQuote.request_id == data.request_id))
    if existing:
        result = serialize_quote(existing)
        db.commit()
        return result
    from expansion.online_payment_service import require_online_order_config
    require_online_order_config(db, actual_site, config)
    if session.status != "active":
        raise HTTPException(409, "Chỉ thanh toán online cho lượt xe đang gửi.")
    now = business_now()
    fee, credits, basis = _totals(db, session, vehicle, now)
    if basis is None or session.billing_policy_version not in {"entry-v1", "prepaid-window-v1"}:
        raise HTTPException(409, "Lượt cũ chưa chốt bảng giá bất biến; cần thu tại bãi.")
    due = fee - credits["total"]
    if due <= 0:
        raise HTTPException(409, "Lượt hiện không còn phí cần thanh toán; không tạo QR 0đ.")
    # Terminal provider status alone cannot clear accepted but unprocessed money.
    if db.scalar(_unresolved_quotes(session_id, now).with_for_update().limit(1)):
        raise HTTPException(409, "Cần kiểm tra hoặc hủy đề nghị thanh toán hiện tại trước khi tạo đề nghị khác.")
    previous = db.scalars(select(SessionFeeQuote).where(SessionFeeQuote.session_id == session_id,
        SessionFeeQuote.status == "pending").with_for_update())
    for old in previous:
        old.status = "expired"  # Only expired, unmapped proposals survived the query above.
    db.flush()
    seconds = 3600 if basis["ticket_type"] == "HOURLY" else 86400
    paid_through = basis["billable_from"] + timedelta(seconds=basis["billable_blocks"] * seconds)
    settings = quote_settings or SessionPaymentConfig(_env_file=None)
    grant = db.get(PortalSessionGrant, session_id)
    quote = SessionFeeQuote(session_id=session_id, site_id=actual_site, created_by_id=user.id,
        owner_customer_id=grant.customer_id if grant else None, request_id=data.request_id,
        session_state_hash=_hash(_session_state(session, vehicle)), credit_snapshot_hash=_hash(credit_claim(credits)),
        gross_fee=fee, credited_amount=credits["total"], amount=due, quoted_at=now,
        paid_through=paid_through.astimezone(BUSINESS_TZ).replace(tzinfo=None),
        expires_at=now + timedelta(seconds=settings.SESSION_FEE_QUOTE_TTL_SECONDS), billing_basis=jsonable_encoder(basis))
    db.add(quote)
    db.flush()
    result = serialize_quote(quote)
    db.commit()
    return result


def fulfillment_problem(db, quote, evidence):
    session, vehicle, site_id = _load_session(db, quote.session_id)
    if session.status != "active" or site_id != quote.site_id:
        return "session_no_longer_active"
    from expansion.site_models import ParkingSite
    site = db.get(ParkingSite, quote.site_id)
    if site is None or not site.is_active:
        return "site_inactive"
    if quote.status not in {"pending", "expired"} or evidence.received_at >= quote.expires_at:
        return "late_or_closed_quote"
    if _hash(_session_state(session, vehicle)) != quote.session_state_hash:
        return "session_identity_changed"
    grant = db.get(PortalSessionGrant, session.id)
    if (grant.customer_id if grant else None) != quote.owner_customer_id:
        return "session_owner_changed"
    if quote.owner_customer_id is not None and vehicle.customer_id != quote.owner_customer_id:
        return "session_owner_changed"
    from models.user import User
    creator = db.get(User, quote.created_by_id)
    if creator is not None and creator.role and creator.role.name == 'customer':
        try:
            authorize_session(db, creator, session.id)
        except HTTPException:
            return 'session_payment_access_revoked'
    credits = credit_snapshot(db, session.id)
    if _hash(credit_claim(credits)) != quote.credit_snapshot_hash:
        return "session_credit_changed"
    # Fee may have grown by another block since quoted_at. The valid original
    # credit remains useful; the remainder is calculated during manual checkout.
    return None


def validate_quote_for_link(db, quote):
    from types import SimpleNamespace
    reason = fulfillment_problem(db, quote, SimpleNamespace(received_at=business_now()))
    if reason:
        raise HTTPException(409, {"code": reason, "message": "Đề nghị không còn phù hợp; hãy kiểm tra lại lượt và số dư."})


def fulfill(db, quote):
    """Flush-only under the session lock; caller commits inbox/credit/receipt together."""
    from services.payment_service import PaymentService
    db.flush()  # The verified provider link identity must exist for the source guard.
    credit = SessionFeeCredit(session_id=quote.session_id, quote_id=quote.id, amount=quote.amount,
        paid_through=quote.paid_through)
    db.add(credit)
    db.flush()
    receipt = PaymentService.record_receipt(db, "session_credit", credit.id, credit.amount, None, method="transfer")
    credit.receipt_id = receipt.id
    db.flush([credit])
    quote.credit_id, quote.receipt_id, quote.status = credit.id, receipt.id, "fulfilled"
    db.flush([quote])
