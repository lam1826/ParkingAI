"""Customer support threads and receipt refund requests (prefix /api/v2)."""
from typing import Literal

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, ConfigDict, Field

from database import get_db
from expansion import refund_service, support_service
from services.auth_service import get_current_user

router = APIRouter(tags=["Customer support and refunds"])


class Input(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class SupportRequestCreate(Input):
    subject: str = Field(min_length=3, max_length=150)
    message: str = Field(min_length=1, max_length=2000)
    category: Literal["general", "order", "session", "receipt", "refund"] = "general"
    site_id: int | None = Field(default=None, strict=True, gt=0)
    linked_type: Literal["order", "session", "receipt", "refund_request"] | None = None
    linked_id: str | None = Field(default=None, min_length=1, max_length=36)


class SupportMessage(Input):
    body: str = Field(min_length=1, max_length=2000)


class SupportClose(Input):
    note: str = Field(default="", max_length=2000)


class RefundRequestCreate(Input):
    reason: str = Field(min_length=1, max_length=500)


class RefundDecision(Input):
    note: str = Field(default="", max_length=500)
    amount: int | None = Field(default=None, strict=True, gt=0)


class RefundRecord(Input):
    method: Literal["cash", "transfer"]
    external_reference: str | None = Field(default=None, max_length=120)
    confirmed: bool = Field(strict=True)


def write(db, operation):
    try:
        result = operation()
        db.commit()
        return result
    except Exception:
        db.rollback()
        raise


# --- customer support ---------------------------------------------------------------

@router.post("/me/support-requests", status_code=201)
def support_create(data: SupportRequestCreate, db=Depends(get_db), user=Depends(get_current_user)):
    if data.linked_type is not None and data.linked_id is None:
        from fastapi import HTTPException
        raise HTTPException(422, "Cần chọn tài nguyên để liên kết.")
    item = write(db, lambda: support_service.create_request(db, user, data))
    return support_service.customer_detail(db, user, item.id)


@router.get("/me/support-requests")
def support_list(status: Literal["open", "answered", "closed"] | None = None, limit: int = Query(50, ge=1, le=100),
                 offset: int = Query(0, ge=0), db=Depends(get_db), user=Depends(get_current_user)):
    return {"items": support_service.customer_list(db, user, status=status, limit=limit, offset=offset)}


@router.get("/me/support-requests/{identity}")
def support_detail(identity: str, db=Depends(get_db), user=Depends(get_current_user)):
    return support_service.customer_detail(db, user, identity)


@router.post("/me/support-requests/{identity}/messages")
def support_reply(identity: str, data: SupportMessage, db=Depends(get_db), user=Depends(get_current_user)):
    write(db, lambda: support_service.customer_reply(db, user, identity, data.body))
    return support_service.customer_detail(db, user, identity)


@router.post("/me/support-requests/{identity}/close")
def support_close(identity: str, db=Depends(get_db), user=Depends(get_current_user)):
    write(db, lambda: support_service.customer_close(db, user, identity))
    return support_service.customer_detail(db, user, identity)


@router.get("/sites/{site_id}/support-requests")
def site_support_list(site_id: int, status: Literal["open", "answered", "closed"] | None = None,
                      category: Literal["general", "order", "session", "receipt", "refund"] | None = None,
                      limit: int = Query(50, ge=1, le=100), offset: int = Query(0, ge=0),
                      db=Depends(get_db), actor=Depends(get_current_user)):
    return {"items": support_service.manager_list(db, actor, site_id, status=status, category=category, limit=limit, offset=offset)}


@router.get("/sites/{site_id}/support-requests/{identity}")
def site_support_detail(site_id: int, identity: str, db=Depends(get_db), actor=Depends(get_current_user)):
    return support_service.manager_detail(db, actor, site_id, identity)


@router.post("/sites/{site_id}/support-requests/{identity}/messages")
def site_support_reply(site_id: int, identity: str, data: SupportMessage, db=Depends(get_db), actor=Depends(get_current_user)):
    write(db, lambda: support_service.manager_reply(db, actor, site_id, identity, data.body))
    return support_service.manager_detail(db, actor, site_id, identity)


@router.post("/sites/{site_id}/support-requests/{identity}/close")
def site_support_close(site_id: int, identity: str, data: SupportClose, db=Depends(get_db), actor=Depends(get_current_user)):
    write(db, lambda: support_service.manager_close(db, actor, site_id, identity, data.note))
    return support_service.manager_detail(db, actor, site_id, identity)


@router.post("/sites/{site_id}/support-requests/{identity}/reopen")
def site_support_reopen(site_id: int, identity: str, db=Depends(get_db), actor=Depends(get_current_user)):
    write(db, lambda: support_service.manager_reopen(db, actor, site_id, identity))
    return support_service.manager_detail(db, actor, site_id, identity)


# --- refund requests ------------------------------------------------------------------

@router.post("/me/receipts/{identity}/refund-requests", status_code=201)
def refund_create(identity: str, data: RefundRequestCreate, db=Depends(get_db), user=Depends(get_current_user)):
    item = write(db, lambda: refund_service.create_request(db, user, identity, data.reason))
    return refund_service.serialize(item, order_id=refund_service._order_ids(db, [item]).get(item.receipt_id))


@router.get("/sites/{site_id}/refund-requests")
def site_refunds(site_id: int, status: Literal["pending", "reviewing", "approved", "rejected", "refunded"] | None = None,
                 limit: int = Query(50, ge=1, le=100), offset: int = Query(0, ge=0),
                 db=Depends(get_db), actor=Depends(get_current_user)):
    return {"items": refund_service.manager_list(db, actor, site_id, status=status, limit=limit, offset=offset)}


@router.get("/sites/{site_id}/refund-requests/{identity}")
def site_refund_detail(site_id: int, identity: str, db=Depends(get_db), actor=Depends(get_current_user)):
    return refund_service.manager_detail(db, actor, site_id, identity)


@router.post("/sites/{site_id}/refund-requests/{identity}/review")
def site_refund_review(site_id: int, identity: str, data: RefundDecision, db=Depends(get_db), actor=Depends(get_current_user)):
    write(db, lambda: refund_service.start_review(db, actor, site_id, identity, data.note))
    return refund_service.manager_detail(db, actor, site_id, identity)


@router.post("/sites/{site_id}/refund-requests/{identity}/approve")
def site_refund_approve(site_id: int, identity: str, data: RefundDecision, db=Depends(get_db), actor=Depends(get_current_user)):
    write(db, lambda: refund_service.approve(db, actor, site_id, identity, amount=data.amount, note=data.note))
    return refund_service.manager_detail(db, actor, site_id, identity)


@router.post("/sites/{site_id}/refund-requests/{identity}/reject")
def site_refund_reject(site_id: int, identity: str, data: RefundDecision, db=Depends(get_db), actor=Depends(get_current_user)):
    write(db, lambda: refund_service.reject(db, actor, site_id, identity, data.note))
    return refund_service.manager_detail(db, actor, site_id, identity)


@router.post("/sites/{site_id}/refund-requests/{identity}/record-refund")
def site_refund_record(site_id: int, identity: str, data: RefundRecord, db=Depends(get_db), actor=Depends(get_current_user)):
    if data.confirmed is not True:
        from fastapi import HTTPException
        raise HTTPException(422, "Cần xác nhận đã hoàn tiền ngoài hệ thống trước khi ghi nhận.")
    write(db, lambda: refund_service.record_refund(db, actor, site_id, identity, method=data.method,
        external_reference=data.external_reference))
    return refund_service.manager_detail(db, actor, site_id, identity)
