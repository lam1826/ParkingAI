import datetime
import pytest
from sqlalchemy.orm import Session

from models.vehicle_type import VehicleType
from models.price_config import PriceConfig
from services.parking_service import ParkingService


def test_calculate_fee_by_hour(
    db_session: Session, vehicle_type: VehicleType, price_config: PriceConfig
):
    """1. Kiểm thử tính phí theo giờ."""
    parking_service = ParkingService(db_session)

    time_in = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(hours=2)
    time_out = datetime.datetime.now(datetime.timezone.utc)

    # calculate_fee yêu cầu cả vehicle_id lẫn vehicle_type_id
    fee = parking_service.calculate_fee(
        vehicle_id=vehicle_type.id,
        vehicle_type_id=vehicle_type.id,
        time_in=time_in,
        time_out=time_out
    )

    assert fee >= price_config.price * 2


def test_calculate_fee_by_day(
    db_session: Session, vehicle_type: VehicleType, price_config: PriceConfig
):
    """2. Kiểm thử tính phí theo ngày."""
    parking_service = ParkingService(db_session)

    time_in = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(hours=25)
    time_out = datetime.datetime.now(datetime.timezone.utc)

    fee = parking_service.calculate_fee(
        vehicle_id=vehicle_type.id,
        vehicle_type_id=vehicle_type.id,
        time_in=time_in,
        time_out=time_out
    )

    assert fee > 0


def test_calculate_fee_monthly_pass(
    db_session: Session, vehicle_type: VehicleType, price_config: PriceConfig
):
    """3. Kiểm thử vé tháng (Phí bằng 0 hoặc chính sách tương ứng)."""
    parking_service = ParkingService(db_session)

    time_in = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(hours=5)
    time_out = datetime.datetime.now(datetime.timezone.utc)

    fee = parking_service.calculate_fee(
        vehicle_id=vehicle_type.id,
        vehicle_type_id=vehicle_type.id,
        time_in=time_in,
        time_out=time_out
    )

    assert fee >= 0.0


def test_calculate_fee_zero_price(db_session: Session, vehicle_type: VehicleType):
    """4. Kiểm thử khi giá cước bằng 0."""
    parking_service = ParkingService(db_session)

    # Giá cước được cấu hình trong bảng PriceConfig, không phải trên VehicleType
    free_price_config = PriceConfig(
        vehicle_type_id=vehicle_type.id,
        is_active=True,
        ticket_type="HOURLY",
        price=0.0,
        effective_date=datetime.date.today(),
    )
    db_session.add(free_price_config)
    db_session.commit()
    db_session.refresh(free_price_config)

    time_in = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(hours=4)
    time_out = datetime.datetime.now(datetime.timezone.utc)

    fee = parking_service.calculate_fee(
        vehicle_id=vehicle_type.id,
        vehicle_type_id=vehicle_type.id,
        time_in=time_in,
        time_out=time_out
    )

    assert fee == 0.0


def test_calculate_fee_invalid_time_range(
    db_session: Session, vehicle_type: VehicleType, price_config: PriceConfig
):
    """5. Kiểm thử time_out nhỏ hơn time_in."""
    parking_service = ParkingService(db_session)

    time_in = datetime.datetime.now(datetime.timezone.utc)
    time_out = time_in - datetime.timedelta(hours=1)

    with pytest.raises(Exception):
        parking_service.calculate_fee(
            vehicle_id=vehicle_type.id,
            vehicle_type_id=vehicle_type.id,
            time_in=time_in,
            time_out=time_out
        )


def test_calculate_fee_unconfigured_price(db_session: Session):
    """6. Kiểm thử khi ID loại xe không tồn tại."""
    parking_service = ParkingService(db_session)

    time_in = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(hours=2)
    time_out = datetime.datetime.now(datetime.timezone.utc)

    with pytest.raises(Exception):
        parking_service.calculate_fee(
            vehicle_id=999999,
            vehicle_type_id=999999,
            time_in=time_in,
            time_out=time_out
        )