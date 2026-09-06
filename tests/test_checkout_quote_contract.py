"""Independent API acceptance tests for reviewed, explicitly confirmed checkout.

All data uses conftest's isolated SQLite database and fake authentication.
Requests deliberately exercise the public routes without automatic body injection.
"""
from datetime import datetime, timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError

from crud import parking_session as session_crud
from models.payment import Payment
from models.role import Role
from models.user import User
from services.auth_service import AuthService
from services.payment_service import PaymentService


@pytest.fixture
def business_reference_now():
    return datetime(2026, 9, 7, 10, 0)


@pytest.fixture
def clock(monkeypatch, business_reference_now):
    value = {"now": business_reference_now + timedelta(minutes=30)}
    monkeypatch.setattr(session_crud, "server_now", lambda: value["now"])
    return value


def headers_for(user):
    token = AuthService().create_access_token(
        user_id=user.id, username=user.username, role=str(user.role)
    )
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def staff_headers(test_user):
    return headers_for(test_user)


def quote(client, session_id, headers):
    response = client.get(f"/api/v1/parking-sessions/{session_id}/checkout-quote", headers=headers)
    assert response.status_code == 200, response.text
    return response.json()


def confirmation(q, method="cash"):
    return {"quote_token": q["quote_token"], "payment_confirmed": True,
            "payment_method": method if q["parking_fee"] > 0 else None}


def confirm(client, session_id, headers, payload):
    return client.put(f"/api/v1/parking-sessions/{session_id}/check-out", json=payload, headers=headers)


def assert_not_collected(db, session, slot):
    db.expire_all()
    assert session.status == "active"
    assert session.check_out_time is None
    assert session.parking_fee is None
    assert slot.is_occupied
    assert db.scalar(select(Payment.id).where(Payment.source_type == "parking_session",
                                            Payment.source_id == session.id)) is None


def test_preview_is_read_only_and_dates_have_timezone(client, db_session, parking_session,
        parking_slot, staff_headers, clock):
    q = quote(client, parking_session.id, staff_headers)
    assert q["parking_fee"] == 25000
    assert q["duration_minutes"] == 30
    assert q["session_id"] == parking_session.id
    assert q["license_plate"] == "30A-999.99"
    quoted = datetime.fromisoformat(q["quoted_at"])
    expires = datetime.fromisoformat(q["expires_at"])
    assert quoted.utcoffset() is not None and expires.utcoffset() is not None
    assert expires - quoted == timedelta(seconds=120)
    assert_not_collected(db_session, parking_session, parking_slot)


@pytest.mark.parametrize("patch", [
    {"payment_confirmed": False}, {"payment_confirmed": "true"},
    {"payment_confirmed": 1}, {"payment_method": None},
    {"payment_method": "online"}, {"parking_fee": 1},
])
def test_confirmation_cannot_be_coerced_or_override_fee(patch, client, db_session,
        parking_session, parking_slot, staff_headers, clock):
    body = confirmation(quote(client, parking_session.id, staff_headers)) | patch
    result = confirm(client, parking_session.id, staff_headers, body)
    assert result.status_code == 422, result.text
    assert_not_collected(db_session, parking_session, parking_slot)


@pytest.mark.parametrize("legacy", [False, True])
def test_old_clients_cannot_silently_collect(legacy, client, db_session, parking_session,
        parking_slot, vehicle, staff_headers, clock):
    if legacy:
        result = client.post("/parking/check-out", json={"license_plate": vehicle.license_plate}, headers=staff_headers)
    else:
        result = confirm(client, parking_session.id, staff_headers, {})
    assert result.status_code == 422, result.text
    assert_not_collected(db_session, parking_session, parking_slot)


@pytest.mark.parametrize("advance", [120, 121])
def test_expired_quote_does_not_release_slot(advance, client, db_session, parking_session,
        parking_slot, staff_headers, clock):
    body = confirmation(quote(client, parking_session.id, staff_headers))
    clock["now"] += timedelta(seconds=advance)
    result = confirm(client, parking_session.id, staff_headers, body)
    assert result.status_code == 409, result.text
    assert_not_collected(db_session, parking_session, parking_slot)


def test_crossing_billing_boundary_requires_new_confirmation(client, db_session,
        parking_session, parking_slot, staff_headers, clock, business_reference_now):
    clock["now"] = business_reference_now + timedelta(minutes=59, seconds=59)
    body = confirmation(quote(client, parking_session.id, staff_headers))
    clock["now"] += timedelta(seconds=2)
    result = confirm(client, parking_session.id, staff_headers, body)
    assert result.status_code == 409, result.text
    assert_not_collected(db_session, parking_session, parking_slot)
    q2 = quote(client, parking_session.id, staff_headers)
    assert q2["parking_fee"] == 50000
    result = confirm(client, parking_session.id, staff_headers, confirmation(q2))
    assert result.status_code == 200, result.text
    assert result.json()["parking_fee"] == 50000


def test_transfer_retry_after_expiry_keeps_single_original_receipt(client, db_session,
        parking_session, staff_headers, test_user, clock):
    body = confirmation(quote(client, parking_session.id, staff_headers), "transfer")
    result = confirm(client, parking_session.id, staff_headers, body)
    assert result.status_code == 200, result.text
    original = result.json()
    clock["now"] += timedelta(hours=2)
    repeated = confirm(client, parking_session.id, staff_headers, body)
    assert repeated.status_code == 200, repeated.text
    assert repeated.json() == original
    receipts = db_session.scalars(select(Payment).where(Payment.source_id == parking_session.id)).all()
    assert len(receipts) == 1
    assert receipts[0].method == "transfer" and receipts[0].amount == 25000
    assert receipts[0].collected_by_id == test_user.id
    mismatch = confirm(client, parking_session.id, staff_headers, body | {"payment_method": "cash"})
    assert mismatch.status_code == 409


def test_different_valid_quote_cannot_replay_completed_session(client, db_session,
        parking_session, staff_headers, clock):
    first = confirmation(quote(client, parking_session.id, staff_headers))
    second = confirmation(quote(client, parking_session.id, staff_headers))
    assert first["quote_token"] != second["quote_token"]
    result = confirm(client, parking_session.id, staff_headers, first)
    assert result.status_code == 200, result.text
    assert confirm(client, parking_session.id, staff_headers, second).status_code == 409


def test_tampered_quote_and_wrong_actor_are_rejected(client, db_session, parking_session,
        parking_slot, staff_headers, test_user, clock):
    body = confirmation(quote(client, parking_session.id, staff_headers))
    token = body["quote_token"]
    tampered = ("B" if token[0] == "A" else "A") + token[1:]
    rejected = confirm(client, parking_session.id, staff_headers, body | {"quote_token": tampered})
    assert rejected.status_code in {400, 403, 409, 422}, rejected.text
    other = User(username="quote_other_staff", full_name="Other test staff", role_id=test_user.role_id,
                 password_hash=test_user.password_hash, is_active=True)
    db_session.add(other)
    db_session.commit()
    rejected = confirm(client, parking_session.id, headers_for(other), body)
    assert rejected.status_code in {403, 409}, rejected.text
    assert_not_collected(db_session, parking_session, parking_slot)


def test_customer_cannot_preview_or_confirm(client, db_session, parking_session,
        parking_slot, staff_headers, test_user, clock):
    body = confirmation(quote(client, parking_session.id, staff_headers))
    role = Role(name="customer")
    db_session.add(role)
    db_session.flush()
    user = User(username="quote_customer", full_name="Test customer", role_id=role.id, password_hash=test_user.password_hash,
                is_active=True)
    db_session.add(user)
    db_session.commit()
    headers = headers_for(user)
    assert client.get(f"/api/v1/parking-sessions/{parking_session.id}/checkout-quote", headers=headers).status_code == 403
    assert confirm(client, parking_session.id, headers, body).status_code == 403
    assert_not_collected(db_session, parking_session, parking_slot)


def test_receipt_failure_rolls_back_completion_and_quote_can_be_retried(client, db_session,
        parking_session, parking_slot, staff_headers, clock, monkeypatch):
    body = confirmation(quote(client, parking_session.id, staff_headers))
    original = PaymentService.record_receipt

    def unavailable(*args, **kwargs):
        raise SQLAlchemyError("synthetic receipt write failure")

    monkeypatch.setattr(PaymentService, "record_receipt", unavailable)
    result = confirm(client, parking_session.id, staff_headers, body)
    assert result.status_code == 500, result.text
    assert_not_collected(db_session, parking_session, parking_slot)
    monkeypatch.setattr(PaymentService, "record_receipt", original)
    result = confirm(client, parking_session.id, staff_headers, body)
    assert result.status_code == 200, result.text


def test_zero_fee_has_explicit_confirmation_without_fake_cash_receipt(client, db_session,
        parking_slot, vehicle, test_user, staff_headers, clock, price_config):
    from models.parking_session import ParkingSession
    # Configure the free tariff before admission; production correctly blocks
    # changing an effective tariff while a vehicle is using it.
    price_config.price = 0
    db_session.commit()
    parking_session = ParkingSession(vehicle_id=vehicle.id, parking_slot_id=parking_slot.id,
        check_in_time=clock["now"] - timedelta(minutes=30), staff_in_id=test_user.id, status="active")
    parking_slot.is_occupied = True
    db_session.add(parking_session)
    db_session.commit()
    q = quote(client, parking_session.id, staff_headers)
    assert q["parking_fee"] == 0
    body = confirmation(q)
    result = confirm(client, parking_session.id, staff_headers, body)
    assert result.status_code == 200, result.text
    db_session.expire_all()
    assert parking_session.status == "completed" and not parking_slot.is_occupied
    assert not db_session.scalars(select(Payment).where(Payment.source_id == parking_session.id)).all()
    clock["now"] += timedelta(minutes=10)
    assert confirm(client, parking_session.id, staff_headers, body).status_code == 200


def test_legacy_retry_after_vehicle_reenters_never_closes_new_session(client, db_session,
        parking_session, parking_slot, vehicle, staff_headers, clock):
    original_id = parking_session.id
    body = confirmation(quote(client, original_id, staff_headers)) | {"license_plate": vehicle.license_plate}
    first = client.post("/parking/check-out", json=body, headers=staff_headers)
    assert first.status_code == 200, first.text
    clock["now"] += timedelta(seconds=1)
    admitted = client.post("/api/v1/parking-sessions/check-in",
        json={"vehicle_id": vehicle.id, "parking_slot_id": parking_slot.id}, headers=staff_headers)
    assert admitted.status_code == 201, admitted.text
    new_id = admitted.json()["id"]
    clock["now"] += timedelta(minutes=5)
    retry = client.post("/parking/check-out", json=body, headers=staff_headers)
    assert retry.status_code == 200, retry.text
    assert retry.json()["session_id"] == original_id
    current = client.get(f"/api/v1/parking-sessions/{new_id}", headers=staff_headers)
    assert current.status_code == 200 and current.json()["status"] == "active"
    db_session.expire_all()
    assert parking_slot.is_occupied
    assert not db_session.scalars(select(Payment).where(Payment.source_id == new_id)).all()
