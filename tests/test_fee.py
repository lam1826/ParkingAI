import datetime
import pytest
from sqlalchemy.orm import Session

from models.vehicle_type import VehicleType
from models.price_config import PriceConfig
from models.customer import Customer
from models.vehicle import Vehicle
from models.monthly_pass import MonthlyPass
from services.parking_service import ParkingService

# Đợt 10A — mọi test dưới đây dẫn xuất thời gian từ ĐÚNG MỘT reference
# instant naive business-local (`business_reference_now`), không gọi
# `datetime.now()` rời rạc và không trộn aware-UTC với host-local.
# `price_config` fixture (conftest.py) cũng dẫn xuất `effective_date` từ
# cùng reference đó.
#
# KHÓA CỨNG mốc thời gian cho TOÀN BỘ file này bằng cách override fixture
# CÙNG TÊN `business_reference_now` của conftest.py. Mốc được chọn là
# 00:30 giờ Việt Nam — nằm giữa khung 00:00–06:59 từng làm cả suite FAIL.
#
# Lịch sử bug (đã sửa): conftest/test_fee dựng time_in/time_out bằng
# `datetime.now(timezone.utc)` (AWARE UTC) còn `price_config.effective_date`
# dùng `date.today()` (ngày HOST-LOCAL). Trong khung giờ VN 00:00–06:59,
# ngày UTC vẫn là hôm trước, nên `time_out.date()` tính theo UTC lệch 1 ngày
# so với effective_date theo giờ VN -> điều kiện
# `effective_date <= time_out.date()` không khớp -> 404 "Chưa cấu hình bảng
# giá" -> 9 test FAIL nguyên khối mỗi ngày trong đúng khung giờ đó.
#
# Nhờ ghim cứng, cả file chạy vĩnh viễn trong khung giờ nguy hiểm cũ: nếu ai
# đó lỡ đưa `datetime.now()`/`date.today()` rời rạc trở lại vào fixture hay
# đường tính phí, test sẽ FAIL xác định — không cần đợi tới đúng khung giờ
# thực tế mới phát hiện.

VN_EARLY_MORNING_REFERENCE = datetime.datetime(2026, 3, 10, 0, 30, 0)


@pytest.fixture()
def business_reference_now() -> datetime.datetime:
    """Override fixture cùng tên trong conftest.py: ghim toàn bộ test_fee.py
    (và fixture `price_config` mà chúng dùng) vào đúng 00:30 giờ VN."""
    return VN_EARLY_MORNING_REFERENCE


def test_calculate_fee_by_hour(
    db_session: Session,
    vehicle_type: VehicleType,
    price_config: PriceConfig,
    business_reference_now: datetime.datetime,
):
    """1. Kiểm thử tính phí theo giờ."""
    parking_service = ParkingService(db_session)

    time_out = business_reference_now
    time_in = time_out - datetime.timedelta(hours=2)

    # calculate_fee yêu cầu cả vehicle_id lẫn vehicle_type_id
    fee = parking_service.calculate_fee(
        vehicle_id=vehicle_type.id,
        vehicle_type_id=vehicle_type.id,
        time_in=time_in,
        time_out=time_out
    )

    assert fee >= price_config.price * 2


def test_calculate_fee_by_day(
    db_session: Session,
    vehicle_type: VehicleType,
    business_reference_now: datetime.datetime,
):
    """2. Kiểm thử tính phí theo ngày (nhánh ticket_type = DAILY)."""
    parking_service = ParkingService(db_session)

    time_out = business_reference_now
    time_in = time_out - datetime.timedelta(hours=25)

    daily_config = PriceConfig(
        vehicle_type_id=vehicle_type.id,
        is_active=True,
        ticket_type="DAILY",
        price=120000.0,
        # Phải có hiệu lực trước cả time_in (lùi 25 giờ) -> lùi 2 ngày.
        effective_date=(business_reference_now - datetime.timedelta(days=2)).date(),
    )
    db_session.add(daily_config)
    db_session.commit()

    fee = parking_service.calculate_fee(
        vehicle_id=vehicle_type.id,
        vehicle_type_id=vehicle_type.id,
        time_in=time_in,
        time_out=time_out
    )

    # 25 giờ -> làm tròn lên 2 ngày
    assert fee == 120000.0 * 2


def test_calculate_fee_monthly_pass(
    db_session: Session,
    vehicle_type: VehicleType,
    price_config: PriceConfig,
    customer: Customer,
    business_reference_now: datetime.datetime,
):
    """3. Kiểm thử vé tháng còn hiệu lực -> phí bằng 0."""
    parking_service = ParkingService(db_session)

    vehicle = Vehicle(
        license_plate="30M-777.77",
        vehicle_type_id=vehicle_type.id,
        customer_id=customer.id,
    )
    db_session.add(vehicle)
    db_session.commit()
    db_session.refresh(vehicle)

    reference_day = business_reference_now.date()
    monthly_pass = MonthlyPass(
        customer_id=customer.id,
        vehicle_id=vehicle.id,
        start_date=reference_day - datetime.timedelta(days=5),
        end_date=reference_day + datetime.timedelta(days=25),
        is_active=True,
    )
    db_session.add(monthly_pass)
    db_session.commit()

    time_out = business_reference_now
    time_in = time_out - datetime.timedelta(hours=5)

    fee = parking_service.calculate_fee(
        vehicle_id=vehicle.id,
        vehicle_type_id=vehicle_type.id,
        time_in=time_in,
        time_out=time_out
    )

    assert fee == 0.0


def test_calculate_fee_zero_price(
    db_session: Session,
    vehicle_type: VehicleType,
    business_reference_now: datetime.datetime,
):
    """4. Kiểm thử khi giá cước bằng 0."""
    parking_service = ParkingService(db_session)

    # Giá cước được cấu hình trong bảng PriceConfig, không phải trên VehicleType
    free_price_config = PriceConfig(
        vehicle_type_id=vehicle_type.id,
        is_active=True,
        ticket_type="HOURLY",
        price=0.0,
        effective_date=(business_reference_now - datetime.timedelta(days=1)).date(),
    )
    db_session.add(free_price_config)
    db_session.commit()
    db_session.refresh(free_price_config)

    time_out = business_reference_now
    time_in = time_out - datetime.timedelta(hours=4)

    fee = parking_service.calculate_fee(
        vehicle_id=vehicle_type.id,
        vehicle_type_id=vehicle_type.id,
        time_in=time_in,
        time_out=time_out
    )

    assert fee == 0.0


def test_calculate_fee_invalid_time_range(
    db_session: Session,
    vehicle_type: VehicleType,
    price_config: PriceConfig,
    business_reference_now: datetime.datetime,
):
    """5. Kiểm thử time_out nhỏ hơn time_in."""
    parking_service = ParkingService(db_session)

    time_in = business_reference_now
    time_out = time_in - datetime.timedelta(hours=1)

    with pytest.raises(Exception):
        parking_service.calculate_fee(
            vehicle_id=vehicle_type.id,
            vehicle_type_id=vehicle_type.id,
            time_in=time_in,
            time_out=time_out
        )


def test_calculate_fee_boundary_exact_hour(
    db_session: Session,
    vehicle_type: VehicleType,
    price_config: PriceConfig,
    business_reference_now: datetime.datetime,
):
    """7. Kiểm thử đúng mốc ranh giới: chính xác 1 giờ -> tính 1 giờ."""
    parking_service = ParkingService(db_session)

    time_out = business_reference_now
    time_in = time_out - datetime.timedelta(seconds=3600)

    fee = parking_service.calculate_fee(
        vehicle_id=vehicle_type.id,
        vehicle_type_id=vehicle_type.id,
        time_in=time_in,
        time_out=time_out
    )

    assert fee == price_config.price * 1


def test_calculate_fee_boundary_just_under_hour(
    db_session: Session,
    vehicle_type: VehicleType,
    price_config: PriceConfig,
    business_reference_now: datetime.datetime,
):
    """8. Kiểm thử dưới mốc: 59 phút 59 giây -> vẫn làm tròn lên 1 giờ."""
    parking_service = ParkingService(db_session)

    time_out = business_reference_now
    time_in = time_out - datetime.timedelta(seconds=3599)

    fee = parking_service.calculate_fee(
        vehicle_id=vehicle_type.id,
        vehicle_type_id=vehicle_type.id,
        time_in=time_in,
        time_out=time_out
    )

    assert fee == price_config.price * 1


def test_calculate_fee_boundary_just_over_hour(
    db_session: Session,
    vehicle_type: VehicleType,
    price_config: PriceConfig,
    business_reference_now: datetime.datetime,
):
    """9. Kiểm thử vượt mốc: 1 giờ 1 giây -> làm tròn lên 2 giờ."""
    parking_service = ParkingService(db_session)

    time_out = business_reference_now
    time_in = time_out - datetime.timedelta(seconds=3601)

    fee = parking_service.calculate_fee(
        vehicle_id=vehicle_type.id,
        vehicle_type_id=vehicle_type.id,
        time_in=time_in,
        time_out=time_out
    )

    assert fee == price_config.price * 2


def test_calculate_fee_zero_duration(
    db_session: Session,
    vehicle_type: VehicleType,
    price_config: PriceConfig,
    business_reference_now: datetime.datetime,
):
    """10. Kiểm thử thời gian gửi bằng 0 (vào ra tức thì) -> phí 0."""
    parking_service = ParkingService(db_session)

    time_in = business_reference_now

    fee = parking_service.calculate_fee(
        vehicle_id=vehicle_type.id,
        vehicle_type_id=vehicle_type.id,
        time_in=time_in,
        time_out=time_in
    )

    assert fee == 0.0


def test_calculate_fee_unconfigured_price(
    db_session: Session, business_reference_now: datetime.datetime,
):
    """6. Kiểm thử khi ID loại xe không tồn tại."""
    parking_service = ParkingService(db_session)

    time_out = business_reference_now
    time_in = time_out - datetime.timedelta(hours=2)

    with pytest.raises(Exception):
        parking_service.calculate_fee(
            vehicle_id=999999,
            vehicle_type_id=999999,
            time_in=time_in,
            time_out=time_out
        )


# ===========================================================================
# Đợt 10A — regression tường minh cho khung 00:00–06:59 giờ Việt Nam
# ===========================================================================
#
# Toàn bộ file này đã chạy tại mốc 00:30 giờ VN (xem fixture override ở
# đầu file), nên MỌI test phía trên đều là bằng chứng suite không còn phụ
# thuộc thời điểm chạy. Hai test dưới đây khẳng định tường minh hai kịch bản
# nhạy cảm nhất, dùng chung đúng fixture `price_config`/`business_reference_now`
# như các test khác — không tạo mốc hay PriceConfig riêng.


def test_fee_across_vietnam_midnight_at_pinned_reference(
    db_session: Session,
    vehicle_type: VehicleType,
    price_config: PriceConfig,
    business_reference_now: datetime.datetime,
):
    """Phí tính đúng cho phiên VẮT QUA nửa đêm giờ VN, với reference ghim tại
    00:30 — khung giờ từng làm cả suite FAIL."""
    reference = business_reference_now
    assert reference.hour == 0 and reference.minute == 30, (
        "Reference phải nằm trong khung 00:00–06:59 giờ VN để test có ý nghĩa"
    )

    # Gửi xe 2 giờ: 22:30 hôm trước -> 00:30 hôm nay (giờ VN)
    time_out = reference
    time_in = time_out - datetime.timedelta(hours=2)
    assert time_in.date() != time_out.date(), (
        "Khoảng thời gian phải vắt qua nửa đêm giờ VN để test đúng kịch bản bug"
    )

    fee = ParkingService(db_session).calculate_fee(
        vehicle_id=vehicle_type.id,
        vehicle_type_id=vehicle_type.id,
        time_in=time_in,
        time_out=time_out,
    )

    assert fee == price_config.price * 2, (
        f"Phí phải đúng 2 giờ x {price_config.price} kể cả khi check-out lúc "
        f"00:30 giờ VN và check-in từ ngày hôm trước; thực tế={fee}"
    )


def test_monthly_pass_starting_on_reference_day_is_active_at_pinned_reference(
    db_session: Session,
    vehicle_type: VehicleType,
    price_config: PriceConfig,
    customer: Customer,
    business_reference_now: datetime.datetime,
):
    """Vé tháng bắt đầu ĐÚNG ngày VN của reference (00:30) phải có hiệu lực
    -> phí 0. Đặt `start_date` đúng bằng ngày VN khiến ngày UTC (vẫn là hôm
    trước tại thời điểm này) sẽ KHÔNG khớp `start_date <= ngày <= end_date`,
    nên test chỉ pass khi lookup dùng đúng ngày Việt Nam."""
    reference = business_reference_now
    reference_day = reference.date()

    vehicle = Vehicle(
        license_plate="30M-000.30",
        vehicle_type_id=vehicle_type.id,
        customer_id=customer.id,
    )
    db_session.add(vehicle)
    db_session.commit()
    db_session.refresh(vehicle)

    db_session.add(MonthlyPass(
        customer_id=customer.id,
        vehicle_id=vehicle.id,
        start_date=reference_day,
        end_date=reference_day + datetime.timedelta(days=30),
        is_active=True,
    ))
    db_session.commit()

    fee = ParkingService(db_session).calculate_fee(
        vehicle_id=vehicle.id,
        vehicle_type_id=vehicle_type.id,
        time_in=reference - datetime.timedelta(hours=2),
        time_out=reference,
    )

    assert fee == 0.0, (
        f"Vé tháng bắt đầu đúng ngày VN {reference_day} phải có hiệu lực lúc "
        f"00:30 cùng ngày -> phí 0; thực tế={fee}"
    )
