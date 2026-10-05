"""Future clock captures cannot poison occupancy latest/history/idempotency."""
from datetime import timedelta

from sqlalchemy import func, select

from expansion import occupancy_engine, occupancy_service
from expansion.occupancy_models import OccupancyObservation
from test_occupancy_api import occupancy, image, calibration, analyze, current  # noqa: F401


def test_future_analysis_rejected_without_cache_then_recomputable(occupancy, monkeypatch):
    _, db, camera, _, _, _, now = occupancy
    config, _, _ = calibration(occupancy)
    future = image(db, camera, now, age=-4, vehicle=True)
    response = analyze(occupancy, config, future)
    assert response.status_code == 409
    assert db.scalar(select(func.count()).select_from(OccupancyObservation)) == 0
    good = image(db, camera, now, age=1, vehicle=True)
    assert analyze(occupancy, config, good).json()["latest"]["source_observation_id"] == good.id
    monkeypatch.setattr(occupancy_service, "business_now", lambda: now + timedelta(seconds=5))
    result = analyze(occupancy, config, future)
    assert result.status_code == 200, result.text
    assert result.json()["readings"][0]["state"] == "occupied"
    assert db.scalar(select(func.count()).select_from(OccupancyObservation)) == 2


def test_legacy_future_result_never_hides_valid_analysis_or_consensus(occupancy, monkeypatch):
    _, db, camera, _, user, _, now = occupancy
    config, _, _ = calibration(occupancy, confirmations=2)
    future = image(db, camera, now, age=-4, vehicle=True)
    regions = config["regions"]
    invalid = occupancy_engine.unknown(regions, "future_capture")
    db.add(OccupancyObservation(calibration_id=config["id"], source_observation_id=future.id,
        source_id_snapshot=future.id, source_image_hash=future.image_hash,
        measured_at=future.captured_at, received_at=now, expires_at=future.expires_at,
        analyzed_by_id=user.id, quality=invalid["quality"], readings=invalid["readings"]))
    db.commit()
    first = image(db, camera, now, age=2, vehicle=True)
    assert analyze(occupancy, config, first).json()["latest"]["source_observation_id"] == first.id
    second = image(db, camera, now, age=1, vehicle=True)
    assert analyze(occupancy, config, second).json()["readings"][0]["state"] == "occupied"
    monkeypatch.setattr(occupancy_service, "business_now", lambda: now + timedelta(seconds=5))
    assert current(occupancy)["latest"]["source_observation_id"] == second.id
    recomputed = analyze(occupancy, config, future)
    assert recomputed.status_code == 200, recomputed.text
    assert recomputed.json()["readings"][0]["state"] == "occupied"
    assert db.scalar(select(func.count()).select_from(OccupancyObservation).where(
        OccupancyObservation.source_id_snapshot == future.id)) == 1
