"""Customer-owned and site-scoped staff access to accrued-fee online payments."""
from fastapi import APIRouter, Depends, Response

from database import get_db
from expansion import online_payment_service, session_payment_service
from expansion.online_payment_router import get_payos_gateway, write
from expansion.online_payment_schemas import LinkCancellation, get_online_payment_config
from expansion.session_payment_schemas import SessionFeeQuoteCreate, SessionFeeQuoteView, SessionPaymentLinkView
from services.auth_service import get_current_user

router = APIRouter(tags=["Online accrued parking fees"])


@router.get("/me/sessions/{identity}/payment-status")
def own_status(identity: str, response: Response, db=Depends(get_db), user=Depends(get_current_user),
               config=Depends(get_online_payment_config)):
    response.headers["Cache-Control"] = "private, no-store"
    return session_payment_service.payment_status(db, user, identity, config)


@router.get("/sites/{site_id}/sessions/{identity}/payment-status")
def site_status(site_id: int, identity: str, response: Response, db=Depends(get_db), user=Depends(get_current_user),
                config=Depends(get_online_payment_config)):
    response.headers["Cache-Control"] = "private, no-store"
    return session_payment_service.payment_status(db, user, identity, config, site_id=site_id)


@router.post("/me/sessions/{identity}/payment-quote", response_model=SessionFeeQuoteView)
def own_quote(identity: str, data: SessionFeeQuoteCreate, response: Response, db=Depends(get_db),
              user=Depends(get_current_user), config=Depends(get_online_payment_config)):
    response.headers["Cache-Control"] = "private, no-store"
    return write(db, lambda: session_payment_service.create_quote(db, user, identity, data, config))


@router.post("/sites/{site_id}/sessions/{identity}/payment-quote", response_model=SessionFeeQuoteView)
def site_quote(site_id: int, identity: str, data: SessionFeeQuoteCreate, response: Response, db=Depends(get_db),
               user=Depends(get_current_user), config=Depends(get_online_payment_config)):
    response.headers["Cache-Control"] = "private, no-store"
    return write(db, lambda: session_payment_service.create_quote(db, user, identity, data, config, site_id=site_id))


@router.get("/session-fee-quotes/{identity}/payment-link", response_model=SessionPaymentLinkView)
def read_link(identity: str, response: Response, db=Depends(get_db), user=Depends(get_current_user),
              config=Depends(get_online_payment_config)):
    response.headers["Cache-Control"] = "private, no-store"
    return online_payment_service.get_session_payment_link(db, user, identity, config)


@router.post("/session-fee-quotes/{identity}/payment-link", response_model=SessionPaymentLinkView)
def create_link(identity: str, response: Response, db=Depends(get_db), user=Depends(get_current_user),
                config=Depends(get_online_payment_config), gateway=Depends(get_payos_gateway)):
    response.headers["Cache-Control"] = "private, no-store"
    return write(db, lambda: online_payment_service.create_session_payment_link(db, user, identity, config, gateway))


@router.post("/session-fee-quotes/{identity}/payment-link/refresh", response_model=SessionPaymentLinkView)
def refresh_link(identity: str, response: Response, db=Depends(get_db), user=Depends(get_current_user),
                 config=Depends(get_online_payment_config), gateway=Depends(get_payos_gateway)):
    response.headers["Cache-Control"] = "private, no-store"
    return write(db, lambda: online_payment_service.reconcile_session_payment_link(db, user, identity, config, gateway))


@router.post("/session-fee-quotes/{identity}/payment-link/cancel", response_model=SessionPaymentLinkView)
def cancel_link(identity: str, data: LinkCancellation, response: Response, db=Depends(get_db), user=Depends(get_current_user),
                config=Depends(get_online_payment_config), gateway=Depends(get_payos_gateway)):
    response.headers["Cache-Control"] = "private, no-store"
    return write(db, lambda: online_payment_service.reconcile_session_payment_link(db, user, identity, config, gateway,
        cancel_reason=data.reason))
