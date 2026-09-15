"""Authenticated order controls and a bounded HMAC-only payOS inbox endpoint."""
import httpx
from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from starlette.concurrency import run_in_threadpool

from database import get_db
from expansion import online_payment_service as service
from expansion.online_payment_schemas import (
    LinkCancellation, PaymentLinkView, ReviewDecisionCreate, get_online_payment_config,
)
from expansion.payos_gateway import PayOSGateway, PayOSGatewayError
from services.auth_service import RoleChecker, get_current_user

router = APIRouter(tags=["payOS payments (disabled until configured)"])
manager = RoleChecker("manager")


def get_payos_gateway(config=Depends(get_online_payment_config)):
    if not config.PAYOS_ENABLED:
        raise HTTPException(503, "Thanh toán payOS chưa được bật.")
    with httpx.Client(trust_env=False, follow_redirects=False) as client:
        yield PayOSGateway(config.adapter_settings(), client)


def write(db, operation):
    try:
        return operation()
    except Exception:
        db.rollback()
        raise


@router.get("/me/orders/{identity}/payment-link", response_model=PaymentLinkView)
def payment_link(identity: str, response: Response, db=Depends(get_db), user=Depends(get_current_user),
                 config=Depends(get_online_payment_config)):
    response.headers["Cache-Control"] = "private, no-store"
    return service.get_payment_link(db, user, identity, config)


@router.post("/me/orders/{identity}/payment-link", response_model=PaymentLinkView)
def create_link(identity: str, response: Response, db=Depends(get_db), user=Depends(get_current_user),
                config=Depends(get_online_payment_config), gateway=Depends(get_payos_gateway)):
    response.headers["Cache-Control"] = "private, no-store"
    return write(db, lambda: service.create_payment_link(db, user, identity, config, gateway))


@router.post("/me/orders/{identity}/payment-link/refresh", response_model=PaymentLinkView)
def refresh_link(identity: str, response: Response, db=Depends(get_db), user=Depends(get_current_user),
                 config=Depends(get_online_payment_config), gateway=Depends(get_payos_gateway)):
    response.headers["Cache-Control"] = "private, no-store"
    return write(db, lambda: service.reconcile_payment_link(db, user, identity, config, gateway))


@router.post("/me/orders/{identity}/payment-link/cancel", response_model=PaymentLinkView)
def cancel_link(identity: str, data: LinkCancellation, response: Response, db=Depends(get_db),
                user=Depends(get_current_user), config=Depends(get_online_payment_config),
                gateway=Depends(get_payos_gateway)):
    response.headers["Cache-Control"] = "private, no-store"
    return write(db, lambda: service.reconcile_payment_link(db, user, identity, config, gateway,
        cancel_reason=data.reason))


@router.post("/payments/payos/webhook")
async def webhook(request: Request, db=Depends(get_db), config=Depends(get_online_payment_config),
                  gateway=Depends(get_payos_gateway)):
    raw = bytearray()
    async for chunk in request.stream():
        raw.extend(chunk)
        if len(raw) > config.PAYOS_MAX_PAYLOAD_BYTES:
            raise HTTPException(413, "Thông báo thanh toán vượt giới hạn.")
    try:
        await run_in_threadpool(write, db, lambda: service.accept_webhook(db, bytes(raw), config, gateway))
    except PayOSGatewayError:
        raise HTTPException(400, "Thông báo thanh toán không hợp lệ.") from None
    # payOS receives success only after the inbox transaction committed. No
    # provider redirect, browser body or DEMO event is used to confirm payment.
    return {"success": True}


@router.get("/sites/{site_id}/online-payments/review")
def review_list(site_id: int, limit: int = Query(50, ge=1, le=100), offset: int = Query(0, ge=0),
                db=Depends(get_db), user=Depends(manager)):
    return service.list_review(db, user, site_id, limit=limit, offset=offset)


@router.post("/sites/{site_id}/online-payments/review/{identity}/decisions")
def review_decision(site_id: int, identity: str, data: ReviewDecisionCreate, db=Depends(get_db), user=Depends(manager)):
    return write(db, lambda: service.record_review_decision(db, user, site_id, identity, data))
