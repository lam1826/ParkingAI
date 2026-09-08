"""Public HTTP regressions at the legacy/portal boundary; isolated SQLite only."""
from datetime import timedelta

import pytest
from sqlalchemy import select

from test_portal_api import portal, onboard
from expansion.portal_models import PortalOrder
from expansion.site_models import ParkingSite
from models.monthly_pass import MonthlyPass
from models.parking_session import ParkingSession
from models.payment import Payment
from services.auth_service import get_current_user


def paid_portal_order(portal):
    browser = portal[0]
    order = browser.post("/api/v2/me/orders", json=onboard(portal)).json()
    response = browser.post(f"/api/v2/me/orders/{order['id']}/simulate",
        json={"token": order["demo_token"], "outcome": "success"})
    assert response.status_code == 200, response.text
    return response.json()


def test_legacy_admission_without_sites_keeps_pre_expansion_contract(
    client, db_session, test_user, vehicle, price_config,
):
    client.app.dependency_overrides[get_current_user] = lambda: test_user
    assert list(db_session.scalars(select(ParkingSite))) == []
    response = client.post("/api/v1/parking-sessions/check-in", json={"vehicle_id": vehicle.id})
    assert response.status_code == 201, response.text
    assert response.json()["parking_slot_id"] is None


@pytest.mark.parametrize("site_count", [1, 2])
def test_legacy_admission_requires_slot_for_site_bound_database(
    portal, client, price_config, site_count,
):
    browser, current, users, site, kind, db = portal
    order = paid_portal_order(portal)
    if site_count == 2:
        db.add(ParkingSite(name="Second site"))
        db.commit()
    current["user"] = users[0]
    client.app.dependency_overrides[get_current_user] = lambda: current["user"]

    response = client.post("/api/v1/parking-sessions/check-in",
        json={"vehicle_id": order["vehicle_id"]})

    assert response.status_code == 422, response.text
    assert "vị trí" in response.json()["detail"].lower()
    assert list(db.scalars(select(ParkingSession))) == []


def test_legacy_renewal_cannot_turn_site_portal_pass_into_global_entitlement(portal, client):
    browser, current, users, site, kind, db = portal
    order = paid_portal_order(portal)
    original = db.get(MonthlyPass, order["monthly_pass_id"])
    current["user"] = users[0]
    client.app.dependency_overrides[get_current_user] = lambda: current["user"]
    response = client.post(f"/api/v1/monthly-passes/{original.id}/renew", json={
        "start_date": (original.end_date + timedelta(days=1)).isoformat(),
        "end_date": (original.end_date + timedelta(days=30)).isoformat(),
        "price": 300000, "payment_method": "cash", "request_id": "review-renewal-0001",
    })

    assert response.status_code == 409, response.text
    assert "cổng khách hàng" in response.json()["detail"].lower()
    assert [row.id for row in db.scalars(select(MonthlyPass))] == [original.id]
    assert len(list(db.scalars(select(Payment)))) == 1
    assert db.get(PortalOrder, order["id"]).status == "fulfilled"


@pytest.mark.parametrize("same_site", [True, False])
def test_legacy_admission_with_slot_applies_portal_pass_only_at_its_site(
    portal, client, parking_slot, price_config, same_site,
):
    browser, current, users, site, kind, db = portal
    order = paid_portal_order(portal)
    destination = site
    if not same_site:
        destination = ParkingSite(name="Different pass site")
        db.add(destination)
        db.flush()
    parking_slot.zone.site_id = destination.id
    db.commit()
    current["user"] = users[0]
    client.app.dependency_overrides[get_current_user] = lambda: current["user"]
    response = client.post("/api/v1/parking-sessions/check-in", json={
        "vehicle_id": order["vehicle_id"], "parking_slot_id": parking_slot.id,
    })
    assert response.status_code == 201, response.text
    assert response.json()["monthly_coverage_end"] == (order["end_date"] if same_site else None)
    assert db.get(ParkingSession, response.json()["id"]).monthly_pass_id == (
        order["monthly_pass_id"] if same_site else None)
    assert db.get(type(parking_slot), parking_slot.id).is_occupied


def test_paid_legacy_retry_is_preserved_without_new_collection(portal, client):
    from services.payment_service import PaymentService
    browser, current, users, site, kind, db = portal
    order = paid_portal_order(portal)
    original = db.get(MonthlyPass, order["monthly_pass_id"])
    # Represent a renewal collected before this boundary fix. Never rewrite
    # issued history or charge the same request again during an HTTP retry.
    old = MonthlyPass(customer_id=original.customer_id, vehicle_id=original.vehicle_id,
        card_id=original.card_id, pass_code="REVIEW-ALREADY-COLLECTED",
        start_date=original.end_date + timedelta(days=1),
        end_date=original.end_date + timedelta(days=30), price=300000,
        renewal_key="review-paid-retry-0001", is_active=True)
    db.add(old)
    db.flush()
    PaymentService.record_receipt(db, "monthly_pass", old.id, old.price, users[0].id, "cash")
    db.commit()
    current["user"] = users[0]
    client.app.dependency_overrides[get_current_user] = lambda: current["user"]
    response = client.post(f"/api/v1/monthly-passes/{original.id}/renew", json={
        "start_date": old.start_date.isoformat(), "end_date": old.end_date.isoformat(),
        "price": old.price, "payment_method": "cash", "request_id": old.renewal_key,
    })
    assert response.status_code == 201, response.text
    assert response.json()["id"] == old.id
    assert len(list(db.scalars(select(MonthlyPass)))) == 2
    assert len(list(db.scalars(select(Payment)))) == 2
