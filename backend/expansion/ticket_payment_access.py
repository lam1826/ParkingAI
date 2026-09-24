"""A ticket authorizes current-stay payment, never vehicle ownership or history."""
from datetime import datetime, timedelta, timezone
import hashlib
import hmac
import uuid

from fastapi import HTTPException
from sqlalchemy import func, or_, select, update

from core.clock import BUSINESS_TZ, business_now
from core.config import settings
from core.vehicle_identity import canonical_identity, identity_expression
from expansion.portal_models import PortalAccountLink, PortalSessionGrant
from expansion.simplified_customer_models import SessionPaymentAccess, SessionTicketCredential
from models.audit_log import AuditLog
from models.parking_session import ParkingSession
from models.parking_slot import ParkingSlot
from models.user import User
from models.vehicle import Vehicle
from models.zone import Zone

NOT_FOUND = 'Chưa xác minh được lượt gửi. Kiểm tra biển số/mã xe, loại xe và mã riêng trên vé hoặc liên hệ nhân viên.'


def customer_only(user):
    if not user.is_active or not user.role or user.role.name != 'customer':
        raise HTTPException(403, 'Chức năng này dành cho tài khoản khách hàng.')


def _code(row):
    body = f'PAP1.{row.session_id}.{row.version}'
    signature = hmac.new(settings.SECRET_KEY.encode(), ('customer-payment:' + body).encode(), hashlib.sha256).hexdigest()[:32]
    return body + '.' + signature


def ticket_payment_code(db, session):
    if session.status != 'active':
        return None
    from expansion.session_payment_service import lock_session
    session = lock_session(db, session.id)
    if session.status != 'active':
        return None
    row = db.get(SessionTicketCredential, session.id)
    if row is None:
        row = SessionTicketCredential(session_id=session.id)
        db.add(row)
        db.flush()
    if row.revoked_at is not None:
        return None
    code = _code(row)
    db.commit()
    return code


def revoke_ticket_payment_access(db, session_id):
    """Flush-only under the caller's session lock (lost-ticket incident)."""
    row = db.get(SessionTicketCredential, session_id)
    if row is not None:
        row.revoked_at = business_now()
    db.execute(update(SessionPaymentAccess).where(SessionPaymentAccess.session_id == session_id,
        SessionPaymentAccess.revoked_at.is_(None)).values(revoked_at=business_now()))
    db.flush()


def rotate_ticket_payment_code(db, session):
    from expansion.session_payment_service import lock_session
    lock_session(db, session.id)
    if session.status != 'active':
        raise HTTPException(409, 'Chỉ cấp lại mã cho lượt đang gửi.')
    row = db.get(SessionTicketCredential, session.id)
    if row is None:
        row = SessionTicketCredential(session_id=session.id)
        db.add(row)
    else:
        row.version, row.revoked_at = uuid.uuid4().hex, None
    db.execute(update(SessionPaymentAccess).where(SessionPaymentAccess.session_id == session.id,
        SessionPaymentAccess.revoked_at.is_(None)).values(revoked_at=business_now()))
    db.flush()
    result = _code(row)
    db.commit()
    return result


def valid_access(db, user, session, vehicle):
    if not user.is_active or not user.role or user.role.name != 'customer' or session.status != 'active':
        return None
    now = business_now()
    row = db.scalar(select(SessionPaymentAccess).join(SessionTicketCredential,
        SessionTicketCredential.session_id == SessionPaymentAccess.session_id).where(
        SessionPaymentAccess.user_id == user.id, SessionPaymentAccess.session_id == session.id,
        SessionPaymentAccess.vehicle_id == vehicle.id,
        SessionPaymentAccess.customer_snapshot_id == vehicle.customer_id,
        SessionPaymentAccess.revoked_at.is_(None), SessionPaymentAccess.expires_at > now,
        SessionTicketCredential.revoked_at.is_(None),
        SessionTicketCredential.version == SessionPaymentAccess.credential_version))
    return row


def _admit_attempt(db, user):
    # Persist a bounded, user-scoped count, with no plate or secret in audit.
    # User lock serializes simultaneous attempts across application workers.
    if db.get_bind().dialect.name == 'sqlite':
        db.execute(update(User).where(User.id == user.id).values(id=User.id))
    db.scalar(select(User.id).where(User.id == user.id).with_for_update())
    cutoff = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(minutes=15)
    count = db.scalar(select(func.count(AuditLog.id)).where(AuditLog.user_id == user.id,
        AuditLog.action == 'TICKET_FEE_LOOKUP', AuditLog.created_at >= cutoff))
    if count >= 30:
        db.rollback()
        raise HTTPException(429, 'Đã tra cứu quá nhiều lần. Hãy thử lại sau.', headers={'Retry-After': '900'})
    db.add(AuditLog(user_id=user.id, username=user.username, action='TICKET_FEE_LOOKUP', resource='session_payment_access',
        method='POST', path='/api/v2/me/fee-lookup', status_code=202, success=True))
    db.commit()


def fee_lookup(db, user, data, config):
    customer_only(user)
    _admit_attempt(db, user)
    from expansion.site_models import ParkingSite
    from expansion.session_payment_service import lock_session, payment_status
    rows = db.execute(select(ParkingSession, Vehicle).join(Vehicle, Vehicle.id == ParkingSession.vehicle_id)
        .join(ParkingSlot, ParkingSlot.id == ParkingSession.parking_slot_id).join(Zone, Zone.id == ParkingSlot.zone_id)
        .join(ParkingSite, ParkingSite.id == Zone.site_id).where(Zone.site_id == data.site_id,
        ParkingSite.is_active.is_(True), ParkingSession.status == 'active', Vehicle.vehicle_type_id == data.vehicle_type_id,
        identity_expression(Vehicle.license_plate) == canonical_identity(data.license_plate)).limit(2)).all()
    if len(rows) != 1:
        raise HTTPException(404, NOT_FOUND)
    session, vehicle = rows[0]
    lock_session(db, session.id)
    db.refresh(vehicle)
    customer_id = db.scalar(select(PortalAccountLink.customer_id).where(PortalAccountLink.user_id == user.id))
    grant = db.get(PortalSessionGrant, session.id)
    owned = customer_id is not None and grant is not None and grant.customer_id == customer_id == vehicle.customer_id
    access = valid_access(db, user, session, vehicle)
    if not owned and access is None:
        credential = db.get(SessionTicketCredential, session.id)
        valid = (session.status == 'active' and credential is not None and credential.revoked_at is None
            and data.ticket_proof is not None and hmac.compare_digest(data.ticket_proof.encode(), _code(credential).encode()))
        if not valid:
            raise HTTPException(404, NOT_FOUND)
        access = db.scalar(select(SessionPaymentAccess).where(SessionPaymentAccess.user_id == user.id,
            SessionPaymentAccess.session_id == session.id))
        if access is None:
            access = SessionPaymentAccess(user_id=user.id, session_id=session.id)
            db.add(access)
        access.credential_version, access.vehicle_id = credential.version, vehicle.id
        access.customer_snapshot_id = vehicle.customer_id
        access.created_at, access.expires_at, access.revoked_at = business_now(), business_now() + timedelta(hours=24), None
        db.flush()
    status = payment_status(db, user, session.id, config)
    result = {'session': {'id': session.id, 'license_plate': vehicle.license_plate,
        'vehicle_type_id': vehicle.vehicle_type_id, 'check_in_time': session.check_in_time.replace(tzinfo=BUSINESS_TZ), 'status': session.status},
        'payment_status': status, 'access': {'kind': 'owned' if owned else 'ticket',
        'expires_at': None if owned else access.expires_at.replace(tzinfo=BUSINESS_TZ)}}
    db.commit()
    return result


def own_credit_receipts(user):
    """Only receipts for proposals personally created with narrow ticket access.

    Reading one's paid receipt remains possible after exit/expiry; this grants
    no cashier receipt, another payer's receipt, or vehicle/session history.
    """
    from expansion.session_payment_models import SessionFeeCredit, SessionFeeQuote
    from models.payment import Payment
    credits = select(SessionFeeCredit.id).join(SessionFeeQuote, SessionFeeQuote.id == SessionFeeCredit.quote_id).join(
        SessionPaymentAccess, SessionPaymentAccess.session_id == SessionFeeQuote.session_id).where(
        SessionFeeQuote.created_by_id == user.id, SessionPaymentAccess.user_id == user.id)
    return (Payment.source_type == 'session_credit') & Payment.source_id.in_(credits)
