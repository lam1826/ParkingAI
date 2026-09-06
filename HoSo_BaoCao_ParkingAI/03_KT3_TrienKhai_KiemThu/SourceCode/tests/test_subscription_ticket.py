"""Paid renewal, rollback and signed ticket flows through the actual API."""
from checkout_helpers import quote_confirmation, service_confirmation
from datetime import timedelta
from uuid import uuid4

from sqlalchemy import select

from models.monthly_pass import MonthlyPass
from models.payment import Payment
from models.parking_session import ParkingSession
from services.auth_service import AuthService
from services.parking_service import ParkingService


def headers(user):
    token = AuthService().create_access_token(user_id=user.id, username=user.username, role=user.role.name)
    return {"Authorization": f"Bearer {token}"}


def create_paid(client, test_user, customer, vehicle, business_reference_now):
    day = business_reference_now.date()
    response = client.post("/api/v1/monthly-passes", headers=headers(test_user), json={
        "customer_id": customer.id, "vehicle_id": vehicle.id, "pass_code": "CARD-ROOT-1",
        "start_date": day.isoformat(), "end_date": (day + timedelta(days=29)).isoformat(),
        "price": 500000,
    })
    assert response.status_code == 201, response.text
    return response.json()


def test_renew_used_pass_retains_card_history_and_collects_once(client, db_session, test_user,
        customer, vehicle, price_config, parking_slot, business_reference_now):
    original = create_paid(client, test_user, customer, vehicle, business_reference_now)
    admission = client.post("/api/v1/parking-sessions/check-in", headers=headers(test_user), json={
        "vehicle_id": vehicle.id, "parking_slot_id": parking_slot.id,
    })
    assert admission.status_code == 201, admission.text
    payload = {"start_date": (business_reference_now.date() + timedelta(days=30)).isoformat(),
        "end_date": (business_reference_now.date() + timedelta(days=59)).isoformat(),
        "price": 600000, "payment_method": "transfer", "request_id": str(uuid4())}
    first = client.post(f"/api/v1/monthly-passes/{original['id']}/renew", headers=headers(test_user), json=payload)
    assert first.status_code == 201, first.text
    retry = client.post(f"/api/v1/monthly-passes/{original['id']}/renew", headers=headers(test_user), json=payload)
    assert retry.status_code == 201, retry.text
    assert first.json()["id"] == retry.json()["id"] != original["id"]
    assert first.json()["card_code"] == original["card_code"] == "CARD-ROOT-1"
    assert first.json()["pass_code"] != original["pass_code"]
    assert db_session.get(MonthlyPass, original["id"]).end_date.isoformat() == original["end_date"]
    assert db_session.get(ParkingSession, admission.json()["id"]).monthly_pass_id == original["id"]
    receipts = db_session.scalars(select(Payment).where(Payment.source_type == "monthly_pass")).all()
    assert sorted(p.amount for p in receipts) == [500000, 600000]
    assert ParkingService(db_session).get_dashboard_data()["total_revenue_today"] == 1100000
    conflict = client.post(f"/api/v1/monthly-passes/{original['id']}/renew", headers=headers(test_user), json={**payload, "price": 700000})
    assert conflict.status_code == 409


def test_overlap_renewal_and_paid_edit_never_change_receipts(client, db_session, test_user,
        customer, vehicle, business_reference_now):
    original = create_paid(client, test_user, customer, vehicle, business_reference_now)
    endpoint = f"/api/v1/monthly-passes/{original['id']}"
    response = client.post(endpoint + "/renew", headers=headers(test_user), json={
        "start_date": original["end_date"], "end_date": original["end_date"], "price": 1, "request_id": str(uuid4())})
    assert response.status_code == 409
    assert client.put(endpoint, headers=headers(test_user), json={"price": 0}).status_code == 409
    assert client.delete(endpoint, headers=headers(test_user)).status_code == 409
    assert client.put(endpoint, headers=headers(test_user), json={"is_active": False}).status_code == 200
    assert db_session.query(Payment).count() == 1
    assert db_session.query(MonthlyPass).count() == 1


def test_receipt_failure_rolls_back_period_and_card(client, db_session, test_user, customer,
        vehicle, business_reference_now, monkeypatch):
    from fastapi import HTTPException
    from models.parking_card import ParkingCard
    from services.payment_service import PaymentService
    def fail(*args, **kwargs):
        raise HTTPException(409, "Collection failed")
    monkeypatch.setattr(PaymentService, "record_receipt", fail)
    day = business_reference_now.date().isoformat()
    response = client.post("/api/v1/monthly-passes", headers=headers(test_user), json={
        "customer_id": customer.id, "vehicle_id": vehicle.id, "pass_code": "ROLLBACK", "price": 1,
        "start_date": day, "end_date": day})
    assert response.status_code == 409
    assert db_session.query(MonthlyPass).count() == db_session.query(ParkingCard).count() == 0


def test_qr_requires_staff_rejects_tampering_and_checkout_collects_once(client, db_session,
        test_user, vehicle, parking_slot, price_config):
    response = client.post("/api/v1/parking-sessions/check-in", headers=headers(test_user), json={
        "vehicle_id": vehicle.id, "parking_slot_id": parking_slot.id})
    assert response.status_code == 201, response.text
    session_id = response.json()["id"]
    endpoint = f"/api/v1/parking-sessions/{session_id}/ticket"
    assert client.get(endpoint).status_code == 401
    ticket = client.get(endpoint, headers=headers(test_user))
    assert ticket.status_code == 200, ticket.text
    data = ticket.json()
    assert "<svg" in data["qr_svg"]
    assert data["license_plate"] == vehicle.license_plate
    resolve = "/api/v1/parking-sessions/tickets/resolve"
    assert client.get(resolve, headers=headers(test_user), params={"token": data["qr_payload"]}).json()["session_id"] == session_id
    assert client.get(resolve, headers=headers(test_user), params={"token": data["qr_payload"][:-1] + "X"}).status_code == 400
    assert db_session.get(ParkingSession, session_id).status == "active"
    confirmation = quote_confirmation(client, headers(test_user), session_id)
    first = client.put(f"/api/v1/parking-sessions/{session_id}/check-out", headers=headers(test_user), json=confirmation)
    retry = client.put(f"/api/v1/parking-sessions/{session_id}/check-out", headers=headers(test_user), json=confirmation)
    assert first.status_code == retry.status_code == 200, first.text
    assert first.json()["parking_fee"] == retry.json()["parking_fee"]
    assert db_session.query(Payment).filter(Payment.source_id == session_id).count() == 1
    receipt = client.get(endpoint, headers=headers(test_user)).json()
    assert receipt["status"] == "completed" and receipt["parking_fee"] == first.json()["parking_fee"]
