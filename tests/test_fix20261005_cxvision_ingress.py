"""Unreadable camera queues and anonymous edge upload admission regressions."""
import asyncio
import hashlib
from datetime import timedelta
from uuid import uuid4

import pytest
from fastapi import FastAPI, HTTPException
from sqlalchemy import func, select
from starlette.requests import Request

from expansion import vision_router, vision_service
from expansion.vision_models import Camera, VisionObservation
from expansion.vision_schemas import ObservationUpload
from database import get_db
from test_vision_passage import passage  # noqa: F401


def receive(p, status, source="live_camera", camera=None, event_id=None):
    camera = camera or p["camera"]
    metadata = ObservationUpload(camera_id=camera.id, event_id=event_id or uuid4())
    prepared = vision_service.PreparedObservation(image_hash="d" * 64, image_bytes=b"evidence",
        image_width=80, image_height=40, captured_at=p["instant"][0], recognition={
            "ocr_status": status, "engine": "disabled", "suggested_plate": None,
            "confidence": None, "detections": []})
    return vision_service.ingest_observation(p["db"], camera, metadata, prepared, capture_source=source)


@pytest.mark.parametrize("source", ["live_camera", "edge"])
@pytest.mark.parametrize("status", ["unavailable", "error", "no_plate"])
def test_all_unreadable_statuses_pause_per_camera_and_review_reopens(passage, source, status):
    p = passage
    rows = []
    for i in range(20):
        rows.append(receive(p, ["no_plate", "unavailable", "error"][i % 3], source))
        p["instant"][0] += timedelta(seconds=4)
    with pytest.raises(HTTPException) as paused:
        receive(p, status, source)
    assert paused.value.status_code == 409
    assert paused.value.detail["code"] == "camera_review_required"
    p["db"].rollback()
    assert p["db"].scalar(select(func.count()).select_from(VisionObservation)) == 20
    assert all(p["db"].get(VisionObservation, row.id).image_bytes == b"evidence" for row in rows)
    assert receive(p, rows[0].ocr_status, source, event_id=rows[0].event_id).id == rows[0].id
    other = Camera(site_id=p["site"].id, name="Other camera", direction="exit")
    p["db"].add(other); p["db"].commit()
    assert receive(p, status, source, camera=other).camera_id == other.id
    assert receive(p, status, "manual_upload").capture_source == "manual_upload"
    assert p["client"].post(f"/api/v2/vision/observations/{rows[0].id}/review",
                            json={"decision": "reject"}).status_code == 200
    assert receive(p, status, source).id not in {row.id for row in rows}


def test_invalid_edge_token_precedes_upload_slot_and_body(passage, monkeypatch):
    p = passage
    gate_calls = []
    class Gate:
        def acquire(self, **kwargs):
            gate_calls.append("acquire")
            return False
        def release(self):
            gate_calls.append("release")
    monkeypatch.setattr(vision_router, "_upload_gate", Gate())
    body_reads = []
    async def receive_body():
        body_reads.append("read")
        raise AssertionError("unauthenticated body was read")
    request = Request({"type": "http", "method": "POST", "path": "/api/v2/vision/edge-events",
                       "headers": [(b"x-camera-token", b"A" * 32)]}, receive_body)
    async def attempt():
        # Drive dependency order through ASGI with a body that cannot be read.
        app = FastAPI(); app.include_router(vision_router.router)
        app.dependency_overrides[get_db] = lambda: p["db"]
        messages = []
        async def send(message):
            messages.append(message)
        scope = dict(request.scope, scheme="http", query_string=b"", server=("test", 80),
                     client=("test", 1), http_version="1.1", root_path="")
        await app(scope, receive_body, send)
        assert next(m["status"] for m in messages if m["type"] == "http.response.start") == 401
    asyncio.run(attempt())
    assert body_reads == [] and gate_calls == []


def test_edge_token_is_bound_to_body_camera(passage):
    import io
    from PIL import Image
    p = passage
    token = "E" * 43
    p["camera"].edge_token_hash = hashlib.sha256(token.encode()).hexdigest()
    p["db"].commit()
    out = io.BytesIO(); Image.new("RGB", (80, 40), "white").save(out, "JPEG")
    response = p["client"].post("/api/v2/vision/edge-events", headers={"X-Camera-Token": token},
        data={"camera_id": p["foreign"].id, "event_id": str(uuid4())},
        files={"file": ("frame.jpg", out.getvalue(), "image/jpeg")})
    assert response.status_code == 401
    assert p["db"].scalar(select(func.count()).select_from(VisionObservation)) == 0


def test_valid_edge_upload_releases_slot_after_bad_body(passage):
    p = passage
    token = "E" * 43
    p["camera"].edge_token_hash = hashlib.sha256(token.encode()).hexdigest()
    p["db"].commit()
    response = p["client"].post("/api/v2/vision/edge-events", headers={
        "X-Camera-Token": token, "Content-Type": "multipart/form-data; boundary=x"}, content=b"invalid")
    assert response.status_code == 422
    assert vision_router._upload_gate.acquire(blocking=False)
    vision_router._upload_gate.release()


def test_disconnected_upload_returns_client_error():
    async def receive_body():
        return {"type": "http.disconnect"}
    request = Request({"type": "http", "headers": []}, receive_body)
    async def attempt():
        with pytest.raises(HTTPException) as rejected:
            await vision_router._read_upload(request)
        assert rejected.value.status_code == 400
    asyncio.run(attempt())


def test_stalled_upload_has_total_time_bound(monkeypatch):
    timeout = asyncio.timeout
    limits = []
    def short_timeout(seconds):
        limits.append(seconds)
        return timeout(.01)
    monkeypatch.setattr(vision_router.asyncio, "timeout", short_timeout)
    async def receive_body():
        await asyncio.Event().wait()
    request = Request({"type": "http", "headers": []}, receive_body)
    async def attempt():
        with pytest.raises(HTTPException) as rejected:
            await vision_router._read_upload(request)
        assert rejected.value.status_code == 408
    asyncio.run(attempt())
    assert limits == [30]
