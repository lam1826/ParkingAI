from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from core.clock import business_now
from core.money import require_exact_vnd
from models.cash_shift import CashShift
from models.payment import Payment
from models.user import User
from services.payment_service import lock_cash_operator, signed_exact_vnd


class CashShiftService:
    @staticmethod
    def _check_access(shift: CashShift, actor: User) -> None:
        if shift.staff_id != actor.id and actor.role.name not in {"manager", "admin"}:
            raise HTTPException(403, "Bạn chỉ được xem hoặc chốt ca của mình.")

    @staticmethod
    def open_shift(db: Session, actor: User, *, opening_cash: int = 0) -> CashShift:
        opening_cash = require_exact_vnd(opening_cash)
        lock_cash_operator(db, actor.id)
        if db.execute(select(CashShift.id).where(CashShift.staff_id == actor.id, CashShift.status == "open")).first():
            raise HTTPException(409, "Bạn đang có ca mở. Hãy chốt ca hiện tại trước.")
        shift = CashShift(staff_id=actor.id, opened_at=business_now(), opening_cash=opening_cash, status="open")
        db.add(shift)
        db.flush()
        return shift

    @staticmethod
    def get_summary(db: Session, shift_id: str, actor: User) -> dict:
        shift = db.get(CashShift, shift_id)
        if shift is None:
            raise HTTPException(404, "Không tìm thấy ca làm việc.")
        CashShiftService._check_access(shift, actor)
        totals = {"cash_receipts": 0, "cash_refunds": 0, "transfer_receipts": 0, "transfer_refunds": 0}
        count = 0
        for payment in db.execute(select(Payment).where(Payment.shift_id == shift.id)).scalars():
            totals[f"{payment.method}_{payment.kind}s"] += require_exact_vnd(payment.amount)
            count += 1
        totals = {key: require_exact_vnd(value) for key, value in totals.items()}
        expected = signed_exact_vnd(shift.opening_cash + totals["cash_receipts"] - totals["cash_refunds"])
        staff = db.get(User, shift.staff_id)
        return {
            "id": shift.id, "staff_id": shift.staff_id, "staff_name": staff.full_name if staff else "",
            "opened_at": shift.opened_at, "closed_at": shift.closed_at, "status": shift.status,
            "opening_cash": shift.opening_cash, "counted_cash": shift.counted_cash,
            "expected_cash": shift.expected_cash if shift.status == "closed" else expected,
            "difference": shift.difference,
            **totals,
            "net_revenue": signed_exact_vnd(totals["cash_receipts"] + totals["transfer_receipts"] - totals["cash_refunds"] - totals["transfer_refunds"]),
            "payment_count": count,
        }

    @staticmethod
    def close_shift(db: Session, shift_id: str, actor: User, *, counted_cash: int) -> dict:
        counted_cash = require_exact_vnd(counted_cash)
        shift = db.get(CashShift, shift_id)
        if shift is None:
            raise HTTPException(404, "Không tìm thấy ca làm việc.")
        CashShiftService._check_access(shift, actor)
        # Collection and close take the same staff lock, even when a manager
        # closes another operator's shift. Refresh after waiting for that lock.
        lock_cash_operator(db, shift.staff_id)
        db.refresh(shift, with_for_update=True)
        if shift.status != "open":
            raise HTTPException(409, "Ca đã chốt; không thể thay đổi số tiền kiểm đếm.")
        summary = CashShiftService.get_summary(db, shift_id, actor)
        shift.closed_at = business_now()
        shift.counted_cash = counted_cash
        shift.expected_cash = summary["expected_cash"]
        shift.difference = signed_exact_vnd(counted_cash - shift.expected_cash)
        shift.status = "closed"
        db.flush()
        return CashShiftService.get_summary(db, shift_id, actor)
