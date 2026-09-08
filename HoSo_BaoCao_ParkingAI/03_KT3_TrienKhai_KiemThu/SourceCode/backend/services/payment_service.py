"""A shared cash ledger; callers own commit/rollback for business mutations."""

from datetime import datetime, timezone

from fastapi import HTTPException
from sqlalchemy import cast, exists, literal, select, String, text, union_all
from sqlalchemy.orm import Session

from core.clock import BUSINESS_TZ, business_now
from core.money import require_exact_vnd, sum_exact_vnd
from models.cash_shift import CashShift
from models.monthly_pass import MonthlyPass
from models.parking_session import ParkingSession
from models.payment import Payment
from models.user import User
from services.auth_service import check_permission


def signed_exact_vnd(value: int, *, label: str = "Tổng tiền") -> int:
    """Refunds can make a day/shift negative; keep the JSON exactness bound."""
    require_exact_vnd(abs(value), label=label)
    return value


def lock_cash_operator(db: Session, staff_id: int) -> None:
    """Serialize collection/open/close for the operator in this transaction.

    PostgreSQL locks the user row. SQLite's no-op write acquires the database
    writer lock even when the session already made authentication reads.
    """
    if db.get_bind().dialect.name == "sqlite":
        result = db.execute(text("UPDATE users SET id = id WHERE id = :staff_id"), {"staff_id": staff_id})
        found = result.rowcount > 0
    else:
        found = db.execute(select(User.id).where(User.id == staff_id).with_for_update()).scalar_one_or_none() is not None
    if not found:
        raise HTTPException(404, "Nhân viên thu tiền không tồn tại.")


class PaymentService:
    @staticmethod
    def record_receipt(
        db: Session, source_type: str, source_id, amount: int,
        collected_by_id: int | None, method: str = "cash", created_at: datetime | None = None,
    ) -> Payment:
        """Idempotently collect once per source; flush only, never commit."""
        if source_type not in {"parking_session", "monthly_pass"} or method not in {"cash", "transfer", "demo"}:
            raise HTTPException(422, "Nguồn thu hoặc phương thức thanh toán không hợp lệ.")
        if method == "demo" and (source_type != "monthly_pass" or collected_by_id is not None):
            raise HTTPException(422, "Thu mô phỏng chỉ áp dụng đơn vé tháng và không gán nhân viên thu tiền.")
        amount = require_exact_vnd(amount)
        source_id = str(source_id)
        if not source_id or len(source_id) > 36:
            raise HTTPException(422, "Mã nguồn thu không hợp lệ.")
        if collected_by_id is not None:
            lock_cash_operator(db, collected_by_id)
        existing = db.execute(select(Payment).where(
            Payment.source_type == source_type, Payment.source_id == source_id, Payment.kind == "receipt"
        )).scalar_one_or_none()
        if existing is not None:
            if existing.amount != amount or existing.method != method:
                raise HTTPException(409, "Nguồn thu đã có chứng từ với số tiền hoặc phương thức khác.")
            return existing
        when = created_at or business_now()
        if when.tzinfo is not None:
            when = when.astimezone(BUSINESS_TZ).replace(tzinfo=None)
        shift = None
        if collected_by_id is not None:
            shift = db.execute(select(CashShift).where(
                CashShift.staff_id == collected_by_id, CashShift.status == "open",
                CashShift.opened_at <= when,
            ).with_for_update()).scalar_one_or_none()
        payment = Payment(
            source_type=source_type, source_id=source_id, kind="receipt", amount=amount,
            method=method, collected_by_id=collected_by_id,
            shift_id=shift.id if shift else None, created_at=when,
            idempotency_key=f"receipt:{source_type}:{source_id}",
        )
        db.add(payment)
        db.flush()
        return payment

    @staticmethod
    def refund(
        db: Session, payment_id: str, actor: User, *, amount: int,
        method: str, reason: str, idempotency_key: str,
    ) -> Payment:
        """Record an authorized compensating transaction without altering a receipt."""
        check_permission(actor, "manager")
        amount = require_exact_vnd(amount)
        if amount == 0 or method not in {"cash", "transfer", "demo"} or not reason.strip():
            raise HTTPException(422, "Số tiền, lý do hoặc phương thức hoàn tiền không hợp lệ.")
        lock_cash_operator(db, actor.id)
        original = db.execute(select(Payment).where(Payment.id == payment_id).with_for_update()).scalar_one_or_none()
        if original is None:
            raise HTTPException(404, "Không tìm thấy phiếu thu.")
        if original.kind != "receipt":
            raise HTTPException(409, "Chỉ được hoàn tiền từ phiếu thu gốc.")
        if (original.method == "demo") != (method == "demo"):
            raise HTTPException(409, "Giao dịch mô phỏng chỉ được hoàn bằng luồng mô phỏng.")
        refund_key = f"refund:{idempotency_key}"
        existing = db.execute(select(Payment).where(Payment.idempotency_key == refund_key)).scalar_one_or_none()
        if existing is not None:
            if (existing.original_payment_id != original.id or existing.amount != amount
                    or existing.method != method or existing.reason != reason.strip() or existing.collected_by_id != actor.id):
                raise HTTPException(409, "Mã yêu cầu hoàn tiền đã được dùng cho nội dung khác.")
            return existing
        refunded = sum_exact_vnd(db.execute(select(Payment.amount).where(
            Payment.original_payment_id == original.id, Payment.kind == "refund"
        )).scalars())
        if amount > original.amount - refunded:
            raise HTTPException(409, "Số tiền hoàn vượt quá số tiền còn lại trên phiếu thu.")
        when = business_now()
        if when < original.created_at:
            raise HTTPException(409, "Thời điểm hoàn tiền không được trước thời điểm thu.")
        shift = None if method == "demo" else db.execute(select(CashShift).where(
            CashShift.staff_id == actor.id, CashShift.status == "open", CashShift.opened_at <= when,
        ).with_for_update()).scalar_one_or_none()
        refund = Payment(
            source_type=original.source_type, source_id=original.source_id,
            kind="refund", amount=amount, method=method, collected_by_id=actor.id,
            shift_id=shift.id if shift else None, created_at=when,
            idempotency_key=refund_key, original_payment_id=original.id, reason=reason.strip(),
        )
        db.add(refund)
        db.flush()
        return refund

    @staticmethod
    def serialize(db: Session, payment: Payment) -> dict:
        refunded = 0
        if payment.kind == "receipt":
            refunded = sum_exact_vnd(db.execute(select(Payment.amount).where(
                Payment.original_payment_id == payment.id, Payment.kind == "refund"
            )).scalars())
        return {
            "id": payment.id, "source_type": payment.source_type, "source_id": payment.source_id,
            "kind": payment.kind, "amount": payment.amount, "method": payment.method,
            "collected_by_id": payment.collected_by_id, "shift_id": payment.shift_id,
            "created_at": payment.created_at, "original_payment_id": payment.original_payment_id,
            "reason": payment.reason, "refunded_amount": refunded,
            "refundable_amount": payment.amount - refunded if payment.kind == "receipt" else 0,
        }

    @staticmethod
    def _revenue_events(db: Session, start: datetime, end: datetime):
        """Read ledger plus unbackfilled legacy records without double counting.

        The legacy bridge is necessary for existing/imported rows and deliberately
        tests receipt existence across all dates, not just the selected period.
        A source moves entirely to ledger accounting as soon as a receipt exists.
        """
        receipt_exists = exists(select(Payment.id).where(
            Payment.source_type == "parking_session", Payment.source_id == ParkingSession.id, Payment.kind == "receipt"
        ))
        monthly_receipt_exists = exists(select(Payment.id).where(
            Payment.source_type == "monthly_pass", Payment.source_id == cast(MonthlyPass.id, String), Payment.kind == "receipt"
        ))
        # Existing monthly metadata uses UTC-naive timestamps; collection is
        # interpreted in the business timezone consistently with the migration.
        utc_start = start.replace(tzinfo=BUSINESS_TZ).astimezone(timezone.utc).replace(tzinfo=None)
        utc_end = end.replace(tzinfo=BUSINESS_TZ).astimezone(timezone.utc).replace(tzinfo=None)
        # One SELECT gives all branches the same database snapshot, including
        # PostgreSQL READ COMMITTED. Separate SELECTs could miss a source if its
        # receipt commits between reading the ledger and reading legacy rows.
        events = union_all(
            select(Payment.created_at.label("at"), Payment.source_type.label("source"),
                   Payment.kind.label("kind"), Payment.amount.label("amount"), literal(False).label("metadata_utc")).where(
                Payment.created_at >= start, Payment.created_at < end, Payment.method != "demo",
            ),
            select(ParkingSession.check_out_time, literal("parking_session"), literal("receipt"),
                   ParkingSession.parking_fee, literal(False)).where(
                ParkingSession.status == "completed", ParkingSession.check_out_time >= start,
                ParkingSession.check_out_time < end, ParkingSession.parking_fee.is_not(None), ~receipt_exists,
            ),
            select(MonthlyPass.created_at, literal("monthly_pass"), literal("receipt"),
                   MonthlyPass.price, literal(True)).where(
                MonthlyPass.created_at >= utc_start, MonthlyPass.created_at < utc_end, ~monthly_receipt_exists,
            ),
        )
        for row in db.execute(events):
            when = row.at
            if row.metadata_utc:
                when = when.replace(tzinfo=timezone.utc).astimezone(BUSINESS_TZ).replace(tzinfo=None)
            yield when, row.source, row.kind, require_exact_vnd(row.amount)

    @staticmethod
    def revenue_breakdown(db: Session, start: datetime, end: datetime) -> dict[str, int]:
        parking = monthly = refunds = 0
        for _, source, kind, amount in PaymentService._revenue_events(db, start, end):
            if kind == "refund":
                refunds += amount
            elif source == "parking_session":
                parking += amount
            else:
                monthly += amount
        return {
            "parking_revenue": require_exact_vnd(parking, label="Tổng doanh thu"),
            "monthly_pass_revenue": require_exact_vnd(monthly, label="Doanh thu vé tháng"),
            "refunds": require_exact_vnd(refunds, label="Tổng hoàn tiền"),
            "total_revenue": signed_exact_vnd(parking + monthly - refunds, label="Tổng doanh thu"),
        }

    @staticmethod
    def revenue_by_day(db: Session, start: datetime, end: datetime) -> dict[str, int]:
        totals: dict[str, int] = {}
        for when, _, kind, amount in PaymentService._revenue_events(db, start, end):
            day = when.strftime("%Y-%m-%d")
            totals[day] = totals.get(day, 0) + (-amount if kind == "refund" else amount)
        return {day: signed_exact_vnd(total, label="Tổng doanh thu") for day, total in totals.items()}
