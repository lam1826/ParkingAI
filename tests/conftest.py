import os

# BẮT BUỘC đứng TRƯỚC mọi import backend (main/database):
# database.py tạo engine ở module level từ DATABASE_URL. Dù main.py không còn
# tự migration khi import, test vẫn ép URL sang in-memory để mọi code mở session
# sau này tuyệt đối không thể chạm backend/database/parking.db THẬT. Dùng gán
# trực tiếp (không setdefault) để cả shell ngoài đặt nhầm URL thật cũng bị ghi đè.
os.environ["DATABASE_URL"] = "sqlite:///:memory:"

os.environ.setdefault("SECRET_KEY", "test_secret_key_for_pytest_123456789")
# Ghi đè trực tiếp giống DATABASE_URL: shell bên ngoài không được phép đưa
# API key thật vào pytest. Các AI test dùng mock client và chỉ bật cờ bằng
# test key giả này để kiểm tra contract sau lớp kill switch.
os.environ["GEMINI_API_KEY"] = "test_gemini_api_key_for_pytest_123456789"
os.environ["AI_ENABLED"] = "true"
os.environ.setdefault("MANAGER_REGISTRATION_CODE", "manager-test-code")
os.environ.setdefault("ADMIN_REGISTRATION_CODE", "admin-test-code")

import sys
from pathlib import Path

backend_path = Path(__file__).resolve().parent.parent / "backend"
if str(backend_path) not in sys.path:
    sys.path.insert(0, str(backend_path))

import bcrypt
import datetime
from typing import Generator
from unittest.mock import MagicMock
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool
from sqlalchemy.orm import sessionmaker, Session

from main import app
from database import Base, get_db

from models.user import User
from models.role import Role
from models.vehicle_type import VehicleType
from models.zone import Zone
from models.parking_slot import ParkingSlot
from models.vehicle import Vehicle
from models.customer import Customer
from models.parking_session import ParkingSession
from models.price_config import PriceConfig

SQLALCHEMY_DATABASE_URL = "sqlite:///:memory:"

# ===========================================================================
# Đợt 10A — Reference instant dùng chung cho fixture/test phụ thuộc thời gian
# ===========================================================================
#
# Trước đây conftest/test_fee dựng thời gian bằng
# `datetime.now(datetime.timezone.utc)` (AWARE UTC) trong khi `price_config`
# và `monthly_pass` dùng `date.today()` (ngày HOST-LOCAL). Hai hệ quy chiếu
# trộn lẫn khiến suite FAIL nguyên khối trong khung giờ VN 00:00–06:59 —
# lúc đó ngày UTC vẫn còn là hôm trước, nên `time_out.date()` (UTC) lớn hơn
# `effective_date` (VN) một ngày và query bảng giá không khớp -> 404.
#
# Cách sửa: MỘT reference instant NAIVE BUSINESS-LOCAL duy nhất cho mỗi
# test/fixture (`business_reference_now`), và mọi giá trị dẫn xuất
# (`effective_date`, `start_date`/`end_date`, `time_in`/`time_out`,
# `check_in_time`) đều tính từ chính reference đó — không gọi đồng hồ nhiều
# lần, không trộn aware-UTC với host-local.
#
# `business_reference_now` mặc định lấy `business_now()` (giờ VN thật, độc
# lập timezone host). Test nào cần cố định thời điểm chỉ cần override
# fixture này — xem `test_fee.py::test_fee_suite_is_independent_of_vietnam_
# early_morning_window`, cố định 00:30 giờ VN để chứng minh suite không còn
# phụ thuộc khung 00:00–06:59.

from core.clock import business_now


@pytest.fixture(scope="function", autouse=True)
def forbid_live_ai_provider(monkeypatch):
    """Fail closed if any pytest path forgets to replace Gemini explicitly.

    A fake API key is insufficient protection: constructing the real SDK
    client can still make a future valid request reach the network.  This
    process-wide provider seam therefore raises before client construction.
    Tests that intentionally exercise AI must use ``mock_ai_provider_client``
    or an explicit ``patch('services.ai_service.genai.Client')``.
    """

    def blocked_provider_client(*args, **kwargs):
        raise AssertionError(
            "Live AI provider access is forbidden during pytest; "
            "use mock_ai_provider_client or patch services.ai_service.genai.Client"
        )

    monkeypatch.setattr("services.ai_service.genai.Client", blocked_provider_client)


@pytest.fixture(scope="function")
def mock_ai_provider_client(forbid_live_ai_provider, monkeypatch) -> MagicMock:
    """Explicit opt-in to a controlled provider mock; never permits network."""
    provider_factory = MagicMock(name="mock_ai_provider_client")
    monkeypatch.setattr("services.ai_service.genai.Client", provider_factory)
    return provider_factory


@pytest.fixture(scope="function")
def business_reference_now() -> datetime.datetime:
    """Một mốc thời gian NAIVE business-local (Asia/Ho_Chi_Minh) dùng chung
    cho toàn bộ fixture/test trong một test case. Override fixture này để
    ghim test vào một thời điểm cụ thể."""
    return business_now()

engine = create_engine(
    SQLALCHEMY_DATABASE_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


@pytest.fixture(scope="function")
def db_session() -> Generator[Session, None, None]:
    Base.metadata.create_all(bind=engine)
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()
        Base.metadata.drop_all(bind=engine)


@pytest.fixture(scope="function")
def client(db_session: Session) -> Generator[TestClient, None, None]:
    def override_get_db():
        try:
            yield db_session
        finally:
            pass

    app.dependency_overrides[get_db] = override_get_db

    with TestClient(app) as c:
        yield c

    app.dependency_overrides.clear()


@pytest.fixture(scope="function")
def role(db_session: Session) -> Role:
    r = Role(name="staff")
    db_session.add(r)
    db_session.commit()
    db_session.refresh(r)
    return r


@pytest.fixture(scope="function")
def test_user(db_session: Session, role: Role) -> User:
    # Hash trực tiếp bằng bcrypt (tương đương AuthService.get_password_hash).
    hashed_password = bcrypt.hashpw(
        "password123".encode("utf-8"), bcrypt.gensalt()
    ).decode("utf-8")
    user = User(
        username="qa_staff",
        role_id=role.id,
        password_hash=hashed_password,
        full_name="Nhân viên QA",
        is_active=True,
    )

    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


@pytest.fixture(scope="function")
def vehicle_type(db_session: Session) -> VehicleType:
    v_type = VehicleType(
        name="Ô tô 4 chỗ",
        description="Xe du lịch dưới 9 chỗ"
    )
    db_session.add(v_type)
    db_session.commit()
    db_session.refresh(v_type)
    return v_type


@pytest.fixture(scope="function")
def price_config(
    db_session: Session,
    vehicle_type: VehicleType,
    business_reference_now: datetime.datetime,
) -> PriceConfig:
    pc = PriceConfig(
        vehicle_type_id=vehicle_type.id,
        is_active=True,
        ticket_type="HOURLY",
        price=25000,
        # Lùi 1 ngày so với reference: bảng giá phải đã có hiệu lực TRƯỚC
        # mọi time_out dẫn xuất từ reference, kể cả khi test lùi/tiến vài
        # giờ quanh mốc đó.
        effective_date=(business_reference_now - datetime.timedelta(days=1)).date(),
    )
    db_session.add(pc)
    db_session.commit()
    db_session.refresh(pc)
    return pc


@pytest.fixture(scope="function")
def zone(db_session: Session) -> Zone:
    z = Zone(name="Khu A", capacity=50, is_active=True)
    db_session.add(z)
    db_session.commit()
    db_session.refresh(z)
    return z


@pytest.fixture(scope="function")
def parking_slot(db_session: Session, zone: Zone, vehicle_type: VehicleType) -> ParkingSlot:
    slot = ParkingSlot(
        zone_id=zone.id,
        vehicle_type_id=vehicle_type.id,
        slot_name="A-01",
        is_occupied=False,
        is_active=True,
    )
    db_session.add(slot)
    db_session.commit()
    db_session.refresh(slot)
    return slot


@pytest.fixture(scope="function")
def customer(db_session: Session) -> Customer:
    c = Customer(full_name="Nguyễn Văn A", phone_number="0900000000")
    db_session.add(c)
    db_session.commit()
    db_session.refresh(c)
    return c


@pytest.fixture(scope="function")
def vehicle(db_session: Session, vehicle_type: VehicleType) -> Vehicle:
    v = Vehicle(license_plate="30A-999.99", vehicle_type_id=vehicle_type.id)
    db_session.add(v)
    db_session.commit()
    db_session.refresh(v)
    return v


@pytest.fixture(scope="function")
def parking_session(
    db_session: Session,
    test_user: User,
    vehicle: Vehicle,
    parking_slot: ParkingSlot,
    price_config: PriceConfig,
    business_reference_now: datetime.datetime,
) -> ParkingSession:
    session = ParkingSession(
        vehicle_id=vehicle.id,
        parking_slot_id=parking_slot.id,
        # NAIVE business-local, cùng hệ quy chiếu với check_in_time/
        # check_out_time thật do server_now() ghi (xem backend/core/clock.py).
        check_in_time=business_reference_now,
        status="active",
        staff_in_id=test_user.id,
    )
    parking_slot.is_occupied = True
    db_session.add(session)
    db_session.commit()
    db_session.refresh(session)
    return session
