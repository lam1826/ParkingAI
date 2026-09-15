"""New admissions retain their tariff; only uncovered monthly time is charged."""
from datetime import datetime, timedelta

import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError

from core.billing import BILLING_POLICY_VERSION, SNAPSHOT_FIELDS, billing_basis
from crud import parking_session as session_crud
from models.parking_session import ParkingSession
from models.payment import Payment
from models.monthly_pass import MonthlyPass
from test_core_crud_permissions import core_access  # noqa: F401
from test_vehicle_type_activation import admission
from test_checkout_quote_contract import quote, confirmation, confirm, headers_for
from test_expansion_sites import env, reserve  # noqa: F401


@pytest.fixture
def business_reference_now():
    return datetime(2026, 9, 15, 23)


@pytest.mark.parametrize("path", ["plate", "id", "scoped"])
def test_admission_tariff_survives_price_edit_and_completed_history(
    client, db_session, core_access, monkeypatch, business_reference_now, path,
):
    clock = {"now": business_reference_now}
    monkeypatch.setattr(session_crud, "server_now", lambda: clock["now"])
    staff, manager = (core_access["headers"][role] for role in ("staff", "manager"))
    url, body = admission(core_access, path)
    assert client.post(url, headers=staff, json=body).status_code == 201
    row = db_session.scalar(select(ParkingSession))
    assert row.billing_policy_version == BILLING_POLICY_VERSION
    assert row.rate_unit_price == 25000
    price_url = f"/api/v1/price-configs/{core_access['price-configs'].id}"
    assert client.put(price_url, headers=manager, json={"price": 47000, "ticket_type": "DAILY"}).status_code == 200
    clock["now"] += timedelta(minutes=30)
    q = quote(client, row.id, staff)
    assert q["parking_fee"] == 25000
    assert q["billing_basis"] == {
        "policy_version": "entry-v1", "rate_source": "entry_snapshot",
        "rate_id": row.rate_config_id, "unit_price": 25000, "ticket_type": "HOURLY",
        "effective_date": row.rate_effective_date.isoformat(),
        "billable_from": "2026-09-15T23:00:00+07:00", "billable_seconds": 1800, "billable_blocks": 1,
    }
    # Even removing the mutable tariff after quote cannot strand this stay.
    assert client.put(price_url, headers=manager, json={"is_active": False}).status_code == 200
    assert client.delete(price_url, headers=manager).status_code == 204
    accepted = confirm(client, row.id, staff, confirmation(q))
    assert accepted.status_code == 200, accepted.text
    historical = accepted.json()
    assert historical["billing_basis"] == q["billing_basis"]
    clock["now"] += timedelta(hours=2)
    replay = confirm(client, row.id, staff, confirmation(q))
    assert replay.status_code == 200 and replay.json() == historical
    assert db_session.scalar(select(Payment.amount).where(Payment.source_id == row.id)) == 25000
    listed = client.get(f"/api/v2/sites/{core_access['site'].id}/sessions", headers=staff)
    assert listed.status_code == 200
    assert next(item for item in listed.json() if item["id"] == row.id)["billing_basis"] == q["billing_basis"]


def test_later_admission_uses_updated_price(client, db_session, core_access, monkeypatch, business_reference_now):
    clock = {"now": business_reference_now}
    monkeypatch.setattr(session_crud, "server_now", lambda: clock["now"])
    staff, manager = (core_access["headers"][role] for role in ("staff", "manager"))
    url, body = admission(core_access, "id")
    first = client.post(url, headers=staff, json=body).json()
    clock["now"] += timedelta(minutes=1)
    q = quote(client, first["id"], staff)
    assert confirm(client, first["id"], staff, confirmation(q)).status_code == 200
    assert client.put(f"/api/v1/price-configs/{core_access['price-configs'].id}", headers=manager, json={"price": 42000}).status_code == 200
    second = client.post(url, headers=staff, json=body)
    assert second.status_code == 201
    clock["now"] += timedelta(minutes=1)
    assert quote(client, second.json()["id"], staff)["parking_fee"] == 42000
    assert db_session.get(ParkingSession, first["id"]).parking_fee == 25000


def test_snapshot_quote_still_requires_reconfirmation_at_hour_boundary(client, db_session,
    core_access, monkeypatch, business_reference_now,
):
    clock = {"now": business_reference_now}
    monkeypatch.setattr(session_crud, "server_now", lambda: clock["now"])
    staff = core_access["headers"]["staff"]
    url, body = admission(core_access, "id")
    created = client.post(url, headers=staff, json=body)
    row = db_session.get(ParkingSession, created.json()["id"])
    clock["now"] += timedelta(hours=1)
    q = quote(client, row.id, staff)
    clock["now"] += timedelta(microseconds=1)
    rejected = confirm(client, row.id, staff, confirmation(q))
    assert rejected.status_code == 409 and rejected.json()["detail"]["code"] == "checkout_quote_changed"
    db_session.refresh(row)
    assert row.status == "active" and core_access["parking-slots"].is_occupied
    assert db_session.scalar(select(Payment.id).where(Payment.source_id == row.id)) is None
    q2 = quote(client, row.id, staff)
    assert q2["parking_fee"] == 50000 and q2["billing_basis"]["billable_seconds"] == 3601
    assert confirm(client, row.id, staff, confirmation(q2)).status_code == 200


@pytest.mark.parametrize("path", ["plate", "id", "scoped"])
def test_clients_cannot_choose_admission_snapshot(client, db_session, core_access, path):
    url, body = admission(core_access, path)
    result = client.post(url, headers=core_access["headers"]["staff"],
                         json={**body, "billing_policy_version": "entry-v1", "rate_unit_price": 1})
    assert result.status_code == 422
    assert db_session.scalar(select(ParkingSession.id)) is None


def test_reservation_arrival_takes_tariff_at_admission_not_booking(env):
    reservation = reserve(env)
    from models.price_config import PriceConfig
    from expansion import reservations
    rate = env.db.scalar(select(PriceConfig))
    rate.price = 31000
    env.db.commit()
    result = reservations.arrive(env.db, env.staff, reservation)
    stay = env.db.get(ParkingSession, result.session_id)
    assert stay.rate_unit_price == 31000 and stay.billing_policy_version == "entry-v1"


@pytest.mark.parametrize("departure,expected_seconds,expected_blocks", [
    (timedelta(), 0, 0), (timedelta(minutes=30), 1800, 1),
    (timedelta(hours=1), 3600, 1), (timedelta(hours=1, microseconds=1), 3601, 2),
])
def test_monthly_only_charges_after_midnight_coverage_end(client, db_session, test_user,
    vehicle, customer, parking_slot, price_config, monkeypatch, business_reference_now,
    departure, expected_seconds, expected_blocks,
):
    entered = business_reference_now
    monthly = MonthlyPass(vehicle_id=vehicle.id, customer_id=customer.id, pass_code="SNAP-MONTHLY",
                          price=0, start_date=entered.date(), end_date=entered.date(), is_active=True)
    db_session.add(monthly); db_session.commit()
    monkeypatch.setattr(session_crud, "server_now", lambda: entered)
    headers = headers_for(test_user)
    created = client.post("/api/v1/parking-sessions/check-in", headers=headers,
                          json={"vehicle_id": vehicle.id, "parking_slot_id": parking_slot.id})
    assert created.status_code == 201, created.text
    session_id = created.json()["id"]
    # Still covered immediately before expiry, no fee.
    monkeypatch.setattr(session_crud, "server_now", lambda: entered + timedelta(minutes=59))
    assert quote(client, session_id, headers)["parking_fee"] == 0
    ended = entered + timedelta(hours=1) + departure
    monkeypatch.setattr(session_crud, "server_now", lambda: ended)
    q = quote(client, session_id, headers)
    assert q["parking_fee"] == expected_blocks * price_config.price
    assert q["billing_basis"]["billable_from"] == "2026-09-16T00:00:00+07:00"
    assert q["billing_basis"]["billable_seconds"] == expected_seconds
    assert q["billing_basis"]["billable_blocks"] == expected_blocks
    result = confirm(client, session_id, headers, confirmation(q))
    assert result.status_code == 200, result.text
    assert result.json()["billing_basis"] == q["billing_basis"]


@pytest.mark.parametrize("ticket,elapsed,blocks", [
    ("HOURLY", timedelta(), 0), ("HOURLY", timedelta(microseconds=1), 1),
    ("HOURLY", timedelta(hours=1), 1), ("HOURLY", timedelta(hours=1, microseconds=1), 2),
    ("DAILY", timedelta(days=1), 1), ("DAILY", timedelta(days=1, microseconds=1), 2),
])
def test_exact_billing_block_boundaries(ticket, elapsed, blocks):
    start = datetime(2026, 9, 15, 23)
    basis = billing_basis(time_in=start, time_out=start + elapsed, unit_price=25000,
                          ticket_type=ticket, rate_id=1, effective_date=start.date(), policy_version="entry-v1")
    assert basis["billable_blocks"] == blocks


@pytest.mark.parametrize("field", SNAPSHOT_FIELDS)
def test_snapshot_is_immutable_even_on_legacy_null(db_session, parking_session, field):
    replacement = {"billing_policy_version": "entry-v1", "rate_config_id": 1,
                   "rate_ticket_type": "HOURLY", "rate_unit_price": 99999, "rate_effective_date": "2026-01-01"}[field]
    with pytest.raises(IntegrityError, match="snapshot immutable"):
        db_session.execute(text(f"UPDATE parking_sessions SET {field} = :replacement WHERE id = :id"),
                           {"replacement": replacement, "id": parking_session.id})
    db_session.rollback()


def test_legacy_monthly_overstay_keeps_full_stay_compatibility(client, db_session, parking_session,
    vehicle, customer, test_user, monkeypatch, business_reference_now,
):
    # Seed a historical entitlement before writing the legacy stay; no route can
    # retrofit it. Fixture session is already immutable so use a separate row.
    db_session.delete(parking_session); db_session.commit()
    monthly = MonthlyPass(vehicle_id=vehicle.id, customer_id=customer.id, pass_code="LEGACY-SNAPSHOT",
                          price=0, start_date=business_reference_now.date(), end_date=business_reference_now.date(), is_active=True)
    db_session.add(monthly); db_session.flush()
    row = ParkingSession(vehicle_id=vehicle.id, monthly_pass_id=monthly.id,
                         monthly_coverage_end=monthly.end_date, check_in_time=business_reference_now,
                         staff_in_id=test_user.id, status="active")
    db_session.add(row); db_session.commit()
    monkeypatch.setattr(session_crud, "server_now", lambda: business_reference_now + timedelta(hours=1, minutes=30))
    headers = headers_for(test_user)
    q = quote(client, row.id, headers)
    assert q["parking_fee"] == 50000
    assert q["billing_basis"]["rate_source"] == "legacy_current_rate"
    assert confirm(client, row.id, headers, confirmation(q)).json()["billing_basis"] is None


def test_legacy_covered_quote_does_not_apply_uncovered_overflow_validation(client, db_session,
    vehicle, customer, test_user, price_config, monkeypatch, business_reference_now,
):
    from core.money import MAX_EXACT_VND
    price_config.price = MAX_EXACT_VND
    period = MonthlyPass(vehicle_id=vehicle.id, customer_id=customer.id, pass_code="LEGACY-COVERED",
                         price=0, start_date=business_reference_now.date(),
                         end_date=(business_reference_now + timedelta(days=30)).date(), is_active=True)
    db_session.add(period); db_session.flush()
    row = ParkingSession(vehicle_id=vehicle.id, monthly_pass_id=period.id,
                         check_in_time=business_reference_now, staff_in_id=test_user.id, status="active")
    db_session.add(row); db_session.commit()
    monkeypatch.setattr(session_crud, "server_now", lambda: business_reference_now + timedelta(days=20))
    q = quote(client, row.id, headers_for(test_user))
    assert q["parking_fee"] == 0
    assert q["billing_basis"]["billable_seconds"] == q["billing_basis"]["billable_blocks"] == 0
