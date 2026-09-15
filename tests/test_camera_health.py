"""Freshness comes from server receipts, with scoped, bounded metadata reads."""
from datetime import timedelta
from uuid import uuid4

import pytest
from sqlalchemy import event, select

from core.clock import business_now
from expansion.vision_models import Camera, VisionObservation
from test_expansion_vision_api import vision, upload  # shared isolated HTTP fixture


def latest(client, camera):
    response = client.get('/api/v2/cameras', params={'site_id': camera.site_id})
    assert response.status_code == 200
    return next(row for row in response.json() if row['id'] == camera.id)


@pytest.mark.parametrize(('age', 'expected'), [(0, 'recent'), (29.9, 'recent'), (30, 'stale'), (3600, 'stale'), (-1, 'stale')])
def test_health_uses_server_time_and_exact_freshness_boundary(vision, monkeypatch, age, expected):
    client, db, camera, _foreign, _user = vision
    now = business_now()
    created = upload(client, camera.id)
    assert created.status_code == 201
    observation = db.get(VisionObservation, created.json()['id'])
    observation.observed_at = now - timedelta(seconds=age)
    # A client-supplied fresh time cannot make a delayed receipt current.
    observation.captured_at = now
    db.commit()
    monkeypatch.setattr('expansion.vision_router.business_now', lambda: now)
    row = latest(client, camera)
    assert row['health'] == expected
    assert row['last_received_at'].endswith('+07:00')
    assert row['health_window_seconds'] == 30


def test_no_retained_image_disabled_and_reenabled_camera_states(vision):
    client, db, camera, _foreign, _user = vision
    assert latest(client, camera)['health'] == 'unseen'
    assert latest(client, camera)['last_received_at'] is None
    assert upload(client, camera.id).status_code == 201
    token = client.post(f'/api/v2/cameras/{camera.id}/edge-token')
    assert token.status_code == 200
    disabled = client.delete(f'/api/v2/cameras/{camera.id}')
    assert disabled.status_code == 200
    assert disabled.json()['health'] == 'disabled'
    assert disabled.json()['last_received_at'] is not None
    assert disabled.json()['edge_enabled'] is False
    resumed = client.patch(f'/api/v2/cameras/{camera.id}', json={'is_active': True})
    assert resumed.status_code == 200
    assert resumed.json()['health'] == 'recent'
    assert resumed.json()['edge_enabled'] is False
    # Retention eviction removes the evidence; it must not invent a heartbeat.
    db.delete(db.scalar(select(VisionObservation).where(VisionObservation.camera_id == camera.id)))
    db.commit()
    assert latest(client, camera)['health'] == 'unseen'


def test_many_cameras_use_one_aggregate_without_images_or_foreign_scope(vision):
    client, db, camera, foreign, _user = vision
    now = business_now()
    for index in range(20):
        extra = Camera(site_id=camera.site_id, name=f'Extra {index}', direction='entry')
        db.add(extra)
        db.flush()
        db.add(VisionObservation(camera_id=extra.id, site_id=extra.site_id,
            event_id=str(uuid4()), image_hash='a' * 64, image_bytes=b'private', image_width=1,
            image_height=1, observed_at=now, captured_at=now, expires_at=now + timedelta(hours=1),
            ocr_status='unavailable', engine='disabled', detections=[]))
    db.commit()
    sql = []
    def record(_connection, _cursor, statement, _parameters, _context, _many):
        if statement.lstrip().upper().startswith('SELECT'):
            sql.append(statement)
    engine = db.get_bind()
    event.listen(engine, 'before_cursor_execute', record)
    try:
        response = client.get('/api/v2/cameras', params={'site_id': camera.site_id})
    finally:
        event.remove(engine, 'before_cursor_execute', record)
    assert response.status_code == 200
    rows = response.json()
    assert len(rows) == 21 and foreign.id not in {row['id'] for row in rows}
    assert sum('FROM vision_observations' in statement for statement in sql) == 1
    assert not any('image_bytes' in statement for statement in sql)
    assert client.get('/api/v2/cameras', params={'site_id': foreign.site_id}).status_code == 403


def test_staff_can_read_freshness_but_cannot_edit_or_rotate(vision):
    client, db, camera, _foreign, user = vision
    user.role.name = 'staff'
    db.commit()
    assert latest(client, camera)['health'] == 'unseen'
    assert client.patch(f'/api/v2/cameras/{camera.id}', json={'name': 'Denied'}).status_code == 403
    assert client.delete(f'/api/v2/cameras/{camera.id}').status_code == 403
    assert client.post(f'/api/v2/cameras/{camera.id}/edge-token').status_code == 403


def test_shorter_retention_immediately_protects_image_review_and_metadata(vision):
    client, db, camera, _foreign, _user = vision
    created = upload(client, camera.id)
    assert created.status_code == 201
    row = db.get(VisionObservation, created.json()['id'])
    now = business_now()
    camera.retention_hours = 24
    row.observed_at = row.captured_at = now - timedelta(hours=2)
    row.expires_at = now + timedelta(hours=22)
    db.commit()
    assert client.get(f'/api/v2/vision/observations/{row.id}/image').status_code == 200
    changed = client.patch(f'/api/v2/cameras/{camera.id}', json={'retention_hours': 1})
    assert changed.status_code == 200
    assert client.get(f'/api/v2/vision/observations/{row.id}/image').status_code == 404
    assert client.post(f'/api/v2/vision/observations/{row.id}/review', json={'decision': 'reject'}).status_code == 404
    listing = client.get('/api/v2/vision/observations', params={'site_id': camera.site_id})
    assert listing.status_code == 200 and listing.json() == []
    # Raising retention later must not resurrect already-expired private data.
    assert client.patch(f'/api/v2/cameras/{camera.id}', json={'retention_hours': 24}).status_code == 200
    assert client.get(f'/api/v2/vision/observations/{row.id}/image').status_code == 404


def test_retention_filter_precedes_pagination_and_reports_effective_expiry(vision):
    client, db, camera, _foreign, _user = vision
    now = business_now()
    long_camera = Camera(site_id=camera.site_id, name='Long retention', direction='entry', retention_hours=24)
    db.add(long_camera)
    db.flush()
    for index, source in enumerate([camera, long_camera]):
        db.add(VisionObservation(camera_id=source.id, site_id=source.site_id, event_id=str(uuid4()),
            image_hash='a' * 64, image_bytes=b'private', image_width=1, image_height=1,
            observed_at=now - timedelta(hours=2 + index), captured_at=now - timedelta(hours=2 + index),
            expires_at=now + timedelta(hours=50), ocr_status='unavailable', engine='disabled', detections=[]))
    db.commit()
    response = client.get('/api/v2/vision/observations', params={'site_id': camera.site_id, 'limit': 1})
    assert response.status_code == 200 and len(response.json()) == 1
    assert response.json()[0]['camera_id'] == long_camera.id
    from datetime import datetime
    effective = datetime.fromisoformat(response.json()[0]['expires_at']).replace(tzinfo=None)
    assert effective == now + timedelta(hours=21)
