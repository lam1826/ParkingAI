from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError, OperationalError
from sqlalchemy.orm import Session

from core.clock import day_bounds
from database import get_db
from models.payment import Payment
from models.user import User
from schemas.payment import PaymentKind, PaymentListResponse, PaymentResponse, PaymentSource, RefundCreate
from services.auth_service import RoleChecker
from services.payment_service import PaymentService

router = APIRouter()


@router.get("", response_model=PaymentListResponse)
def list_payments(
    page: int = Query(1, ge=1), size: int = Query(25, ge=1, le=100),
    source_type: PaymentSource | None = None, source_id: str | None = Query(None, max_length=36),
    kind: PaymentKind | None = None, shift_id: str | None = Query(None, max_length=36),
    date_from: date | None = None, date_to: date | None = None,
    db: Session = Depends(get_db), actor: User = Depends(RoleChecker("staff")),
):
    if date_from and date_to and date_from > date_to:
        raise HTTPException(422, "Ngày bắt đầu phải trước hoặc bằng ngày kết thúc.")
    statement = select(Payment)
    if actor.role.name not in {"manager", "admin"}:
        statement = statement.where(Payment.collected_by_id == actor.id)
    for column, value in ((Payment.source_type, source_type), (Payment.source_id, source_id),
                          (Payment.kind, kind), (Payment.shift_id, shift_id)):
        if value is not None:
            statement = statement.where(column == value)
    try:
        if date_from:
            statement = statement.where(Payment.created_at >= day_bounds(date_from)[0])
        if date_to:
            statement = statement.where(Payment.created_at < day_bounds(date_to)[1])
    except (ValueError, OverflowError) as exc:
        raise HTTPException(422, "Ngày nằm ngoài phạm vi được hỗ trợ.") from exc
    total = db.scalar(select(func.count()).select_from(statement.subquery()))
    items = db.scalars(statement.order_by(Payment.created_at.desc(), Payment.id).offset((page - 1) * size).limit(size)).all()
    return {"total": total, "page": page, "size": size, "items": [PaymentService.serialize(db, row) for row in items]}


@router.post("/{payment_id}/refund", response_model=PaymentResponse)
def refund_payment(
    payment_id: str, payload: RefundCreate, db: Session = Depends(get_db),
    actor: User = Depends(RoleChecker("manager")),
):
    try:
        payment = PaymentService.refund(db, payment_id, actor, **payload.model_dump())
        db.commit()
        return PaymentService.serialize(db, payment)
    except (IntegrityError, OperationalError) as exc:
        db.rollback()
        raise HTTPException(409, "Giao dịch đang được xử lý hoặc dữ liệu hoàn tiền không còn hợp lệ. Vui lòng tải lại.") from exc


@router.get("/{payment_id}", response_model=PaymentResponse)
def get_payment(payment_id: str, db: Session = Depends(get_db), actor: User = Depends(RoleChecker("staff"))):
    payment = db.get(Payment, payment_id)
    if payment is None:
        raise HTTPException(404, "Không tìm thấy giao dịch.")
    if payment.collected_by_id != actor.id and actor.role.name not in {"manager", "admin"}:
        raise HTTPException(403, "Bạn chỉ được xem giao dịch của mình.")
    return PaymentService.serialize(db, payment)
