"""Unreadable live feeds pause without deleting possible missed-plate evidence."""
from dataclasses import replace
from datetime import timedelta
from uuid import uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy import func, select

from expansion import vision_service
from expansion.vision_models import VisionObservation
from expansion.vision_schemas import ObservationUpload
from models.parking_session import ParkingSession
from models.payment import Payment
from test_vision_passage import passage, enable, process  # noqa: F401


def receive(p, *, source="live_camera", camera=None, event_id=None, recognized=False):
    now = p["instant"][0]
    prepared = vision_service.PreparedObservation(
        image_hash="d" * 64, image_bytes=b"possible missed plate", image_width=80, image_height=40,
        captured_at=now, recognition={"ocr_status": "no_plate", "engine": "yolo_rapidocr",
            "suggested_plate": None, "confidence": None, "detections": []},
    )
    if recognized:
        plate = p["vehicle"].license_plate
        prepared = replace(prepared, recognition={"ocr_status": "recognized", "engine": "yolo_rapidocr",
            "suggested_plate": plate, "confidence": .995,
            "detections": [{"plate": plate, "confidence": .995, "detector_confidence": .999, "ocr_confidence": .999}]})
    camera = camera or p["camera"]
    return vision_service.ingest_observation(p["db"], camera,
        ObservationUpload(camera_id=camera.id, event_id=event_id or uuid4()), prepared, capture_source=source)


@pytest.mark.parametrize("source", ["live_camera", "edge"])
def test_idle_camera_backpressure_preserves_all_evidence_and_review_reopens_capture(passage, source):
    p = passage
    enable(p)
    retained = []
    # Production thresholds, not a lowered site cap. Each frame could be an OCR miss.
    for _ in range(20):
        row = receive(p, source=source)
        retained.append((row.id, row.event_id))
        assert process(p, row.id).json()["state"] == "manual"
        p["instant"][0] += timedelta(seconds=4)
    with pytest.raises(HTTPException) as paused:
        receive(p, source=source)
    assert paused.value.status_code == 409
    assert paused.value.detail["code"] == "camera_review_required"
    p["db"].rollback()
    assert p["db"].scalar(select(func.count()).select_from(VisionObservation)) == 20
    for identity, event_id in retained:
        row = p["db"].get(VisionObservation, identity)
        assert row.image_bytes == b"possible missed plate" and row.review_status == "pending"
        assert receive(p, source=source, event_id=event_id).id == identity
    assert p["db"].scalar(select(func.count()).select_from(ParkingSession)) == 0
    assert p["db"].scalar(select(func.count()).select_from(Payment)) == 0
    reviewed = p["client"].post(f"/api/v2/vision/observations/{retained[0][0]}/review", json={"decision": "reject"})
    assert reviewed.status_code == 200, reviewed.text
    resumed = receive(p, source=source)
    assert resumed.id not in {identity for identity, _ in retained}
    assert p["db"].get(VisionObservation, retained[0][0]) is not None


def test_noisy_backlog_does_not_block_recognized_manual_or_other_camera(passage):
    from expansion.vision_models import Camera
    p = passage
    enable(p)
    other = Camera(site_id=p["site"].id, name="Second lane", direction="entry", retention_hours=1)
    p["db"].add(other)
    p["db"].commit()
    for _ in range(20):
        receive(p)
        p["instant"][0] += timedelta(seconds=4)
    assert receive(p, source="manual_upload").capture_source == "manual_upload"
    assert receive(p, camera=other).camera_id == other.id
    recognized = receive(p, recognized=True)
    result = process(p, recognized.id)
    assert result.status_code == 200 and result.json()["state"] == "entered", result.text
    assert p["db"].scalar(select(func.count()).select_from(VisionObservation)) == 23


def test_manual_no_plate_images_do_not_consume_live_backpressure_budget(passage):
    p = passage
    for _ in range(20):
        receive(p, source="manual_upload")
        p["instant"][0] += timedelta(seconds=4)
    assert receive(p).capture_source == "live_camera"
