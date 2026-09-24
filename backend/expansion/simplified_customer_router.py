"""Narrow, authenticated customer flows approved in the simplified preview."""
from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy import func, or_, select
from typing import Literal

from database import get_db
from expansion import declared_bookings, ticket_payment_access
from expansion.online_payment_schemas import get_online_payment_config
from expansion.portal_router import write
from expansion.simplified_customer_models import DeclaredParkingReservation
from expansion.simplified_customer_schemas import AdvanceBookingCreate, FeeLookup
from expansion.site_service import scoped_session
from services.auth_service import get_current_user

router = APIRouter(tags=['Customer fees and optional advance booking'])


@router.post('/me/fee-lookup')
def lookup(body: FeeLookup, response: Response, db=Depends(get_db), user=Depends(get_current_user),
           config=Depends(get_online_payment_config)):
    response.headers['Cache-Control'] = 'private, no-store'
    return write(db, lambda: ticket_payment_access.fee_lookup(db, user, body, config))


@router.get('/me/advance-bookings')
def bookings(site_id: int | None = Query(None, gt=0), limit: int = Query(50, ge=1, le=100),
             offset: int = Query(0, ge=0), db=Depends(get_db), user=Depends(get_current_user)):
    ticket_payment_access.customer_only(user)
    query = select(DeclaredParkingReservation).where(DeclaredParkingReservation.user_id == user.id)
    if site_id is not None:
        query = query.where(DeclaredParkingReservation.site_id == site_id)
    total = db.scalar(select(func.count()).select_from(query.subquery()))
    rows = db.scalars(query.order_by(DeclaredParkingReservation.created_at.desc(), DeclaredParkingReservation.id)
        .offset(offset).limit(limit))
    return {'items': [declared_bookings.serialize(db, row) for row in rows], 'total': total, 'limit': limit, 'offset': offset}


@router.post('/me/advance-bookings', status_code=201)
def book(body: AdvanceBookingCreate, db=Depends(get_db), user=Depends(get_current_user)):
    return write(db, lambda: declared_bookings.serialize(db, declared_bookings.create(db, user, body)))


@router.post('/me/advance-bookings/{identity}/cancel')
def cancel(identity: str, db=Depends(get_db), user=Depends(get_current_user)):
    return write(db, lambda: declared_bookings.serialize(db, declared_bookings.cancel(db, user, identity)))


@router.get('/sites/{site_id}/advance-bookings')
def reception(site_id: int, status: Literal['confirmed', 'arrived', 'cancelled', 'expired'] | None = None,
              limit: int = Query(50, ge=1, le=100), offset: int = Query(0, ge=0),
              db=Depends(get_db), user=Depends(get_current_user)):
    from expansion.site_scope import require_site_access
    from models.parking_slot import ParkingSlot
    require_site_access(db, user, site_id)
    model = DeclaredParkingReservation
    query = select(model).where(model.site_id == site_id)
    now = declared_bookings.server_now()
    if status == 'confirmed':
        query = query.where(model.status == 'confirmed', model.arrival_deadline > now)
    elif status == 'expired':
        query = query.where(or_(model.status == 'expired', (model.status == 'confirmed') & (model.arrival_deadline <= now)))
    elif status is not None:
        query = query.where(model.status == status)
    total = db.scalar(select(func.count()).select_from(query.subquery()))
    rows = db.execute(query.add_columns(ParkingSlot).join(ParkingSlot, ParkingSlot.id == model.slot_id)
        .order_by(model.start_at.desc(), model.id).offset(offset).limit(limit)).all()
    return {'items': [{**declared_bookings.serialize(db, row), 'user_id': row.user_id} for row, slot in rows],
        'total': total, 'limit': limit, 'offset': offset}


@router.post('/sites/{site_id}/sessions/{session_id}/ticket-payment-code/rotate')
def rotate(site_id: int, session_id: str, response: Response, db=Depends(get_db), user=Depends(get_current_user)):
    from expansion.site_scope import require_site_access
    require_site_access(db, user, site_id, 'manager')
    session = scoped_session(db, user, site_id, session_id)
    response.headers['Cache-Control'] = 'private, no-store'
    return {'payment_access_code': write(db, lambda: ticket_payment_access.rotate_ticket_payment_code(db, session))}
