"""Site-scoped cash operations; global/unknown historical rows remain admin-only."""
from datetime import date
from types import SimpleNamespace

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy import case, func, select
from sqlalchemy.exc import IntegrityError, OperationalError

from core.clock import business_now, day_bounds
from database import get_db
from expansion.site_models import SiteMembership
from expansion.site_scope import is_global_admin, require_site_access
from models.cash_shift import CashShift
from models.payment import Payment
from schemas.cash_shift import CashShiftClose, CashShiftOpen
from schemas.payment import RefundCreate
from services.auth_service import get_current_user
from services.cash_shift_service import CashShiftService
from services.payment_service import PaymentService, signed_exact_vnd

router = APIRouter()


def _manager(db, actor, site_id):
    return is_global_admin(actor) or (actor.role.name == "manager" and db.scalar(select(SiteMembership.id).where(
        SiteMembership.site_id == site_id, SiteMembership.user_id == actor.id, SiteMembership.role == "manager")) is not None)


def _scope(db, actor, site_id, model):
    require_site_access(db, actor, site_id)
    statement = select(model).where(model.site_id == site_id)
    if not _manager(db, actor, site_id):
        statement = statement.where((model.staff_id if model is CashShift else model.collected_by_id) == actor.id)
    return statement


def _row(db, actor, site_id, model, identity):
    row = db.scalar(_scope(db, actor, site_id, model).where(model.id == identity))
    if row is None:
        raise HTTPException(404, "Không tìm thấy bản ghi trong phạm vi được cấp quyền.")
    return row


def _write(db, operation):
    try:
        result = operation()
        db.commit()
        return result
    except HTTPException:
        db.rollback()
        raise
    except (IntegrityError, OperationalError) as exc:
        db.rollback()
        raise HTTPException(409, "Dữ liệu vừa thay đổi. Hãy tải lại trước khi xác nhận.") from exc


@router.get("/sites/{site_id}/cash-shifts")
def shifts(site_id: int, page: int = Query(1, ge=1), size: int = Query(25, ge=1, le=100),
           db=Depends(get_db), actor=Depends(get_current_user)):
    statement = _scope(db, actor, site_id, CashShift)
    total = db.scalar(select(func.count()).select_from(statement.subquery()))
    rows = db.scalars(statement.order_by(CashShift.opened_at.desc(), CashShift.id).offset((page - 1) * size).limit(size))
    return {"total": total, "page": page, "size": size,
            "items": [CashShiftService.get_summary(db, row.id, actor) for row in rows]}


@router.post("/sites/{site_id}/cash-shifts", status_code=201)
def open_shift(site_id: int, body: CashShiftOpen, db=Depends(get_db), actor=Depends(get_current_user)):
    require_site_access(db, actor, site_id)
    def operation():
        row = CashShiftService.open_shift(db, actor, site_id=site_id, **body.model_dump())
        return CashShiftService.get_summary(db, row.id, actor)
    return _write(db, operation)


@router.get("/sites/{site_id}/cash-shifts/{identity}")
def shift(site_id: int, identity: str, db=Depends(get_db), actor=Depends(get_current_user)):
    _row(db, actor, site_id, CashShift, identity)
    return CashShiftService.get_summary(db, identity, actor)


@router.post("/sites/{site_id}/cash-shifts/{identity}/close")
def close_shift(site_id: int, identity: str, body: CashShiftClose, db=Depends(get_db), actor=Depends(get_current_user)):
    _row(db, actor, site_id, CashShift, identity)
    return _write(db, lambda: CashShiftService.close_shift(db, identity, actor, **body.model_dump()))


def _payments(db, actor, site_id, date_from, date_to, shift_id=None):
    statement = _scope(db, actor, site_id, Payment)
    if date_from and date_to and date_from > date_to:
        raise HTTPException(422, "Ngày bắt đầu phải trước hoặc bằng ngày kết thúc.")
    try:
        if date_from:
            statement = statement.where(Payment.created_at >= day_bounds(date_from)[0])
        if date_to:
            statement = statement.where(Payment.created_at < day_bounds(date_to)[1])
    except (ValueError, OverflowError) as exc:
        raise HTTPException(422, "Ngày nằm ngoài phạm vi được hỗ trợ.") from exc
    if shift_id:
        statement = statement.where(Payment.shift_id == shift_id)
    return statement


@router.get("/sites/{site_id}/payments")
def payments(site_id: int, page: int = Query(1, ge=1), size: int = Query(25, ge=1, le=100),
             date_from: date | None = None, date_to: date | None = None, shift_id: str | None = Query(None, max_length=36),
             db=Depends(get_db), actor=Depends(get_current_user)):
    statement = _payments(db, actor, site_id, date_from, date_to, shift_id)
    total = db.scalar(select(func.count()).select_from(statement.subquery()))
    rows = db.scalars(statement.order_by(Payment.created_at.desc(), Payment.id).offset((page - 1) * size).limit(size))
    return {"total": total, "page": page, "size": size, "items": [PaymentService.serialize(db, row) for row in rows]}


@router.get("/sites/{site_id}/revenue")
def revenue(site_id: int, date_from: date | None = None, date_to: date | None = None,
            db=Depends(get_db), actor=Depends(get_current_user)):
    start, end = date_from or business_now().date(), date_to or business_now().date()
    rows = _payments(db, actor, site_id, start, end).where(Payment.method != "demo").subquery()
    signed = case((rows.c.kind == "refund", -rows.c.amount), else_=rows.c.amount)
    total, unassigned, count = db.execute(select(func.coalesce(func.sum(signed), 0),
        func.coalesce(func.sum(case((rows.c.shift_id.is_(None), signed), else_=0)), 0), func.count()).select_from(rows)).one()
    return {"site_id": site_id, "date_from": start, "date_to": end,
            "scope": "site" if _manager(db, actor, site_id) else "own_collections",
            "total_revenue": signed_exact_vnd(total), "unassigned_revenue": signed_exact_vnd(unassigned),
            "payment_count": count, "note": "Theo ngày thu/hoàn; không gồm QR DEMO hoặc chứng từ lịch sử chưa xác định bãi."}


@router.get("/sites/{site_id}/payments/{identity}/pdf")
def receipt_pdf(site_id: int, identity: str, db=Depends(get_db), actor=Depends(get_current_user)):
    from expansion.portal_documents import build_receipt_pdf
    receipt = _row(db, actor, site_id, Payment, identity)
    # Site staff need the receipt, not an unrelated customer's contact details.
    return Response(build_receipt_pdf(receipt, SimpleNamespace(full_name="Khách gửi xe")), media_type="application/pdf",
        headers={"Cache-Control": "no-store", "Content-Disposition": 'attachment; filename="parkingai-receipt.pdf"'})


@router.post("/sites/{site_id}/payments/{identity}/refund")
def refund(site_id: int, identity: str, body: RefundCreate, db=Depends(get_db), actor=Depends(get_current_user)):
    require_site_access(db, actor, site_id, "manager")
    original = _row(db, actor, site_id, Payment, identity)
    if original.method == "demo":
        raise HTTPException(409, "Hoàn QR DEMO phải đi qua yêu cầu và phê duyệt tại cổng khách hàng.")
    def operation():
        row = PaymentService.refund(db, identity, actor, **body.model_dump())
        return PaymentService.serialize(db, row)
    return _write(db, operation)
