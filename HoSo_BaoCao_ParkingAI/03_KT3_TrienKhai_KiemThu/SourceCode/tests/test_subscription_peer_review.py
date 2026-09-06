"""Independent review checks for financial atomicity and malformed QR tokens."""
from checkout_helpers import quote_confirmation, service_confirmation
from datetime import timedelta
from uuid import uuid4

import pytest
from fastapi import HTTPException

from models.monthly_pass import MonthlyPass
from models.parking_card import ParkingCard
from models.parking_session import ParkingSession
from models.payment import Payment
from services.auth_service import AuthService
from services.payment_service import PaymentService
from services.ticket_service import resolve_ticket, ticket_token


def headers(user):
    token = AuthService().create_access_token(user_id=user.id, username=user.username, role=user.role.name)
    return {"Authorization": f"Bearer {token}"}


def test_non_ascii_ticket_signature_is_validation_error():
    token = ticket_token(str(uuid4())).rsplit(".", 1)[0] + "." + "é" * 32
    with pytest.raises(HTTPException) as error:
        resolve_ticket(token)
    assert error.value.status_code == 400


@pytest.mark.parametrize("route", ["/parking/check-out", "/api/v1/parking-sessions/{id}/check-out"])
def test_collection_failure_restores_session_and_slot(client, db_session, test_user,
        vehicle, parking_slot, price_config, monkeypatch, route):
    admission = client.post("/api/v1/parking-sessions/check-in", headers=headers(test_user),
        json={"vehicle_id": vehicle.id, "parking_slot_id": parking_slot.id})
    assert admission.status_code == 201, admission.text
    session_id = admission.json()["id"]

    def fail(*args, **kwargs):
        raise HTTPException(409, "Collection failed")
    monkeypatch.setattr(PaymentService, "record_receipt", fail)
    confirmation = quote_confirmation(client, headers(test_user), session_id)
    if route.startswith("/parking/"):
        result = client.post(route, headers=headers(test_user), json={**{"license_plate": vehicle.license_plate}, **confirmation})
    else:
        result = client.put(route.format(id=session_id), headers=headers(test_user), json=confirmation)
    assert result.status_code == 409
    db_session.expire_all()
    session = db_session.get(ParkingSession, session_id)
    assert (session.status, session.check_out_time, session.parking_fee) == ("active", None, None)
    assert parking_slot.is_occupied is True
    assert db_session.query(Payment).count() == 0


def test_failed_legacy_renewal_rolls_back_linkage_and_retry_succeeds(client, db_session,
        test_user, vehicle, customer, business_reference_now, monkeypatch):
    day = business_reference_now.date()
    original = MonthlyPass(customer_id=customer.id, vehicle_id=vehicle.id, pass_code="LEGACY-PEER",
        price=500000, start_date=day - timedelta(days=30), end_date=day - timedelta(days=1), is_active=True)
    db_session.add(original)
    db_session.commit()
    original_id = original.id
    payload = {"start_date": day.isoformat(), "end_date": (day + timedelta(days=29)).isoformat(),
        "price": 600000, "request_id": str(uuid4()), "payment_method": "cash"}
    endpoint = f"/api/v1/monthly-passes/{original_id}/renew"
    actual_collect = PaymentService.record_receipt

    def fail(*args, **kwargs):
        raise HTTPException(409, "Collection failed")
    monkeypatch.setattr(PaymentService, "record_receipt", fail)
    assert client.post(endpoint, headers=headers(test_user), json=payload).status_code == 409
    db_session.expire_all()
    assert db_session.get(MonthlyPass, original_id).card_id is None
    assert db_session.query(ParkingCard).count() == db_session.query(Payment).count() == 0
    assert db_session.query(MonthlyPass).count() == 1

    monkeypatch.setattr(PaymentService, "record_receipt", actual_collect)
    retried = client.post(endpoint, headers=headers(test_user), json=payload)
    assert retried.status_code == 201, retried.text
    assert retried.json()["card_code"] == "LEGACY-PEER"
    assert db_session.query(Payment).count() == 1
    assert db_session.query(MonthlyPass).count() == 2


def test_legacy_period_linked_to_card_cannot_change_owner_after_renewal(client, db_session,
        test_user, vehicle, customer, business_reference_now):
    from models.customer import Customer
    day = business_reference_now.date()
    original = MonthlyPass(customer_id=customer.id, vehicle_id=vehicle.id, pass_code="LEGACY-LINK",
        price=500000, start_date=day - timedelta(days=30), end_date=day - timedelta(days=1), is_active=True)
    other_customer = Customer(full_name="Khách khác", phone_number="0900000001")
    db_session.add_all([original, other_customer])
    db_session.commit()
    endpoint = f"/api/v1/monthly-passes/{original.id}"
    renewed = client.post(endpoint + "/renew", headers=headers(test_user), json={
        "start_date": day.isoformat(), "end_date": (day + timedelta(days=29)).isoformat(),
        "price": 600000, "request_id": str(uuid4())})
    assert renewed.status_code == 201, renewed.text
    changed = client.put(endpoint, headers=headers(test_user), json={"customer_id": other_customer.id})
    assert changed.status_code == 409
    db_session.expire_all()
    assert original.customer_id == original.card.customer_id == customer.id
