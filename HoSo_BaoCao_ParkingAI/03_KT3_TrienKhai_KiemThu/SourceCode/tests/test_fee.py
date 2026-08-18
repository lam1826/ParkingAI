import datetime
import pytest
from sqlalchemy.orm import Session

from models.vehicle_type import VehicleType
from models.price_config import PriceConfig
from models.customer import Customer
from models.vehicle import Vehicle
from models.monthly_pass import MonthlyPass
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
    db_session: Session, vehicle_type: VehicleType
):
    """2. Kiểm thử tính phí theo ngày (nhánh ticket_type = DAILY)."""
    parking_service = ParkingService(db_session)

    daily_config = PriceConfig(
        vehicle_type_id=vehicle_type.id,
        is_active=True,
        ticket_type="DAILY",
        price=120000.0,
        effective_date=datetime.date.today(),
    )
    db_session.add(daily_config)
    db_session.commit()

    time_in = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(hours=25)
    time_out = datetime.datetime.now(datetime.timezone.utc)

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

    monthly_pass = MonthlyPass(
        customer_id=customer.id,
        vehicle_id=vehicle.id,
        start_date=datetime.date.today() - datetime.timedelta(days=5),
        end_date=datetime.date.today() + datetime.timedelta(days=25),
        is_active=True,
    )
    db_session.add(monthly_pass)
    db_session.commit()

    time_in = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(hours=5)
    time_out = datetime.datetime.now(datetime.timezone.utc)

    fee = parking_service.calculate_fee(
        vehicle_id=vehicle.id,
        vehicle_type_id=vehicle_type.id,
        time_in=time_in,
        time_out=time_out
    )

    assert fee == 0.0


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


def test_calculate_fee_boundary_exact_hour(
    db_session: Session, vehicle_type: VehicleType, price_config: PriceConfig
):
    """7. Kiểm thử đúng mốc ranh giới: chính xác 1 giờ -> tính 1 giờ."""
    parking_service = ParkingService(db_session)

    time_out = datetime.datetime.now(datetime.timezone.utc)
    time_in = time_out - datetime.timedelta(seconds=3600)

    fee = parking_service.calculate_fee(
        vehicle_id=vehicle_type.id,
        vehicle_type_id=vehicle_type.id,
        time_in=time_in,
        time_out=time_out
    )

    assert fee == price_config.price * 1


def test_calculate_fee_boundary_just_under_hour(
    db_session: Session, vehicle_type: VehicleType, price_config: PriceConfig
):
    """8. Kiểm thử dưới mốc: 59 phút 59 giây -> vẫn làm tròn lên 1 giờ."""
    parking_service = ParkingService(db_session)

    time_out = datetime.datetime.now(datetime.timezone.utc)
    time_in = time_out - datetime.timedelta(seconds=3599)

    fee = parking_service.calculate_fee(
        vehicle_id=vehicle_type.id,
        vehicle_type_id=vehicle_type.id,
        time_in=time_in,
        time_out=time_out
    )

    assert fee == price_config.price * 1


def test_calculate_fee_boundary_just_over_hour(
    db_session: Session, vehicle_type: VehicleType, price_config: PriceConfig
):
    """9. Kiểm thử vượt mốc: 1 giờ 1 giây -> làm tròn lên 2 giờ."""
    parking_service = ParkingService(db_session)

    time_out = datetime.datetime.now(datetime.timezone.utc)
    time_in = time_out - datetime.timedelta(seconds=3601)

    fee = parking_service.calculate_fee(
        vehicle_id=vehicle_type.id,
        vehicle_type_id=vehicle_type.id,
        time_in=time_in,
        time_out=time_out
    )

    assert fee == price_config.price * 2


def test_calculate_fee_zero_duration(
    db_session: Session, vehicle_type: VehicleType, price_config: PriceConfig
):
    """10. Kiểm thử thời gian gửi bằng 0 (vào ra tức thì) -> phí 0."""
    parking_service = ParkingService(db_session)

    time_in = datetime.datetime.now(datetime.timezone.utc)

    fee = parking_service.calculate_fee(
        vehicle_id=vehicle_type.id,
        vehicle_type_id=vehicle_type.id,
        time_in=time_in,
        time_out=time_in
    )

    assert fee == 0.0


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