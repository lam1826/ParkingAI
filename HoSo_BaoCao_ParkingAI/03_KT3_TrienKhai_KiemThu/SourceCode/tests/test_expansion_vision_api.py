"""Private phone images and manual approval, using isolated fixture DB only."""
import io
from datetime import timedelta
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from PIL import Image
from sqlalchemy import select, update

from core.clock import business_now
from database import get_db
from expansion.site_models import ParkingSite, SiteMembership
from expansion.vision_models import Camera, VisionObservation
from expansion.vision_router import router
from expansion.vision_service import decode_image
from models.parking_session import ParkingSession
from services.auth_service import get_current_user


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
