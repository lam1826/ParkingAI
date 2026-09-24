"""Completed automatic decisions release image capacity, not business evidence."""
from datetime import timedelta
from uuid import uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy import func, select

from expansion import vision_service
from expansion.vision_models import VisionObservation
from expansion.vision_passage_models import VisionPassageEvent
from expansion.vision_schemas import ObservationUpload
from models.parking_session import ParkingSession
from models.payment import Payment
from test_vision_passage import enable, frame, passage, process  # noqa: F401


def incoming(p, event_id=None):
    now = p['instant'][0]
    prepared = vision_service.PreparedObservation(
        image_hash='c' * 64, image_bytes=b'new isolated frame', image_width=80, image_height=40,
        captured_at=now, recognition={'ocr_status': 'no_plate', 'engine': 'yolo_rapidocr',
                                    'suggested_plate': None, 'confidence': None, 'detections': []},
    )
    return vision_service.ingest_observation(
        p['db'], p['camera'], ObservationUpload(camera_id=p['camera'].id, event_id=event_id or uuid4()),
        prepared, capture_source='live_camera',
    )


def decided_frame(p, state):
    if state == 'disabled':
        identity = frame(p)
        result = process(p, identity).json()
    else:
        if state == 'exited':
            p['rate'].price = 0
            p['db'].commit()
        enable(p)
        identity = frame(p, **({'confidence': .5} if state == 'manual' else {}))
        result = process(p, identity).json()
        if state in {'already_entered', 'exited', 'waiting_payment'}:
            assert result['state'] == 'entered', result
            p['db'].delete(p['db'].get(VisionObservation, identity))
            p['db'].commit()
            if state in {'exited', 'waiting_payment'}:
                p['camera'].direction = 'exit'
                p['db'].commit()
                enable(p)
            identity = frame(p)
            result = process(p, identity).json()
    assert result['state'] == state, result
    return identity, result


@pytest.mark.parametrize('state', ['entered', 'already_entered', 'exited'])
def test_completed_automation_image_is_evicted_without_losing_event_or_review_queue(passage, monkeypatch, state):
    p = passage
    identity, outcome = decided_frame(p, state)
    db = p['db']
    processed = db.get(VisionObservation, identity)
    assert (processed.review_status, processed.confirmed_plate, processed.reviewed_by_id) == ('pending', None, None)
    p['instant'][0] += timedelta(seconds=61)
    pending_id = frame(p, capture_source='manual_upload')
    # An older reviewed image in another site must never supply this site's quota.
    foreign_id = frame(p, camera_id=p['foreign'].id, site_id=p['foreign'].site_id,
                       observed_at=p['instant'][0] - timedelta(minutes=5), review_status='rejected')
    session_id = outcome['session_id']
    session_state = db.get(ParkingSession, session_id).status
    event_count = db.scalar(select(func.count()).select_from(VisionPassageEvent))
    payment_count = db.scalar(select(func.count()).select_from(Payment))
    monkeypatch.setattr(vision_service, 'MAX_SITE_OBSERVATIONS', 2)

    replacement = incoming(p)

    db.expire_all()
    assert db.get(VisionObservation, identity) is None
    assert db.get(VisionObservation, pending_id).image_bytes == b'synthetic'
    assert db.get(VisionObservation, pending_id).review_status == 'pending'
    assert db.get(VisionObservation, foreign_id) is not None
    assert replacement.review_status == 'pending' and replacement.reviewed_by_id is None
    assert db.scalar(select(func.count()).select_from(VisionObservation).where(VisionObservation.site_id == p['site'].id)) == 2
    event = db.scalar(select(VisionPassageEvent).where(VisionPassageEvent.observation_key == identity))
    assert event.observation_id is None and event.session_id == session_id
    assert process(p, identity).json() == outcome
    assert p['client'].get(f'/api/v2/vision/observations/{identity}/image').status_code == 404
    assert db.get(ParkingSession, session_id).status == session_state
    assert db.scalar(select(func.count()).select_from(ParkingSession)) == 1
    assert db.scalar(select(func.count()).select_from(VisionPassageEvent)) == event_count
    assert db.scalar(select(func.count()).select_from(Payment)) == payment_count


@pytest.mark.parametrize('state', ['unprocessed', 'manual', 'disabled', 'waiting_payment'])
def test_unresolved_automation_image_is_not_evicted_to_make_room(passage, monkeypatch, state):
    p = passage
    if state == 'unprocessed':
        identity, outcome = frame(p), None
    else:
        identity, outcome = decided_frame(p, state)
    monkeypatch.setattr(vision_service, 'MAX_SITE_OBSERVATIONS', 1)
    db = p['db']
    event_count = db.scalar(select(func.count()).select_from(VisionPassageEvent))
    session_count = db.scalar(select(func.count()).select_from(ParkingSession))
    with pytest.raises(HTTPException) as failure:
        incoming(p)
    assert failure.value.status_code == 409
    db.rollback()
    db.expire_all()
    retained = db.get(VisionObservation, identity)
    assert retained.image_bytes == b'synthetic' and retained.review_status == 'pending'
    assert retained.reviewed_by_id is None and retained.confirmed_plate is None
    assert db.scalar(select(func.count()).select_from(VisionObservation)) == 1
    assert db.scalar(select(func.count()).select_from(VisionPassageEvent)) == event_count
    assert db.scalar(select(func.count()).select_from(ParkingSession)) == session_count
    assert db.scalar(select(func.count()).select_from(Payment)) == 0
    if outcome is not None:
        assert process(p, identity).json() == outcome


@pytest.mark.parametrize('age', [59, 60])
def test_recent_completed_frame_still_counts_toward_camera_rate_limit(passage, monkeypatch, age):
    p = passage
    identity, outcome = decided_frame(p, 'entered')
    monkeypatch.setattr(vision_service, 'MAX_SITE_OBSERVATIONS', 1)
    p['instant'][0] += timedelta(seconds=age)
    if age < 60:
        with pytest.raises(HTTPException) as failure:
            incoming(p)
        assert failure.value.status_code == 409
        p['db'].rollback()
        assert p['db'].get(VisionObservation, identity) is not None
    else:
        incoming(p)
        assert p['db'].get(VisionObservation, identity) is None
    assert process(p, identity).json() == outcome


@pytest.mark.parametrize('state', ['entered', 'already_entered', 'exited', 'manual', 'disabled', 'waiting_payment'])
def test_retired_automatic_frame_identity_cannot_be_recreated(passage, state):
    p = passage
    identity, outcome = decided_frame(p, state)
    event_count = p['db'].scalar(select(func.count()).select_from(VisionPassageEvent))
    session_count = p['db'].scalar(select(func.count()).select_from(ParkingSession))
    retired = p['db'].get(VisionObservation, identity)
    event_id = retired.event_id
    p['db'].delete(retired)
    p['db'].commit()

    with pytest.raises(HTTPException) as failure:
        incoming(p, event_id)

    assert failure.value.status_code == 410
    p['db'].rollback()
    assert process(p, identity).json() == outcome
    assert p['db'].scalar(select(func.count()).select_from(VisionObservation)) == 0
    assert p['db'].scalar(select(func.count()).select_from(VisionPassageEvent)) == event_count
    assert p['db'].scalar(select(func.count()).select_from(ParkingSession)) == session_count
    assert p['db'].scalar(select(func.count()).select_from(Payment)) == 0


def test_active_processed_image_keeps_replay_and_payload_conflict_contract(passage):
    p = passage
    identity, outcome = decided_frame(p, 'entered')
    original = p['db'].get(VisionObservation, identity)
    metadata = ObservationUpload(camera_id=p['camera'].id, event_id=original.event_id)
    prepared = vision_service.PreparedObservation(
        image_hash=original.image_hash, image_bytes=original.image_bytes,
        image_width=original.image_width, image_height=original.image_height,
        captured_at=original.captured_at, recognition={},
    )
    replay = vision_service.ingest_observation(p['db'], p['camera'], metadata, prepared, capture_source='live_camera')
    assert replay.id == identity
    assert process(p, identity).json() == outcome
    with pytest.raises(HTTPException) as source_conflict:
        vision_service.ingest_observation(p['db'], p['camera'], metadata, prepared, capture_source='manual_upload')
    assert source_conflict.value.status_code == 409
    with pytest.raises(HTTPException) as image_conflict:
        incoming(p, original.event_id)
    assert image_conflict.value.status_code == 409
    assert p['db'].scalar(select(func.count()).select_from(VisionObservation)) == 1
    assert p['db'].scalar(select(func.count()).select_from(ParkingSession)) == 1


@pytest.mark.parametrize('mismatch', ['camera_id', 'site_id', 'event_id', 'observation_key', 'observation_id', 'session_id'])
def test_unrelated_or_incomplete_terminal_event_cannot_evict_pending_image(passage, monkeypatch, mismatch):
    p = passage
    identity, _ = decided_frame(p, 'entered')
    event = p['db'].scalar(select(VisionPassageEvent).where(VisionPassageEvent.observation_key == identity))
    values = {'camera_id': p['foreign'].id, 'site_id': p['foreign'].site_id,
              'event_id': str(uuid4()), 'observation_key': str(uuid4()),
              'observation_id': None, 'session_id': None}
    setattr(event, mismatch, values[mismatch])
    p['db'].commit()
    p['instant'][0] += timedelta(seconds=61)
    monkeypatch.setattr(vision_service, 'MAX_SITE_OBSERVATIONS', 1)
    with pytest.raises(HTTPException) as failure:
        incoming(p)
    assert failure.value.status_code == 409
    p['db'].rollback()
    retained = p['db'].get(VisionObservation, identity)
    assert retained.image_bytes == b'synthetic' and retained.review_status == 'pending'
