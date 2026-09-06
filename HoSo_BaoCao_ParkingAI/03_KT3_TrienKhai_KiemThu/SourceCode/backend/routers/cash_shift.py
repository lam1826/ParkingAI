from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError, OperationalError
from sqlalchemy.orm import Session

from database import get_db
from models.cash_shift import CashShift
from models.user import User
from schemas.cash_shift import CashShiftClose, CashShiftListResponse, CashShiftOpen, CashShiftResponse
from services.auth_service import RoleChecker
from services.cash_shift_service import CashShiftService

router = APIRouter()


@router.get("", response_model=CashShiftListResponse)
def list_shifts(
    page: int = Query(1, ge=1), size: int = Query(25, ge=1, le=100),
    status: Literal["open", "closed"] | None = None,
    staff_id: int | None = Query(None, ge=1), db: Session = Depends(get_db),
    actor: User = Depends(RoleChecker("staff")),
):
    statement = select(CashShift)
    if actor.role.name not in {"manager", "admin"}:
        if staff_id is not None and staff_id != actor.id:
            raise HTTPException(403, "Bạn chỉ được xem ca của mình.")
        statement = statement.where(CashShift.staff_id == actor.id)
    elif staff_id is not None:
        statement = statement.where(CashShift.staff_id == staff_id)
    if status is not None:
        statement = statement.where(CashShift.status == status)
    total = db.scalar(select(func.count()).select_from(statement.subquery()))
    rows = db.scalars(statement.order_by(CashShift.opened_at.desc(), CashShift.id).offset((page - 1) * size).limit(size)).all()
    return {"total": total, "page": page, "size": size, "items": [CashShiftService.get_summary(db, row.id, actor) for row in rows]}


@router.post("", response_model=CashShiftResponse, status_code=201)
def open_shift(payload: CashShiftOpen, db: Session = Depends(get_db), actor: User = Depends(RoleChecker("staff"))):
    try:
        shift = CashShiftService.open_shift(db, actor, **payload.model_dump())
        db.commit()
        return CashShiftService.get_summary(db, shift.id, actor)
    except (IntegrityError, OperationalError) as exc:
        db.rollback()
        raise HTTPException(409, "Không thể mở ca. Bạn có thể đã có một ca đang mở.") from exc


@router.get("/{shift_id}", response_model=CashShiftResponse)
def get_shift(shift_id: str, db: Session = Depends(get_db), actor: User = Depends(RoleChecker("staff"))):
    return CashShiftService.get_summary(db, shift_id, actor)


@router.post("/{shift_id}/close", response_model=CashShiftResponse)
def close_shift(shift_id: str, payload: CashShiftClose, db: Session = Depends(get_db), actor: User = Depends(RoleChecker("staff"))):
    try:
        summary = CashShiftService.close_shift(db, shift_id, actor, **payload.model_dump())
        db.commit()
        return summary
    except (IntegrityError, OperationalError) as exc:
        db.rollback()
        raise HTTPException(409, "Ca đang có giao dịch hoặc đã chốt. Vui lòng tải lại và thử lại.") from exc
