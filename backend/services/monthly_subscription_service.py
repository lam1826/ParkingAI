"""Create paid periods atomically; renewal never rewrites historical entitlement."""
import uuid

from fastapi import HTTPException
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError

from core.clock import business_today
from crud.monthly_pass import get_overlapping_active_pass_by_vehicle
from models.customer import Customer
from models.monthly_pass import MonthlyPass
from models.parking_card import ParkingCard
from models.vehicle import Vehicle
from services.payment_service import lock_cash_operator


def _lock_vehicle(db, vehicle_id):
    # All periods for a vehicle share a transaction lock, including renewals.
    if db.bind.dialect.name == "sqlite":
        db.execute(update(Vehicle).where(Vehicle.id == vehicle_id).values(id=Vehicle.id))
    vehicle = db.scalar(select(Vehicle).where(Vehicle.id == vehicle_id).with_for_update())
    if vehicle is None:
        raise HTTPException(404, "Không tìm thấy phương tiện.")
    return vehicle


def has_receipt(db, pass_id):
    from models.payment import Payment
    return db.query(Payment.id).filter(
        Payment.source_type == "monthly_pass", Payment.source_id == str(pass_id),
        Payment.kind == "receipt",
    ).first() is not None


def counter_site(db, staff_id, requested_site_id=None):
    """Site whose finance owns a counter-sold period's receipt.

    Portal periods keep the site of their frozen order. A counter sale or
    renewal has no order, so its receipt is attributed to the site chosen by
    the seller (validated), else the seller's open site-bound shift, else the
    only site of a single-site installation. A multi-site installation never
    records a new site-less receipt that no site finance screen, shift or
    refund queue can reach.
    """
    from expansion.site_models import ParkingSite
    from expansion.site_scope import require_site_access
    from models.cash_shift import CashShift
    from models.user import User
    if requested_site_id is not None:
        actor = db.get(User, staff_id) if staff_id is not None else None
        if actor is None:
            raise HTTPException(403, "Cần nhân viên thu tiền để ghi nhận khoản thu tại bãi.")
        require_site_access(db, actor, requested_site_id, "manager")
        return requested_site_id
    if staff_id is not None:
        shift_site = db.scalar(select(CashShift.site_id).where(
            CashShift.staff_id == staff_id, CashShift.status == "open"))
        if shift_site is not None:
            return shift_site
    sites = list(db.scalars(select(ParkingSite.id).where(ParkingSite.is_active.is_(True)).order_by(ParkingSite.id).limit(2)))
    if not sites:
        return None  # Legacy installation without an active site: no site finance exists.
    if len(sites) == 1:
        return sites[0]
    raise HTTPException(409, "Hệ thống có nhiều bãi: hãy mở ca thu tiền tại bãi bán vé hoặc chọn bãi trước khi bán hoặc gia hạn vé tháng.")


def was_refunded(db, pass_id):
    """True when money of this period was returned (ledger refund or refunded portal order)."""
    from expansion.portal_models import PortalOrder
    from models.payment import Payment
    refunded = db.query(Payment.id).filter(
        Payment.source_type == "monthly_pass", Payment.source_id == str(pass_id), Payment.kind == "refund",
    ).first() is not None
    return refunded or db.scalar(select(PortalOrder.id).where(
        PortalOrder.monthly_pass_id == pass_id, PortalOrder.status == "refunded")) is not None


def _collect(db, period, staff_id, method, site_id=None):
    from services.payment_service import PaymentService
    db.flush()
    PaymentService.record_receipt(
        db, source_type="monthly_pass", source_id=str(period.id),
        amount=period.price, collected_by_id=staff_id, method=method,
        counter_site_id=site_id,
    )
    db.commit()
    db.refresh(period)
    return period


def create_subscription(db, data, staff_id):
    try:
        # Match reservation arrival and camera exit: operator before vehicle.
        # record_receipt reuses this lock when it collects the paid period.
        if staff_id is not None:
            lock_cash_operator(db, staff_id)
        vehicle = _lock_vehicle(db, data.vehicle_id)
        if data.is_active and get_overlapping_active_pass_by_vehicle(db, data.vehicle_id, data.start_date, data.end_date):
            raise HTTPException(409, "Khoảng hiệu lực chồng lấn với kỳ vé đang hoạt động.")
        if db.get(Customer, data.customer_id) is None:
            raise HTTPException(404, "Không tìm thấy khách hàng.")
        # The pass owner must be the vehicle owner (portal fulfilment enforces
        # the same). A walk-in vehicle without an owner stays allowed.
        if vehicle.customer_id is not None and vehicle.customer_id != data.customer_id:
            raise HTTPException(409, "Xe đã thuộc khách hàng khác. Hãy chọn đúng chủ xe cho vé tháng.")
        if db.scalar(select(ParkingCard.id).where(ParkingCard.code == data.pass_code)) is not None:
            raise HTTPException(409, "Mã thẻ đã tồn tại. Hãy gia hạn từ kỳ vé hiện có.")
        site_id = counter_site(db, staff_id, data.site_id)
        card = ParkingCard(code=data.pass_code, customer_id=data.customer_id, vehicle_id=data.vehicle_id)
        db.add(card)
        db.flush()
        period = MonthlyPass(**data.model_dump(exclude={"payment_method", "site_id"}), card_id=card.id)
        db.add(period)
        return _collect(db, period, staff_id, data.payment_method, site_id)
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
        if staff_id is not None:
            lock_cash_operator(db, staff_id)
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
        # Portal periods carry site scope in their originating order. A legacy
        # renewal creates no order, so it would silently become a global pass.
        # Already collected retries above keep their original receipt; new
        # portal renewals must use the order flow that preserves the site.
        from expansion.portal_models import PortalOrder
        if db.scalar(select(PortalOrder.id).where(PortalOrder.monthly_pass_id == original.id)) is not None:
            raise HTTPException(
                409,
                "Vé thuộc gói theo bãi. Hãy gia hạn qua cổng khách hàng để giữ đúng bãi và điều kiện gói vé.",
            )
        if data.start_date <= original.end_date:
            raise HTTPException(409, "Kỳ gia hạn phải bắt đầu sau ngày hết hạn của kỳ đã chọn.")
        # Coverage is fixed at admission: a period that already ended cannot
        # cover any future stay, so collecting for it only takes money.
        if data.end_date < business_today():
            raise HTTPException(409, "Kỳ gia hạn đã kết thúc trước hôm nay. Hãy chọn kỳ bắt đầu từ hôm nay trở đi.")
        overlap = get_overlapping_active_pass_by_vehicle(db, original.vehicle_id, data.start_date, data.end_date)
        if overlap:
            raise HTTPException(409, "Khoảng gia hạn chồng lấn với một kỳ vé đang hoạt động.")
        site_id = counter_site(db, staff_id, data.site_id)
        period = MonthlyPass(customer_id=original.customer_id, vehicle_id=original.vehicle_id,
            card_id=original.card_id, pass_code="KY-" + uuid.uuid4().hex.upper(),
            renewal_key=data.request_id, price=data.price, start_date=data.start_date,
            end_date=data.end_date, is_active=True)
        db.add(period)
        return _collect(db, period, staff_id, data.payment_method, site_id)
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(409, "Kỳ gia hạn hoặc mã yêu cầu bị trùng; hãy tải lại dữ liệu.") from exc
    except Exception:
        db.rollback()
        raise
