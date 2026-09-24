"""Synthetic OCR evidence tests the gates/transactions, not recognition accuracy."""
from datetime import datetime, timedelta
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from core import clock
from database import get_db
from expansion.site_models import ParkingSite, SiteMembership
from expansion.vision_models import Camera, VisionObservation
from expansion.vision_passage_models import CameraAutomationPolicy, VisionPassageEvent
from expansion.vision_passage_router import router
from expansion.vision_router import router as image_router
from models.parking_session import ParkingSession
from models.payment import Payment
from services.auth_service import get_current_user


@pytest.fixture
def passage(db_session, test_user, parking_slot, vehicle, price_config, business_reference_now, monkeypatch):
    db = db_session
    instant = [business_reference_now]
    class Frozen(datetime):
        @classmethod
        def now(cls, tz=None):
            aware = instant[0].replace(tzinfo=clock.BUSINESS_TZ)
            return aware.astimezone(tz) if tz else instant[0]
    monkeypatch.setattr(clock, "datetime", Frozen)
    test_user.role.name = "manager"
    site, other = ParkingSite(name="Passage test"), ParkingSite(name="Private other")
    db.add_all([site, other]); db.flush()
    parking_slot.zone.site_id = site.id
    db.add(SiteMembership(site_id=site.id, user_id=test_user.id, role="manager"))
    camera = Camera(site_id=site.id, zone_id=parking_slot.zone_id, name="Entry", direction="entry", retention_hours=1)
    foreign = Camera(site_id=other.id, name="Other", direction="exit", retention_hours=1)
    db.add_all([camera, foreign]); db.commit()
    monkeypatch.setenv("PARKING_VISION_ENGINE", "disabled")
    app = FastAPI(); app.include_router(router); app.include_router(image_router)
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_current_user] = lambda: test_user
    with TestClient(app) as client:
        yield dict(client=client, db=db, camera=camera, foreign=foreign, actor=test_user,
                   vehicle=vehicle, slot=parking_slot, rate=price_config, instant=instant, site=site)


def enable(p, **changes):
    body = {"enabled": True, **changes}
    result = p["client"].put(f'/api/v2/cameras/{p["camera"].id}/automation', json=body)
    assert result.status_code == 200, result.text
    p["instant"][0] += timedelta(seconds=1)
    return result.json()


def frame(p, **changes):
    now, vehicle, camera = p["instant"][0], p["vehicle"], p["camera"]
    detection = dict(plate=vehicle.license_plate, confidence=.995, detector_confidence=.999, ocr_confidence=.999, box=[0, 0, 40, 20])
    body = dict(camera_id=camera.id, site_id=camera.site_id, event_id=str(uuid4()), image_hash="a" * 64,
                image_bytes=b"synthetic", image_width=80, image_height=40, observed_at=now,
                captured_at=now, capture_source="live_camera", expires_at=now + timedelta(hours=1), ocr_status="recognized",
                suggested_plate=vehicle.license_plate, confidence=.995, detections=[detection], engine="yolo_rapidocr")
    body.update(changes)
    row = VisionObservation(**body); p["db"].add(row); p["db"].commit()
    return row.id


def process(p, identity):
    return p["client"].post(f"/api/v2/vision/observations/{identity}/process")


def count(p, model):
    return p["db"].scalar(select(func.count()).select_from(model))


def test_defaults_disabled_and_staff_cannot_enable(passage):
    p = passage
    before = p["client"].get(f'/api/v2/cameras/{p["camera"].id}/automation').json()
    assert before["enabled"] is False and before["type_source"] == "registered_vehicle"
    p["actor"].role.name = "staff"; p["db"].commit()
    assert p["client"].put(f'/api/v2/cameras/{p["camera"].id}/automation', json={"enabled": True}).status_code == 403
    result = process(p, frame(p))
    assert result.status_code == 200 and result.json()["state"] == "disabled"
    assert count(p, ParkingSession) == 0


def test_entry_replay_new_frame_and_purge_keep_one_session(passage):
    p = passage; enable(p)
    identity = frame(p)
    first = process(p, identity)
    assert first.status_code == 200, first.text
    assert first.json()["state"] == "entered" and first.json()["type_source"] == "registered_vehicle"
    assert process(p, identity).json() == first.json()
    assert process(p, frame(p)).json()["state"] == "already_entered"
    assert count(p, ParkingSession) == 1
    p["db"].delete(p["db"].get(VisionObservation, identity)); p["db"].commit()
    assert process(p, identity).json() == first.json()
    assert p["db"].scalar(select(VisionPassageEvent).where(VisionPassageEvent.observation_key == identity)).observation_id is None


@pytest.mark.parametrize("change", [
    {"confidence": .89}, {"ocr_status": "unavailable"}, {"engine": "disabled"},
    {"detections": []}, {"review_status": "accepted", "confirmed_plate": "59A-12345"},
    {"suggested_plate": "UNKNOWN"},
    {"capture_source": "manual_upload"},
])
def test_uncertain_evidence_never_admits(passage, change):
    p = passage; enable(p)
    result = process(p, frame(p, **change))
    assert result.status_code == 200 and result.json()["state"] == "manual"
    assert count(p, ParkingSession) == 0 and not p["db"].get(type(p["slot"]), p["slot"].id).is_occupied


def test_unknown_type_multiple_plates_old_and_future_capture_are_manual(passage):
    p = passage; enable(p)
    identity = frame(p)
    row = p["db"].get(VisionObservation, identity)
    row.suggested_plate = "51K-123.45"
    row.detections = [{**row.detections[0], "plate": row.suggested_plate}]
    p["db"].commit()
    assert process(p, identity).json()["state"] == "manual"
    assert process(p, frame(p, captured_at=p["instant"][0] - timedelta(seconds=40))).json()["state"] == "manual"
    assert process(p, frame(p, captured_at=p["instant"][0] + timedelta(seconds=1))).json()["state"] == "manual"
    row = p["db"].get(VisionObservation, frame(p)); row.detections = row.detections * 2; p["db"].commit()
    assert process(p, row.id).json()["state"] == "manual"
    assert count(p, ParkingSession) == 0


def test_policy_changes_camera_direction_and_expiry_fail_closed(passage):
    p = passage; enable(p)
    p["camera"].direction = "exit"; p["db"].commit()
    assert process(p, frame(p)).json()["state"] == "disabled"
    assert p["client"].get(f'/api/v2/cameras/{p["camera"].id}/automation').json()["enabled"] is False
    enable(p)
    expired = frame(p, observed_at=p["instant"][0] - timedelta(hours=2))
    assert process(p, expired).status_code == 404


def test_scope_and_policy_validation(passage):
    p = passage
    assert p["client"].get(f'/api/v2/cameras/{p["foreign"].id}/automation').status_code == 403
    assert p["client"].get('/api/v2/vision/passages', params={"site_id": p["foreign"].site_id}).status_code == 403
    for body in [{"enabled": True, "max_age_seconds": 31}, {"enabled": "yes"}, {"enabled": True, "minimum_confidence": .5}, {"enabled": True, "vehicle_type_id": 1}]:
        assert p["client"].put(f'/api/v2/cameras/{p["camera"].id}/automation', json=body).status_code == 422


def test_unpaid_exit_waits_and_leaves_inventory_and_ledger_unchanged(passage):
    p = passage; enable(p)
    admitted = process(p, frame(p)).json()
    p["camera"].direction = "exit"; p["db"].commit(); enable(p)
    result = process(p, frame(p)).json()
    assert result["state"] == "waiting_payment" and result["session_id"] == admitted["session_id"]
    assert p["db"].get(ParkingSession, admitted["session_id"]).status == "active"
    assert p["db"].get(type(p["slot"]), p["slot"].id).is_occupied
    assert count(p, Payment) == 0


def test_zero_fee_exit_and_outcome_share_one_commit(passage, monkeypatch):
    p = passage; p["rate"].price = 0; p["db"].commit(); enable(p)
    entered = process(p, frame(p)).json()
    p["camera"].direction = "exit"; p["db"].commit(); enable(p)
    identity = frame(p)
    real_commit = p["db"].commit
    commits = []
    def recorded_commit():
        pending = [row for row in p["db"].identity_map.values() if isinstance(row, VisionPassageEvent) and row.observation_key == identity]
        commits.append([row.state for row in pending])
        real_commit()
    monkeypatch.setattr(p["db"], "commit", recorded_commit)
    result = process(p, identity)
    assert result.status_code == 200 and result.json()["state"] == "exited", result.text
    assert commits == [["exited"]]
    session = p["db"].get(ParkingSession, entered["session_id"])
    assert session.status == "completed" and session.parking_fee == 0
    assert not p["db"].get(type(p["slot"]), p["slot"].id).is_occupied
    assert process(p, identity).json()["id"] == result.json()["id"]
    assert count(p, Payment) == 0


def test_admission_rejection_keeps_durable_manual_decision_no_partial_stay(passage):
    p = passage; enable(p)
    p["slot"].is_active = False; p["db"].commit()
    identity = frame(p)
    result = process(p, identity)
    assert result.status_code == 200 and result.json()["state"] == "manual", result.text
    assert count(p, ParkingSession) == 0 and count(p, VisionPassageEvent) == 1
    assert process(p, identity).json()["id"] == result.json()["id"]


def test_manual_outcomes_never_retain_recognized_plate_after_expiry_or_retention_change(passage):
    p = passage; enable(p)
    identity = frame(p, capture_source="manual_upload")
    result = process(p, identity).json()
    assert result["state"] == "manual" and result["license_plate"] is None and result["vehicle_type_id"] is None
    stored = p["db"].scalar(select(VisionPassageEvent).where(VisionPassageEvent.observation_key == identity))
    assert stored.license_plate is None and stored.plate_key is None
    p["instant"][0] += timedelta(hours=2)
    p["client"].patch(f'/api/v2/cameras/{p["camera"].id}', json={"retention_hours": 1})
    listing = p["client"].get('/api/v2/vision/passages', params={"site_id": p["site"].id})
    assert listing.status_code == 200 and listing.json()[0]["license_plate"] is None
    assert p["vehicle"].license_plate not in listing.text


def test_ingress_source_is_assigned_by_endpoint_and_cannot_be_promoted_on_replay(passage):
    import io
    from PIL import Image
    p = passage
    output = io.BytesIO(); Image.new("RGB", (80, 40), "white").save(output, "JPEG")
    event_id = str(uuid4())
    fields = {"camera_id": p["camera"].id, "event_id": event_id}
    file = {"file": ("camera.jpg", output.getvalue(), "image/jpeg")}
    manual = p["client"].post('/api/v2/vision/observations', data=fields, files=file)
    assert manual.status_code == 201 and manual.json()["capture_source"] == "manual_upload"
    assert p["client"].post('/api/v2/vision/live-frames', data=fields, files=file).status_code == 409
    fields["event_id"] = str(uuid4())
    live = p["client"].post('/api/v2/vision/live-frames', data=fields, files=file)
    assert live.status_code == 201 and live.json()["capture_source"] == "live_camera"
    fields["capture_source"] = "edge"
    assert p["client"].post('/api/v2/vision/observations', data=fields, files=file).status_code == 422


def test_concurrent_same_observation_commits_one_event_and_one_admission(passage, tmp_path):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from models.user import User
    from expansion.vision_passage_service import process_observation
    p = passage; enable(p); identity = frame(p)
    actor_id = p["actor"].id
    engine = create_engine("sqlite:///" + (tmp_path / "passage.sqlite").as_posix(), connect_args={"check_same_thread": False, "timeout": 10})
    source, target = p["db"].get_bind().raw_connection(), engine.raw_connection()
    try:
        source.driver_connection.backup(target.driver_connection)
    finally:
        source.close(); target.close()
    factory = sessionmaker(bind=engine)
    barrier = Barrier(2)
    def run():
        with factory() as db:
            actor = db.get(User, actor_id)
            barrier.wait(timeout=5)
            return process_observation(db, actor, identity)
    try:
        with ThreadPoolExecutor(max_workers=2) as executor:
            results = list(executor.map(lambda _: run(), range(2)))
        assert results[0]["id"] == results[1]["id"] and results[0]["state"] == "entered"
        with factory() as db:
            assert db.scalar(select(func.count()).select_from(ParkingSession)) == 1
            assert db.scalar(select(func.count()).select_from(VisionPassageEvent)) == 1
    finally:
        engine.dispose()
