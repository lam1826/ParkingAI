import datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from models.monthly_pass import MonthlyPass
from models.price_config import PriceConfig
from models.user import User
from models.zone import Zone
from services.auth_service import AuthService


def make_headers(user: User) -> dict[str, str]:
    token = AuthService().create_access_token(
        user_id=user.id,
        username=user.username,
        role=user.role.name,
    )
    return {"Authorization": f"Bearer {token}"}


@pytest.mark.parametrize("boolean_value", [True, False])
def test_zone_capacity_rejects_boolean_on_create_and_update(
    client: TestClient,
    db_session: Session,
    test_user: User,
    zone: Zone,
    boolean_value: bool,
):
    headers = make_headers(test_user)
    original_count = db_session.query(Zone).count()
    original_capacity = zone.capacity

    created = client.post(
        "/api/v1/zones",
        headers=headers,
        json={"name": "Khu bool", "capacity": boolean_value, "is_active": True},
    )
    updated = client.put(
        f"/api/v1/zones/{zone.id}",
        headers=headers,
        json={"capacity": boolean_value},
    )

    assert created.status_code == 422
    assert updated.status_code == 422
    assert db_session.query(Zone).count() == original_count
    db_session.refresh(zone)
    assert zone.capacity == original_capacity


@pytest.mark.parametrize("boolean_value", [True, False])
def test_price_config_price_rejects_boolean_on_create_and_update(
    client: TestClient,
    db_session: Session,
    test_user: User,
    vehicle_type,
    price_config: PriceConfig,
    boolean_value: bool,
):
    headers = make_headers(test_user)
    original_count = db_session.query(PriceConfig).count()
    original_price = price_config.price

    created = client.post(
        "/api/v1/price-configs",
        headers=headers,
        json={
            "vehicle_type_id": vehicle_type.id,
            "ticket_type": "HOURLY",
            "price": boolean_value,
            "effective_date": datetime.date(2035, 1, 1).isoformat(),
            "is_active": False,
        },
    )
    updated = client.put(
        f"/api/v1/price-configs/{price_config.id}",
        headers=headers,
        json={"price": boolean_value},
    )

    assert created.status_code == 422
    assert updated.status_code == 422
    assert db_session.query(PriceConfig).count() == original_count
    db_session.refresh(price_config)
    assert price_config.price == original_price


@pytest.mark.parametrize("boolean_value", [True, False])
def test_monthly_pass_price_rejects_boolean_on_create_and_update(
    client: TestClient,
    db_session: Session,
    test_user: User,
    vehicle,
    customer,
    business_reference_now,
    boolean_value: bool,
):
    headers = make_headers(test_user)
    start_date = business_reference_now.date()
    monthly_pass = MonthlyPass(
        customer_id=customer.id,
        vehicle_id=vehicle.id,
        pass_code="STRICT-INT-EXISTING",
        price=0,
        start_date=start_date,
        end_date=start_date + datetime.timedelta(days=30),
        is_active=False,
    )
    db_session.add(monthly_pass)
    db_session.commit()
    original_count = db_session.query(MonthlyPass).count()

    created = client.post(
        "/api/v1/monthly-passes",
        headers=headers,
        json={
            "customer_id": customer.id,
            "vehicle_id": vehicle.id,
            "pass_code": "STRICT-INT-CREATE",
            "price": boolean_value,
            "start_date": start_date.isoformat(),
            "end_date": (start_date + datetime.timedelta(days=30)).isoformat(),
            "is_active": False,
        },
    )
    updated = client.put(
        f"/api/v1/monthly-passes/{monthly_pass.id}",
        headers=headers,
        json={"price": boolean_value},
    )

    assert created.status_code == 422
    assert updated.status_code == 422
    assert db_session.query(MonthlyPass).count() == original_count
    db_session.refresh(monthly_pass)
    assert monthly_pass.price == 0
