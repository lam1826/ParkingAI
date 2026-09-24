"""Camera exit consumes real receipt-backed credits; provider transport is offline."""
from datetime import timedelta
from uuid import uuid4

from sqlalchemy import select

from expansion.vision_models import Camera, VisionObservation
from expansion.vision_passage_service import process_observation, update_policy
from expansion.vision_passage_schemas import AutomationPolicyUpdate
from models.parking_session import ParkingSession
from models.payment import Payment
from models.vehicle import Vehicle
from test_session_online_payments import parking_online, online, portal, no_external_payment_configuration, quote, link, settle  # noqa: F401


def test_camera_paid_exit_keeps_one_credit_and_one_zero_balance_receipt(parking_online):
    ctx = parking_online
    settle(ctx, link(ctx, quote(ctx)))
    actor = ctx.users[0]
    camera = Camera(site_id=ctx.site.id, zone_id=ctx.slot.zone_id, name="Paid exit", direction="exit", retention_hours=1)
    ctx.db.add(camera); ctx.db.commit()
    update_policy(ctx.db, actor, camera.id, AutomationPolicyUpdate(enabled=True))
    ctx.clock[0] += timedelta(seconds=1)
    session = ctx.db.get(ParkingSession, ctx.session_id)
    vehicle = ctx.db.get(Vehicle, session.vehicle_id)
    now = ctx.clock[0]
    observation = VisionObservation(camera_id=camera.id, site_id=camera.site_id, event_id=str(uuid4()),
        image_hash="a" * 64, image_bytes=b"synthetic", image_width=80, image_height=40, captured_at=now,
        observed_at=now, expires_at=now + timedelta(hours=1), capture_source="live_camera", ocr_status="recognized",
        engine="yolo_rapidocr", confidence=.995, suggested_plate=vehicle.license_plate,
        detections=[{"plate": vehicle.license_plate, "confidence": .995, "detector_confidence": .999, "ocr_confidence": .999}])
    ctx.db.add(observation); ctx.db.commit()
    result = process_observation(ctx.db, actor, observation.id)
    assert result["state"] == "exited", result
    receipts = list(ctx.db.scalars(select(Payment).order_by(Payment.amount.desc())))
    assert [(row.source_type, row.amount) for row in receipts] == [("session_credit", 10000), ("parking_session", 0)]
    assert ctx.db.get(ParkingSession, ctx.session_id).status == "completed"
    assert process_observation(ctx.db, actor, observation.id)["id"] == result["id"]
    assert len(list(ctx.db.scalars(select(Payment)))) == 2
