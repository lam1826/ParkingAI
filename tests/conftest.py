import os

os.environ.setdefault("SECRET_KEY", "test_secret_key_for_pytest_123456789")
os.environ.setdefault("GEMINI_API_KEY", "test_gemini_api_key_for_pytest_123456789")

import sys
from pathlib import Path

backend_path = Path(__file__).resolve().parent.parent / "backend"
if str(backend_path) not in sys.path:
    sys.path.insert(0, str(backend_path))

import bcrypt
import datetime
from typing import Generator
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
def price_config(db_session: Session, vehicle_type: VehicleType) -> PriceConfig:
    pc = PriceConfig(
        vehicle_type_id=vehicle_type.id,
        is_active=True,
        ticket_type="HOURLY",
        price=25000.0,
        effective_date=datetime.date.today(),
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
    parking_slot: ParkingSlot
) -> ParkingSession:
    session = ParkingSession(
        vehicle_id=vehicle.id,
        parking_slot_id=parking_slot.id,
        check_in_time=datetime.datetime.now(datetime.timezone.utc),
        status="active",
        staff_in_id=test_user.id,
    )
    parking_slot.is_occupied = True
    db_session.add(session)
    db_session.commit()
    db_session.refresh(session)
    return session
