"""#58: the price API must not leave a vehicle type with no rate in force today.

Admission deliberately refuses a not-yet-effective rate and requires a fallback rate even for
monthly-pass holders (tests/test_rate_provenance.py). Because only one active rate per vehicle
type is allowed, an ACTIVE rate whose effective_date is in the future means "no rate today" and
stops every admission of that type. The write side must refuse that state, and the public price
list must not advertise a rate that is not yet in force.
"""
import datetime

from models.price_config import PriceConfig
from services.auth_service import AuthService
from core.clock import business_today
from expansion.public_profile import walk_in_rates


def _headers(user):
    token = AuthService().create_access_token(user_id=user.id, username=user.username,
        role=user.role.name, password_hash=user.password_hash)
    return {"Authorization": f"Bearer {token}"}


def _tomorrow():
    return business_today() + datetime.timedelta(days=1)


def _snapshot(config):
    return (config.vehicle_type_id, config.ticket_type, config.price, config.effective_date, config.is_active)


def test_put_future_date_on_active_rate_is_rejected_and_admission_keeps_working(
        client, db_session, manager_user, vehicle_type, parking_slot, price_config):
    before = _snapshot(price_config)
    response = client.put(f"/api/v1/price-configs/{price_config.id}",
        json={"price": 7000, "effective_date": _tomorrow().isoformat()}, headers=_headers(manager_user))
    assert response.status_code == 422, response.text
    assert "Ngày áp dụng" in response.json()["detail"]
    db_session.refresh(price_config)
    assert _snapshot(price_config) == before

    admitted = client.post("/parking/check-in", json={"license_plate": "29A-111.11",
        "vehicle_type_id": vehicle_type.id}, headers=_headers(manager_user))
    assert admitted.status_code == 201, admitted.text


def test_post_future_active_replacement_is_rejected(client, db_session, manager_user, vehicle_type, price_config):
    headers = _headers(manager_user)
    assert client.put(f"/api/v1/price-configs/{price_config.id}", json={"is_active": False},
        headers=headers).status_code == 200
    count = db_session.query(PriceConfig).count()
    response = client.post("/api/v1/price-configs", json={"vehicle_type_id": vehicle_type.id,
        "ticket_type": "HOURLY", "price": 7000, "effective_date": _tomorrow().isoformat(), "is_active": True},
        headers=headers)
    assert response.status_code == 422, response.text
    assert db_session.query(PriceConfig).count() == count

    today = client.post("/api/v1/price-configs", json={"vehicle_type_id": vehicle_type.id,
        "ticket_type": "HOURLY", "price": 7000, "effective_date": business_today().isoformat(), "is_active": True},
        headers=headers)
    assert today.status_code == 201, today.text


def test_reactivating_a_future_dated_rate_is_rejected(client, db_session, manager_user, vehicle_type):
    future = PriceConfig(vehicle_type_id=vehicle_type.id, ticket_type="HOURLY", price=7000,
        effective_date=_tomorrow(), is_active=False)
    db_session.add(future)
    db_session.commit()
    response = client.put(f"/api/v1/price-configs/{future.id}", json={"is_active": True},
        headers=_headers(manager_user))
    assert response.status_code == 422, response.text
    db_session.refresh(future)
    assert future.is_active is False


def test_inactive_future_rows_and_current_edits_remain_allowed(client, db_session, manager_user, vehicle_type, price_config):
    headers = _headers(manager_user)
    draft = client.post("/api/v1/price-configs", json={"vehicle_type_id": vehicle_type.id,
        "ticket_type": "HOURLY", "price": 7000, "effective_date": _tomorrow().isoformat(), "is_active": False},
        headers=headers)
    assert draft.status_code == 201, draft.text
    edited = client.put(f"/api/v1/price-configs/{price_config.id}", json={"price": 26000}, headers=headers)
    assert edited.status_code == 200, edited.text
    today = client.put(f"/api/v1/price-configs/{price_config.id}",
        json={"effective_date": business_today().isoformat()}, headers=headers)
    assert today.status_code == 200, today.text


def test_existing_future_active_rate_can_still_be_switched_off(client, db_session, manager_user, vehicle_type):
    legacy = PriceConfig(vehicle_type_id=vehicle_type.id, ticket_type="HOURLY", price=7000,
        effective_date=_tomorrow(), is_active=True)
    db_session.add(legacy)
    db_session.commit()
    response = client.put(f"/api/v1/price-configs/{legacy.id}", json={"is_active": False},
        headers=_headers(manager_user))
    assert response.status_code == 200, response.text


def test_public_walk_in_rates_hide_rates_not_yet_in_force(db_session, vehicle_type, price_config):
    assert [row["price"] for row in walk_in_rates(db_session, [vehicle_type.id])] == [price_config.price]
    price_config.effective_date = _tomorrow()  # legacy row written before the API guard existed
    db_session.commit()
    assert walk_in_rates(db_session, [vehicle_type.id]) == []
