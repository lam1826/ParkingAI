"""Server-side ownership predicates shared by portal, support and refund flows.

Everything a customer may read, link or ask a refund for must satisfy one of
these predicates. Nothing here trusts identifiers or amounts sent by a client.
"""
from sqlalchemy import cast, or_, select, String

from expansion.portal_models import PortalOrder, PortalSessionGrant
from models.monthly_pass import MonthlyPass
from models.parking_session import ParkingSession
from models.payment import Payment


def own_session_ids(customer):
    return select(PortalSessionGrant.parking_session_id).where(PortalSessionGrant.customer_id == customer.id)


def own_order_ids(user, customer):
    return select(PortalOrder.id).where(PortalOrder.user_id == user.id, PortalOrder.customer_id == customer.id)


def owned_receipt_predicate(user, customer):
    """Receipts and refunds whose source belongs to this verified customer."""
    from expansion.session_payment_models import SessionFeeCredit
    own_periods = select(cast(MonthlyPass.id, String)).where(MonthlyPass.customer_id == customer.id)
    own_sessions = own_session_ids(customer)
    own_credits = select(SessionFeeCredit.id).where(SessionFeeCredit.session_id.in_(own_sessions))
    return or_(
        (Payment.source_type == "session_credit") & Payment.source_id.in_(own_credits),
        (Payment.source_type == "portal_order") & Payment.source_id.in_(own_order_ids(user, customer)),
        (Payment.source_type == "monthly_pass") & Payment.source_id.in_(own_periods),
        (Payment.source_type == "parking_session") & Payment.source_id.in_(own_sessions),
    )


def owned_receipt(db, user, customer, identity):
    return db.scalar(select(Payment).where(Payment.id == identity, owned_receipt_predicate(user, customer)))


def owned_session(db, customer, identity):
    return db.scalar(select(ParkingSession).where(ParkingSession.id == identity,
        ParkingSession.id.in_(own_session_ids(customer))))


def owned_order(db, user, customer, identity):
    return db.scalar(select(PortalOrder).where(PortalOrder.id == identity,
        PortalOrder.user_id == user.id, PortalOrder.customer_id == customer.id))
