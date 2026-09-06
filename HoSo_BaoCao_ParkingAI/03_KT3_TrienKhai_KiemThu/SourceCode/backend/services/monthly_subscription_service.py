"""Create paid periods atomically; renewal never rewrites historical entitlement."""
import uuid

from fastapi import HTTPException
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError

from crud.monthly_pass import get_overlapping_active_pass_by_vehicle
from models.customer import Customer
from models.monthly_pass import MonthlyPass
from models.parking_card import ParkingCard
from models.vehicle import Vehicle


def _lock_vehicle(db, vehicle_id):
    # All periods for a vehicle share a transaction lock, including renewals.
    if db.bind.dialect.name == "sqlite":
        db.execute(update(Vehicle).where(Vehicle.id == vehicle_id).values(id=Vehicle.id))
    vehicle = db.scalar(select(Vehicle).where(Vehicle.id == vehicle_id).with_for_update())
    if vehicle is None:
        raise HTTPException(404, "Không tìm thấy phương tiện.")


def has_receipt(db, pass_id):
    from models.payment import Payment
    return db.query(Payment.id).filter(
        Payment.source_type == "monthly_pass", Payment.source_id == str(pass_id),
        Payment.kind == "receipt",
    ).first() is not None


def _collect(db, period, staff_id, method):
    from services.payment_service import PaymentService
    db.flush()
    PaymentService.record_receipt(
        db, source_type="monthly_pass", source_id=str(period.id),
        amount=period.price, collected_by_id=staff_id, method=method,
    )
    db.commit()
    db.refresh(period)
    return period


def create_subscription(db, data, staff_id):
    try:
        _lock_vehicle(db, data.vehicle_id)
        if data.is_active and get_overlapping_active_pass_by_vehicle(db, data.vehicle_id, data.start_date, data.end_date):
            raise HTTPException(409, "Khoảng hiệu lực chồng lấn với kỳ vé đang hoạt động.")
        if db.get(Customer, data.customer_id) is None:
            raise HTTPException(404, "Không tìm thấy khách hàng.")
        if db.scalar(select(ParkingCard.id).where(ParkingCard.code == data.pass_code)) is not None:
            raise HTTPException(409, "Mã thẻ đã tồn tại. Hãy gia hạn từ kỳ vé hiện có.")
        card = ParkingCard(code=data.pass_code, customer_id=data.customer_id, vehicle_id=data.vehicle_id)
        db.add(card)
        db.flush()
        period = MonthlyPass(**data.model_dump(exclude={"payment_method"}), card_id=card.id)
        db.add(period)
        return _collect(db, period, staff_id, data.payment_method)
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(409, "Mã thẻ hoặc khoảng hiệu lực đã được sử dụng.") from exc
    except Exception:
        db.rollback()
        raise


def renew_subscription(db, original_id, data, staff_id):
    try:
        original = db.get(MonthlyPass, original_id)
        if original is None:
            raise HTTPException(404, "Không tìm thấy vé tháng.")
        _lock_vehicle(db, original.vehicle_id)
        db.refresh(original)
        if not original.pass_code and not original.card_id:
            raise HTTPException(409, "Vé cũ chưa có mã thẻ. Cần cấp mã thẻ trước khi gia hạn.")
        if original.card_id is None:
            card = db.scalar(select(ParkingCard).where(ParkingCard.code == original.pass_code))
            if card is None:
                card = ParkingCard(code=original.pass_code, customer_id=original.customer_id,
                                   vehicle_id=original.vehicle_id)
                db.add(card)
                db.flush()
            if (card.customer_id, card.vehicle_id) != (original.customer_id, original.vehicle_id):
                raise HTTPException(409, "Thông tin chủ thẻ không khớp với kỳ vé.")
            original.card_id = card.id
            db.flush()
        existing = db.scalar(select(MonthlyPass).where(MonthlyPass.renewal_key == data.request_id))
        if existing is not None:
            from models.payment import Payment
            receipt = db.scalar(select(Payment).where(Payment.source_type == "monthly_pass",
                Payment.source_id == str(existing.id), Payment.kind == "receipt"))
            if (existing.card_id, existing.start_date, existing.end_date, existing.price) != (
                original.card_id, data.start_date, data.end_date, data.price
            ) or receipt is None or receipt.method != data.payment_method or receipt.collected_by_id != staff_id:
                raise HTTPException(409, "Mã yêu cầu đã được dùng cho giao dịch khác.")
            db.commit()
            return existing
        if data.start_date <= original.end_date:
            raise HTTPException(409, "Kỳ gia hạn phải bắt đầu sau ngày hết hạn của kỳ đã chọn.")
        overlap = get_overlapping_active_pass_by_vehicle(db, original.vehicle_id, data.start_date, data.end_date)
        if overlap:
            raise HTTPException(409, "Khoảng gia hạn chồng lấn với một kỳ vé đang hoạt động.")
        period = MonthlyPass(customer_id=original.customer_id, vehicle_id=original.vehicle_id,
            card_id=original.card_id, pass_code="KY-" + uuid.uuid4().hex.upper(),
            renewal_key=data.request_id, price=data.price, start_date=data.start_date,
            end_date=data.end_date, is_active=True)
        db.add(period)
        return _collect(db, period, staff_id, data.payment_method)
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(409, "Kỳ gia hạn hoặc mã yêu cầu bị trùng; hãy tải lại dữ liệu.") from exc
    except Exception:
        db.rollback()
        raise
