"""Occupancy is private evidence, never an admission or inventory mutation."""
import hashlib
from datetime import datetime, timedelta
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import event, func, select
from sqlalchemy.exc import IntegrityError

import core.clock as clock
from database import get_db
from expansion import occupancy_engine
from expansion.occupancy_models import OccupancyCalibration, OccupancyCalibrationSlot, OccupancyObservation
from expansion.occupancy_router import router, _gate
from expansion.site_models import ParkingSite, SiteMembership
from expansion.vision_models import Camera, VisionObservation
from models.parking_session import ParkingSession
from services.auth_service import get_current_user
from test_occupancy_engine import frame


@pytest.fixture
def occupancy(db_session, test_user, zone, parking_slot, monkeypatch):
    now = datetime(2026, 9, 15, 10, 0)
    class Frozen(datetime):
        @classmethod
        def now(cls, tz=None):
            return now.replace(tzinfo=clock.BUSINESS_TZ).astimezone(tz) if tz else now
    monkeypatch.setattr(clock, "datetime", Frozen)
    test_user.role.name = "manager"
    site, other = ParkingSite(name="Occupancy QA"), ParkingSite(name="Foreign CV")
    db_session.add_all([site, other]); db_session.flush()
    zone.site_id = site.id
    db_session.add(SiteMembership(site_id=site.id, user_id=test_user.id, role="manager"))
    camera = Camera(site_id=site.id, zone_id=zone.id, name="Fixed view", direction="entry", retention_hours=24)
    foreign = Camera(site_id=other.id, name="Foreign view", direction="entry")
    db_session.add_all([camera, foreign]); db_session.commit()
    app = FastAPI(); app.include_router(router)
    app.dependency_overrides[get_db] = lambda: db_session
    app.dependency_overrides[get_current_user] = lambda: test_user
    with TestClient(app) as client:
        yield client, db_session, camera, foreign, test_user, parking_slot, now


def image(db, camera, now, *, age=0, received_age=0, vehicle=False):
    content = frame(vehicle=vehicle)
    row = VisionObservation(camera_id=camera.id, site_id=camera.site_id, event_id=str(uuid4()),
        image_hash=hashlib.sha256(content).hexdigest(), image_bytes=content, image_width=160, image_height=160,
        observed_at=now - timedelta(seconds=received_age), captured_at=now - timedelta(seconds=age),
        expires_at=now + timedelta(hours=24), ocr_status="no_plate", engine="disabled", detections=[])
    db.add(row); db.commit()
    return row


def calibration(ctx, *, confirmations=1):
    client, db, camera, _, _, slot, now = ctx
    reference = image(db, camera, now, age=60)
    body = {"camera_id": camera.id, "reference_observation_id": reference.id,
        "regions": [{"slot_id": slot.id, "polygon": [[.1, .1], [.45, .1], [.45, .8], [.1, .8]]}],
        "settings": {"confirmation_frames": confirmations}, "empty_reference_confirmed": True, "request_id": str(uuid4())}
    response = client.post(f"/api/v2/sites/{camera.site_id}/occupancy/calibrations", json=body)
    assert response.status_code == 200, response.text
    return response.json(), reference, body


def analyze(ctx, config, source):
    client, _, camera, *_ = ctx
    return client.post(f"/api/v2/sites/{camera.site_id}/occupancy/analyze", json={
        "camera_id": camera.id, "calibration_id": config["id"], "observation_id": source.id})


def current(ctx):
    client, _, camera, *_ = ctx
    result = client.get(f"/api/v2/sites/{camera.site_id}/occupancy", params={"camera_id": camera.id})
    assert result.status_code == 200, result.text
    assert result.headers["cache-control"] == "no-store"
    return result.json()


def test_observation_idempotence_discrepancy_and_no_business_writes(occupancy):
    _, db, camera, _, _, slot, now = occupancy
    config, _, _ = calibration(occupancy)
    source = image(db, camera, now, vehicle=True)
    response = analyze(occupancy, config, source)
    assert response.status_code == 200, response.text
    reading = response.json()["readings"][0]
    assert reading["state"] == "occupied" and reading["mismatch"] is True
    assert response.json()["latest"]["measured_at"].endswith("+07:00")
    assert analyze(occupancy, config, source).json()["latest"]["id"] == response.json()["latest"]["id"]
    assert db.scalar(select(func.count()).select_from(OccupancyObservation)) == 1
    assert db.scalar(select(func.count()).select_from(ParkingSession)) == 0
    db.refresh(slot)
    assert slot.is_occupied is False


def test_metadata_read_avoids_private_blobs_and_financial_queries(occupancy):
    _, db, camera, _, _, _, now = occupancy
    config, _, _ = calibration(occupancy)
    assert analyze(occupancy, config, image(db, camera, now)).status_code == 200
    statements = []
    def record(_connection, _cursor, statement, *_args):
        statements.append(statement)
    bind = db.get_bind()
    db.expire_all()
    # Resolve the fixture camera before instrumenting; production auth is independent.
    _ = camera.site_id
    event.listen(bind, "before_cursor_execute", record)
    try:
        payload = current(occupancy)
    finally:
        event.remove(bind, "before_cursor_execute", record)
    assert payload["readings"][0]["state"] == "empty"
    assert not any("image_bytes" in sql or "FROM payments" in sql for sql in statements)
    assert "license_plate" not in str(payload)


@pytest.mark.parametrize(("age", "reason"), [(30, "stale_capture"), (300, "stale_capture"), (-1, "future_capture")])
def test_new_receipt_cannot_refresh_old_or_future_capture(occupancy, age, reason):
    _, db, camera, _, _, _, now = occupancy
    config, _, _ = calibration(occupancy)
    result = analyze(occupancy, config, image(db, camera, now, age=age)).json()
    assert result["readings"][0]["state"] == "unknown"
    assert result["readings"][0]["reason"] == reason


@pytest.mark.parametrize("cause", ["reference_delete", "source_delete", "reference_retention", "source_retention", "camera_disabled"])
def test_retention_and_disabled_camera_invalidate_saved_state(occupancy, cause):
    _, db, camera, _, _, _, now = occupancy
    config, reference, _ = calibration(occupancy)
    source = image(db, camera, now)
    assert analyze(occupancy, config, source).json()["readings"][0]["state"] == "empty"
    if cause.endswith("delete"):
        db.delete(reference if cause.startswith("reference") else source)
    elif cause.endswith("retention"):
        target = reference if cause.startswith("reference") else source
        target.observed_at = now - timedelta(hours=2)
        camera.retention_hours = 1
    else:
        camera.is_active = False
    db.commit()
    result = current(occupancy)
    assert result["readings"][0]["state"] == "unknown"
    assert result["readings"][0]["mismatch"] is None
    assert db.scalar(select(func.count()).select_from(OccupancyObservation)) == 1


def test_new_calibration_invalidates_previous_result_and_old_analyze_request(occupancy):
    _, db, camera, _, _, _, now = occupancy
    config, _, body = calibration(occupancy)
    source = image(db, camera, now)
    assert analyze(occupancy, config, source).status_code == 200
    client = occupancy[0]
    endpoint = f"/api/v2/sites/{camera.site_id}/occupancy/calibrations"
    assert client.post(endpoint, json=body).json()["id"] == config["id"]
    changed = {**body, "settings": {"confirmation_frames": 2}}
    assert client.post(endpoint, json=changed).status_code == 409
    changed["request_id"] = str(uuid4())
    assert client.post(endpoint, json=changed).json()["version"] == 2
    assert current(occupancy)["latest"] is None
    assert analyze(occupancy, config, source).status_code == 409


def test_consensus_requires_different_increasing_frames_and_ignores_late_upload(occupancy):
    _, db, camera, _, _, _, now = occupancy
    config, _, _ = calibration(occupancy, confirmations=2)
    first = image(db, camera, now, age=2, vehicle=True)
    assert analyze(occupancy, config, first).json()["readings"][0]["reason"] == "insufficient_history"
    assert analyze(occupancy, config, first).json()["readings"][0]["state"] == "unknown"
    fresh = image(db, camera, now, age=1, vehicle=True)
    result = analyze(occupancy, config, fresh).json()
    assert result["readings"][0]["state"] == "occupied"
    old = image(db, camera, now, age=15)
    assert analyze(occupancy, config, old).json()["latest"]["source_observation_id"] == fresh.id


def test_scope_and_manager_role_are_both_required_for_calibration(occupancy):
    client, db, camera, foreign, user, _, now = occupancy
    config, _, body = calibration(occupancy)
    foreign_result = client.get(f"/api/v2/sites/{foreign.site_id}/occupancy", params={"camera_id": foreign.id})
    assert foreign_result.status_code == 403
    assert client.get(f"/api/v2/sites/{camera.site_id}/occupancy", params={"camera_id": foreign.id}).status_code == 404
    assert analyze(occupancy, config, image(db, foreign, now)).status_code == 404
    user.role.name = "staff"; db.commit()
    assert current(occupancy)["calibration"]["id"] == config["id"]
    assert client.post(f"/api/v2/sites/{camera.site_id}/occupancy/calibrations", json=body).status_code == 403
    assert analyze(occupancy, config, image(db, camera, now)).status_code == 200
    user.role.name = "manager"
    membership = db.scalar(select(SiteMembership).where(SiteMembership.user_id == user.id))
    membership.role = "staff"; db.commit()
    assert client.post(f"/api/v2/sites/{camera.site_id}/occupancy/calibrations", json=body).status_code == 403


def test_cpu_gate_and_post_compute_authorization_recheck(occupancy, monkeypatch):
    client, db, camera, _, user, _, now = occupancy
    config, _, _ = calibration(occupancy)
    source = image(db, camera, now)
    assert _gate.acquire(blocking=False)
    try:
        assert analyze(occupancy, config, source).status_code == 429
    finally:
        _gate.release()
    original = occupancy_engine.analyze
    def revoke(*args):
        assert not db.in_transaction()
        result = original(*args)
        user.is_active = False; db.commit()
        return result
    monkeypatch.setattr(occupancy_engine, "analyze", revoke)
    assert analyze(occupancy, config, source).status_code == 403
    assert db.scalar(select(func.count()).select_from(OccupancyObservation)) == 0


@pytest.mark.parametrize("change", ["reference", "camera", "calibration"])
def test_inference_race_never_saves_an_invalid_snapshot(occupancy, monkeypatch, change):
    _, db, camera, _, _, _, now = occupancy
    config, reference, _ = calibration(occupancy)
    source = image(db, camera, now)
    original = occupancy_engine.analyze
    def mutate(*args):
        assert not db.in_transaction()
        result = original(*args)
        if change == "reference":
            db.delete(reference)
        elif change == "camera":
            camera.is_active = False
        else:
            old = db.get(OccupancyCalibration, config["id"])
            values = {column.name: getattr(old, column.name) for column in old.__table__.columns
                if column.name not in {"id", "version", "request_id"}}
            db.add(OccupancyCalibration(**values, version=2, request_id=str(uuid4())))
        db.commit()
        return result
    monkeypatch.setattr(occupancy_engine, "analyze", mutate)
    assert analyze(occupancy, config, source).status_code == 409
    assert db.scalar(select(func.count()).select_from(OccupancyObservation)) == 0


def test_calibration_cannot_include_a_slot_outside_camera_zone(occupancy, zone, vehicle_type):
    from models.parking_slot import ParkingSlot
    from models.zone import Zone
    client, db, camera, *_ = occupancy
    _, _, body = calibration(occupancy)
    other_zone = Zone(name="Outside camera", capacity=2, site_id=camera.site_id)
    db.add(other_zone); db.flush()
    other_slot = ParkingSlot(zone_id=other_zone.id, vehicle_type_id=vehicle_type.id, slot_name="Outside-1")
    db.add(other_slot); db.commit()
    body["regions"][0]["slot_id"] = other_slot.id
    body["request_id"] = str(uuid4())
    assert client.post(f"/api/v2/sites/{camera.site_id}/occupancy/calibrations", json=body).status_code == 409


def test_consensus_conflict_then_recovery_uses_raw_frames(occupancy):
    _, db, camera, _, _, _, now = occupancy
    config, _, _ = calibration(occupancy, confirmations=2)
    assert analyze(occupancy, config, image(db, camera, now, age=3)).status_code == 200
    result = analyze(occupancy, config, image(db, camera, now, age=2, vehicle=True)).json()
    assert result["readings"][0]["reason"] == "unstable_observations"
    result = analyze(occupancy, config, image(db, camera, now, age=1, vehicle=True)).json()
    assert result["readings"][0]["state"] == "occupied"


def test_calibrated_slot_identity_cannot_be_deleted_and_reused(occupancy):
    from models.parking_slot import ParkingSlot
    from sqlalchemy import delete
    _, db, _, _, _, slot, _ = occupancy
    config, _, _ = calibration(occupancy)
    assert db.get(OccupancyCalibrationSlot, (config["id"], slot.id)) is not None
    with pytest.raises(IntegrityError):
        db.execute(delete(ParkingSlot).where(ParkingSlot.id == slot.id))
        db.commit()
    db.rollback()
    assert db.get(ParkingSlot, slot.id) is not None


@pytest.mark.parametrize("change", ["name", "type"])
def test_changed_slot_mapping_is_unknown_until_recalibrated(occupancy, change):
    from models.vehicle_type import VehicleType
    _, db, camera, _, _, slot, now = occupancy
    config, _, _ = calibration(occupancy)
    assert analyze(occupancy, config, image(db, camera, now)).json()["readings"][0]["state"] == "empty"
    if change == "name":
        slot.slot_name = "New physical label"
    else:
        kind = VehicleType(name="Different type")
        db.add(kind); db.flush()
        slot.vehicle_type_id = kind.id
    db.commit()
    result = current(occupancy)["readings"][0]
    assert result["state"] == "unknown" and result["reason"] == "slot_mapping_changed"
    assert result["mismatch"] is None
