"""Waitlist offers use one server instant even when the requested start has passed."""
from datetime import timedelta

import pytest
from fastapi import HTTPException
from sqlalchemy import select, update

from core.clock import BUSINESS_TZ, business_now
from expansion import reservations
from expansion.site_models import ParkingReservation, SiteWaitlist
from expansion.site_schemas import BookingWindow
from models.user import User
from models.parking_session import ParkingSession
from models.parking_slot import ParkingSlot
from models.zone import Zone
from services.parking_service import ParkingService
from services import parking_service as parking_service_module
from test_expansion_sites import data, env
from test_expansion_sites_concurrency import race, store


def waiting(env, *, start=None, end=None):
    body = BookingWindow(**data(env, start=start, end=end).model_dump(exclude={"slot_id"}))
    row = reservations.join_waitlist(env.db, env.staff, body)
    env.db.commit()
    return row


def test_offer_after_start_works_with_real_clock(env, monkeypatch):
    row = waiting(env)
    monkeypatch.setattr(reservations.session_crud, "server_now", business_now)
    before = business_now()
    result = env.client.post(f"/api/v2/sites/{env.a.id}/waitlist/{row.id}/offer")
    after = business_now()
    assert result.status_code == 200, result.text
    offered = env.db.get(ParkingReservation, result.json()["id"])
    assert before <= offered.start_at <= after
    assert offered.end_at == row.end_at
    assert row.status == "offered" and row.reservation_id == offered.id


def test_offer_samples_one_server_instant_when_clock_advances(env, monkeypatch):
    row = waiting(env)
    sampled = []
    base = env.now + timedelta(minutes=1)

    def advancing_clock():
        value = base + timedelta(microseconds=len(sampled))
        sampled.append(value)
        return value

    monkeypatch.setattr(reservations.session_crud, "server_now", advancing_clock)
    offered = reservations.offer_waitlist(env.db, env.staff, row)
    env.db.commit()
    assert sampled == [base]
    assert offered.start_at == base
    assert offered.arrival_deadline == base + timedelta(minutes=15)


def test_offer_future_window_preserves_start_with_real_clock(env, monkeypatch):
    start = env.now + timedelta(hours=1)
    row = waiting(env, start=start)
    monkeypatch.setattr(reservations.session_crud, "server_now", business_now)
    offered = reservations.offer_waitlist(env.db, env.staff, row)
    env.db.commit()
    assert offered.start_at == start
    assert offered.end_at == row.end_at


def test_offer_at_window_end_rejects_without_reservation(env, monkeypatch):
    row = waiting(env)
    monkeypatch.setattr(reservations.session_crud, "server_now", lambda: row.end_at)
    result = env.client.post(f"/api/v2/sites/{env.a.id}/waitlist/{row.id}/offer")
    assert result.status_code == 409
    env.db.refresh(row)
    assert row.status == "waiting" and row.reservation_id is None
    assert not env.db.scalars(select(ParkingReservation)).all()


def test_offered_retry_returns_original_after_window_ends(env, monkeypatch):
    row = waiting(env)
    monkeypatch.setattr(reservations.session_crud, "server_now", business_now)
    first = reservations.offer_waitlist(env.db, env.staff, row)
    env.db.commit()
    original_start = first.start_at
    monkeypatch.setattr(reservations.session_crud, "server_now", lambda: row.end_at + timedelta(days=1))
    retry = reservations.offer_waitlist(env.db, env.staff, row)
    env.db.commit()
    assert retry.id == first.id and retry.start_at == original_start
    assert len(env.db.scalars(select(ParkingReservation)).all()) == 1


def test_direct_reservation_still_rejects_past_client_start(env, monkeypatch):
    body = data(env).model_dump(mode="json")
    monkeypatch.setattr(reservations.session_crud, "server_now", business_now)
    result = env.client.post(f"/api/v2/sites/{env.a.id}/reservations", json=body)
    assert result.status_code == 422
    # The transaction clock is internal; clients cannot supply a clock override.
    future = data(env, start=env.now + timedelta(hours=1)).model_dump(mode="json")
    assert env.client.post(f"/api/v2/sites/{env.a.id}/reservations", json={**future, "_now": body["start_at"]}).status_code == 422


def test_arrival_reuses_accepted_instant_when_clock_crosses_deadline(env, monkeypatch):
    row = reservations.reserve(env.db, env.staff, data(env))
    env.db.commit()
    accepted_at = row.arrival_deadline - timedelta(microseconds=1)
    sampled = []

    def crossing_clock():
        value = accepted_at + timedelta(microseconds=len(sampled))
        sampled.append(value)
        return value

    monkeypatch.setattr(reservations.session_crud, "server_now", crossing_clock)
    result = env.client.post(f"/api/v2/sites/{env.a.id}/reservations/{row.id}/arrive")
    assert result.status_code == 200, result.text
    env.db.refresh(row)
    session = env.db.get(ParkingSession, row.session_id)
    assert row.status == "arrived" and session.status == "active"
    assert session.check_in_time == accepted_at
    assert sampled == [accepted_at]


def test_arrival_at_deadline_does_not_create_session(env, monkeypatch):
    row = reservations.reserve(env.db, env.staff, data(env))
    env.db.commit()
    monkeypatch.setattr(reservations.session_crud, "server_now", lambda: row.arrival_deadline)
    result = env.client.post(f"/api/v2/sites/{env.a.id}/reservations/{row.id}/arrive")
    assert result.status_code == 409
    assert not env.db.scalars(select(ParkingSession)).all()
    assert not env.db.get(ParkingSlot, env.slot.id).is_occupied


def test_failed_reservation_binding_rolls_back_admission_before_commit(env, monkeypatch):
    row = reservations.reserve(env.db, env.staff, data(env))
    env.db.commit()
    monkeypatch.setattr(reservations, "record_admission", lambda db, session: None)
    result = env.client.post(f"/api/v2/sites/{env.a.id}/reservations/{row.id}/arrive")
    assert result.status_code == 409
    env.db.refresh(row)
    assert row.status == "confirmed" and row.session_id is None
    assert not env.db.scalars(select(ParkingSession)).all()
    assert not env.db.get(ParkingSlot, env.slot.id).is_occupied


@pytest.mark.parametrize("move_before", ["service_read", "atomic_claim"])
def test_cross_site_slot_move_cannot_authorize_admission(env, monkeypatch, move_before):
    destination = Zone(name="Review destination B", site_id=env.b.id, capacity=3)
    env.db.add(destination)
    env.db.commit()
    destination_id, slot_id = destination.id, env.slot.id

    def relocate_slot(db):
        # An admin can move an unused slot. Model the committed change between
        # the staff request's scope read and the next admission boundary.
        db.execute(update(ParkingSlot).where(ParkingSlot.id == slot_id).values(zone_id=destination_id))
        db.commit()
        db.expire_all()

    if move_before == "service_read":
        original = ParkingService.check_in

        def interleaved(self, *args, **kwargs):
            relocate_slot(self.db)
            return original(self, *args, **kwargs)

        monkeypatch.setattr(ParkingService, "check_in", interleaved)
    else:
        original = parking_service_module.claim_parking_slot

        def interleaved(db, *args, **kwargs):
            relocate_slot(db)
            return original(db, *args, **kwargs)

        monkeypatch.setattr(parking_service_module, "claim_parking_slot", interleaved)
    result = env.client.post(f"/api/v2/sites/{env.a.id}/check-in", json={
        "license_plate": env.vehicle.license_plate,
        "vehicle_type_id": env.vehicle.vehicle_type_id,
        "parking_slot_id": slot_id,
    })
    assert result.status_code in {404, 409}, result.text
    assert not env.db.scalars(select(ParkingSession)).all()
    slot = env.db.get(ParkingSlot, slot_id)
    assert slot.zone_id == destination_id and not slot.is_occupied


@pytest.mark.parametrize("same_waitlist", [True, False])
def test_parallel_current_offers_preserve_capacity_and_replay(store, monkeypatch, same_waitlist):
    engine, factory, now, ids = store
    with factory() as db:
        actor = db.get(User, ids["actor"])
        rows = []
        for index in range(1 if same_waitlist else 2):
            body = BookingWindow(site_id=ids["site"], vehicle_id=ids["vehicles"][index],
                                 start_at=now.replace(tzinfo=BUSINESS_TZ),
                                 end_at=(now + timedelta(hours=2)).replace(tzinfo=BUSINESS_TZ),
                                 request_id=f"waitlist-offer-race-{index:04}")
            rows.append(reservations.join_waitlist(db, actor, body))
        db.commit()
        waiting_ids = [row.id for row in rows]
    monkeypatch.setattr(reservations.session_crud, "server_now", business_now)

    def offer_action(waiting_id):
        def action():
            with factory() as db:
                actor = db.get(User, ids["actor"])
                row = db.get(SiteWaitlist, waiting_id)
                try:
                    offered = reservations.offer_waitlist(db, actor, row)
                    db.commit()
                    return 200, offered.id
                except HTTPException as exc:
                    db.rollback()
                    return exc.status_code, None
        return action

    results = race(engine, [offer_action(waiting_ids[0]), offer_action(waiting_ids[-1])])
    if same_waitlist:
        assert results[0] == results[1] and results[0][0] == 200
    else:
        assert sorted(code for code, _ in results) == [200, 409]
    with factory() as db:
        assert len(db.scalars(select(ParkingReservation)).all()) == 1
        states = [row.status for row in db.scalars(select(SiteWaitlist))]
        assert states.count("offered") == 1
        assert states.count("waiting") == (0 if same_waitlist else 1)
