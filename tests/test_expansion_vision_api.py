"""Private phone images and manual approval, using isolated fixture DB only."""
import io
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from threading import Event, Lock
from time import monotonic
from uuid import uuid4

import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient
from PIL import Image
from sqlalchemy import create_engine, select, update
from sqlalchemy.orm import sessionmaker

from core.clock import business_now
from database import get_db
from expansion.site_models import ParkingSite, SiteMembership
from expansion.vision_models import Camera, VisionObservation
from expansion.vision_router import router
from expansion.vision_schemas import ObservationUpload
from expansion.vision_service import decode_image
from models.parking_session import ParkingSession
from services.auth_service import AuthService, get_current_user


def picture(fmt="JPEG"):
    output = io.BytesIO()
    Image.new("RGB", (180, 80), "white").save(output, fmt)
    return output.getvalue()


def test_phone_mpo_jpeg_keeps_only_primary_photo_without_metadata():
    # Some iPhones attach a second gain-map image inside an otherwise normal
    # JPEG. The primary photo is safe to accept and canonicalize to one JPEG.
    output = io.BytesIO()
    Image.new("RGB", (180, 80), "white").save(output, "MPO", save_all=True,
        append_images=[Image.new("RGB", (90, 40), "black")])
    primary, encoded = decode_image(output.getvalue(), "image/jpeg")
    assert primary.size == (180, 80)
    stored = Image.open(io.BytesIO(encoded))
    assert stored.format == "JPEG" and getattr(stored, "n_frames", 1) == 1
    assert "exif" not in stored.info and "mp" not in stored.info


@pytest.fixture
def vision(db_session, test_user, zone, monkeypatch):
    monkeypatch.setenv("PARKING_VISION_ENGINE", "disabled")
    test_user.role.name = "manager"
    site = ParkingSite(name="Camera test site")
    other = ParkingSite(name="Other private site")
    db_session.add_all([site, other]); db_session.flush()
    zone.site_id = site.id
    db_session.add(SiteMembership(site_id=site.id, user_id=test_user.id, role="manager"))
    camera = Camera(site_id=site.id, zone_id=zone.id, name="Phone", direction="entry", retention_hours=1)
    foreign = Camera(site_id=other.id, name="Other", direction="exit", retention_hours=1)
    db_session.add_all([camera, foreign]); db_session.commit()
    app = FastAPI(); app.include_router(router)
    app.dependency_overrides[get_db] = lambda: db_session
    app.dependency_overrides[get_current_user] = lambda: test_user
    with TestClient(app) as client:
        yield client, db_session, camera, foreign, test_user


def upload(client, camera_id, content=None, mime="image/jpeg", event_id=None):
    return client.post("/api/v2/vision/observations", data={"camera_id": camera_id, "event_id": event_id or str(uuid4())},
                       files={"file": ("phone.jpg", picture() if content is None else content, mime)})


def test_reviewed_observations_are_evicted_at_the_site_cap(vision, monkeypatch):
    from expansion import vision_service
    from expansion.vision_schemas import ObservationUpload

    _client, db, camera, _foreign, _user = vision
    monkeypatch.setattr(vision_service, "MAX_SITE_OBSERVATIONS", 2)
    now = business_now()
    old_rejected = VisionObservation(
        camera_id=camera.id, site_id=camera.site_id, event_id=str(uuid4()), image_hash="a" * 64,
        image_bytes=b"old", image_width=20, image_height=20, observed_at=now - timedelta(minutes=3),
        captured_at=now - timedelta(minutes=3), expires_at=now + timedelta(hours=1),
        ocr_status="no_plate", engine="disabled", detections=[], review_status="rejected",
    )
    accepted = VisionObservation(
        camera_id=camera.id, site_id=camera.site_id, event_id=str(uuid4()), image_hash="b" * 64,
        image_bytes=b"accepted", image_width=20, image_height=20, observed_at=now - timedelta(minutes=2),
        captured_at=now - timedelta(minutes=2), expires_at=now + timedelta(hours=1),
        ocr_status="recognized", engine="disabled", detections=[], review_status="accepted",
    )
    db.add_all([old_rejected, accepted])
    db.commit()
    old_rejected_id, accepted_id = old_rejected.id, accepted.id
    metadata = ObservationUpload(camera_id=camera.id, event_id=uuid4())
    prepared = vision_service.PreparedObservation(
        image_hash="c" * 64, image_bytes=b"new", image_width=20, image_height=20,
        captured_at=now, recognition={"ocr_status": "unavailable", "engine": "disabled",
        "detections": [], "suggested_plate": None, "confidence": None},
    )

    created = vision_service.ingest_observation(db, camera, metadata, prepared)

    assert created.id is not None
    assert db.get(VisionObservation, old_rejected_id) is None
    assert db.get(VisionObservation, accepted_id) is not None


def test_reduced_camera_retention_applies_to_preexisting_observations(vision):
    from expansion.vision_service import purge_expired

    _client, db, camera, _foreign, _user = vision
    now = business_now()
    row = VisionObservation(
        camera_id=camera.id, site_id=camera.site_id, event_id=str(uuid4()), image_hash="d" * 64,
        image_bytes=b"old", image_width=20, image_height=20, observed_at=now - timedelta(hours=2),
        captured_at=now - timedelta(hours=2), expires_at=now + timedelta(hours=10),
        ocr_status="no_plate", engine="disabled", detections=[], review_status="accepted",
    )
    camera.retention_hours = 1
    db.add(row)
    db.commit()
    row_id = row.id

    assert purge_expired(db, camera.site_id) == 1
    db.commit()
    assert db.get(VisionObservation, row_id) is None


def test_engine_failure_is_logged_and_reported_until_a_success(tmp_path, monkeypatch, caplog):
    from expansion import vision_service

    model = tmp_path / "plate.onnx"
    model.write_bytes(b"placeholder")
    monkeypatch.setenv("PARKING_VISION_ENGINE", "yolo_rapidocr")
    monkeypatch.setenv("PARKING_VISION_MODEL", str(model))
    monkeypatch.setattr(vision_service.importlib.util, "find_spec", lambda _name: object())

    class Engine:
        def recognize(self, _image):
            raise RuntimeError("private model path must stay in logs")

    vision_service._engine = Engine()
    vision_service._engine_path = model.resolve()
    vision_service._last_engine_error = None
    result = vision_service.recognize_image(Image.new("RGB", (100, 50)))
    status = vision_service.model_status()

    assert result["ocr_status"] == "error"
    assert status["available"] is False and status["degraded"] is True
    assert status["last_error"]
    assert "vision_inference_failed" in caplog.text
    assert "private model path" not in caplog.text

    class Recovered:
        def recognize(self, _image):
            return []

    vision_service._engine = Recovered()
    assert vision_service.recognize_image(Image.new("RGB", (100, 50)))["ocr_status"] == "no_plate"
    assert vision_service.model_status()["available"] is True


def test_concurrent_upload_is_rejected_before_entering_processing(vision, monkeypatch):
    import expansion.vision_router as vision_router_module

    client, _, camera, _, _ = vision
    first_entered = Event()
    release_first = Event()
    counter_lock = Lock()
    calls = 0

    async def controlled_upload(_request):
        nonlocal calls
        with counter_lock:
            calls += 1
            current = calls
        if current == 1:
            first_entered.set()
            await vision_router_module.run_in_threadpool(release_first.wait, 5)
        return (
            ObservationUpload(camera_id=camera.id, event_id=str(uuid4())),
            picture(),
            "image/jpeg",
        )

    monkeypatch.setattr(vision_router_module, "_read_upload", controlled_upload)
    try:
        with ThreadPoolExecutor(max_workers=1) as pool:
            first = pool.submit(client.post, "/api/v2/vision/observations")
            assert first_entered.wait(timeout=2)
            started = monotonic()
            overloaded = client.post("/api/v2/vision/observations")
            elapsed = monotonic() - started
            release_first.set()
            accepted = first.result(timeout=5)
        assert accepted.status_code == 201
        assert overloaded.status_code == 429
        assert elapsed < 0.5
        assert calls == 1
    finally:
        release_first.set()


def test_inference_does_not_hold_the_only_database_connection(vision, tmp_path, monkeypatch):
    client, source_db, camera, _, user = vision
    del client
    database_path = tmp_path / "vision-pool.sqlite"
    engine = create_engine(
        "sqlite:///" + database_path.as_posix(),
        connect_args={"timeout": 0.2, "check_same_thread": False},
        pool_size=1,
        max_overflow=0,
        pool_timeout=0.2,
    )
    source = source_db.get_bind().raw_connection()
    target = engine.raw_connection()
    try:
        source.driver_connection.backup(target.driver_connection)
    finally:
        source.close()
        target.close()
    factory = sessionmaker(bind=engine, expire_on_commit=False)

    def request_db():
        with factory() as db:
            yield db

    inference_started = Event()
    release_inference = Event()

    def slow_recognition(_image):
        inference_started.set()
        release_inference.wait(timeout=5)
        return {
            "ocr_status": "unavailable",
            "engine": "disabled",
            "detections": [],
            "suggested_plate": None,
            "confidence": None,
        }

    monkeypatch.setattr("expansion.vision_service.recognize_image", slow_recognition)
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_db] = request_db

    @app.get("/ready")
    def ready(db=Depends(get_db)):
        db.scalar(select(1))
        return {"status": "ready"}

    token = AuthService().create_access_token(
        user_id=user.id,
        username=user.username,
        role=user.role.name,
    )
    headers = {"Authorization": f"Bearer {token}"}
    try:
        with TestClient(app, raise_server_exceptions=False) as isolated, ThreadPoolExecutor(max_workers=1) as pool:
            upload_future = pool.submit(
                isolated.post,
                "/api/v2/vision/observations",
                headers=headers,
                data={"camera_id": camera.id, "event_id": str(uuid4())},
                files={"file": ("phone.jpg", picture(), "image/jpeg")},
            )
            assert inference_started.wait(timeout=2)
            started = monotonic()
            readiness = isolated.get("/ready")
            elapsed = monotonic() - started
            release_inference.set()
            uploaded = upload_future.result(timeout=5)
        assert readiness.status_code == 200
        assert readiness.json() == {"status": "ready"}
        assert elapsed < 0.2
        assert uploaded.status_code == 201
    finally:
        release_inference.set()
        engine.dispose()


def test_phone_upload_disabled_model_is_honest_and_review_never_moves_a_vehicle(vision):
    client, db, camera, _, _ = vision
    response = upload(client, camera.id)
    assert response.status_code == 201, response.text
    data = response.json()
    assert data["ocr_status"] == "unavailable" and data["suggested_plate"] is None
    assert data["next_action"] is None
    confirmed = client.post(f'/api/v2/vision/observations/{data["id"]}/review', json={"decision": "accept", "license_plate": "30A-123.45"})
    assert confirmed.status_code == 200, confirmed.text
    assert confirmed.json()["next_action"]["kind"] == "check_in"
    assert not db.scalars(select(ParkingSession)).all()
    image = client.get(data["image_url"])
    assert image.status_code == 200 and image.headers["cache-control"] == "no-store"
    assert Image.open(io.BytesIO(image.content)).format == "JPEG"


@pytest.mark.parametrize("content,mime,status", [(b"<svg></svg>", "image/svg+xml", 415), (b"invalid", "image/jpeg", 422),
    (picture("PNG"), "image/jpeg", 422), (b"x" * (2 * 1024 * 1024 + 1), "image/jpeg", 413)],
    ids=["unsupported-svg", "invalid-image", "mime-mismatch", "oversized"])
def test_untrusted_upload_is_bounded_and_decoded(vision, content, mime, status):
    client, db, camera, _, _ = vision
    assert upload(client, camera.id, content, mime).status_code == status
    assert not db.scalars(select(VisionObservation)).all()


def test_cross_site_camera_image_and_list_are_denied(vision):
    client, db, camera, foreign, user = vision
    assert upload(client, foreign.id).status_code == 403
    assert client.get("/api/v2/cameras", params={"site_id": foreign.site_id}).status_code == 403
    data = upload(client, camera.id).json()
    db.query(SiteMembership).filter_by(user_id=user.id).delete(); db.commit()
    # Object-level reads of an observation outside the caller's sites answer 404 (not 403) so the
    # response cannot confirm that a foreign identifier exists; site-level listings still return 403.
    assert client.get(data["image_url"]).status_code == 404
    assert client.get("/api/v2/vision/observations", params={"site_id": camera.site_id}).status_code == 403


def test_event_idempotency_conflict_expiry_and_terminal_review(vision):
    client, db, camera, _, _ = vision
    event = str(uuid4()); first = upload(client, camera.id, event_id=event).json()
    assert upload(client, camera.id, event_id=event).json()["id"] == first["id"]
    assert upload(client, camera.id, content=picture("PNG"), mime="image/png", event_id=event).status_code == 409
    url = f'/api/v2/vision/observations/{first["id"]}/review'
    assert client.post(url, json={"decision": "accept"}).status_code == 422
    assert client.post(url, json={"decision": "reject"}).status_code == 200
    assert client.post(url, json={"decision": "accept", "license_plate": "30A-12345"}).status_code == 409
    observation = db.get(VisionObservation, first["id"]); observation.expires_at = business_now() - timedelta(seconds=1); db.commit()
    assert client.get(first["image_url"]).status_code == 404
    assert client.get("/api/v2/vision/observations", params={"site_id": camera.site_id}).json() == []
    assert client.post("/api/v2/vision/purge-expired", params={"site_id": camera.site_id}).json() == {"removed": 1}


def test_edge_token_is_camera_scoped_and_revocation_takes_effect(vision):
    client, db, camera, foreign, _ = vision
    token = client.post(f"/api/v2/cameras/{camera.id}/edge-token").json()["token"]
    response = client.post("/api/v2/vision/edge-events", headers={"X-Camera-Token": token}, data={"camera_id": camera.id}, files={"file": ("x.jpg", picture(), "image/jpeg")})
    assert response.status_code == 201, response.text
    assert set(response.json()) == {"id", "event_id", "received"}
    wrong = client.post("/api/v2/vision/edge-events", headers={"X-Camera-Token": token}, data={"camera_id": foreign.id}, files={"file": ("x.jpg", picture(), "image/jpeg")})
    assert wrong.status_code == 401
    assert client.delete(f"/api/v2/cameras/{camera.id}").status_code == 200
    revoked = client.post("/api/v2/vision/edge-events", headers={"X-Camera-Token": token}, data={"camera_id": camera.id}, files={"file": ("x.jpg", picture(), "image/jpeg")})
    assert revoked.status_code == 401
    assert token not in str(client.get("/api/v2/cameras", params={"site_id": camera.site_id}).json())


def test_stale_review_cannot_overwrite_another_staff_decision(vision, monkeypatch):
    import expansion.vision_router as module
    client, db, camera, _, user = vision
    uploaded = upload(client, camera.id).json()
    original = module._observation
    def stale_read(*args, **kwargs):
        observation = original(*args, **kwargs)
        assert observation.review_status == "pending"
        # Emulate a competing committed decision between read and update.
        db.execute(update(VisionObservation).where(VisionObservation.id == observation.id).values(
            review_status="accepted", confirmed_plate="30A-456.78", reviewed_by_id=user.id,
            reviewed_at=business_now()).execution_options(synchronize_session=False))
        return observation
    monkeypatch.setattr(module, "_observation", stale_read)
    result = client.post(f'/api/v2/vision/observations/{uploaded["id"]}/review', json={"decision": "reject"})
    assert result.status_code == 409, result.text
    db.expire_all()
    assert db.get(VisionObservation, uploaded["id"]).confirmed_plate == "30A-456.78"
