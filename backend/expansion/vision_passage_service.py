"""Authenticated operator automation. OCR is evidence, never a vehicle classifier.

Each observation has one durable outcome. Successful admission/departure and its
outcome commit together; uncertain/unpaid events stay in the manual queue.
"""
import math
import re
from datetime import timedelta

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import defer

from core.clock import BUSINESS_TZ, business_now
from expansion.site_models import ParkingSite
from expansion.site_scope import require_site_access
from expansion.vision_models import Camera, VisionObservation
from expansion.vision_passage_models import CameraAutomationPolicy, VisionPassageEvent
from models.parking_session import ParkingSession
from models.parking_slot import ParkingSlot
from models.vehicle import Vehicle
from models.vehicle_type import VehicleType
from models.zone import Zone
from schemas.checkout import CheckoutConfirmation
from services.checkout_service import CheckoutService
from services.parking_service import ParkingService
from services.payment_service import lock_cash_operator


def plate_key(value):
    return re.sub(r"[ .-]", "", str(value or "").strip().upper())


def stamp(value):
    return value.replace(tzinfo=BUSINESS_TZ).isoformat() if value else None


def camera_for(db, actor, camera_id, *, manage=False, lock=False):
    camera = db.get(Camera, camera_id)
    if camera is None:
        raise HTTPException(404, "Không tìm thấy camera.")
    require_site_access(db, actor, camera.site_id, minimum_role="manager" if manage else "staff")
    if lock:
        # Same scope-before-camera order as observation ingestion. KEY SHARE
        # avoids blocking unrelated updates of the site's descriptive fields.
        db.scalar(select(ParkingSite).where(ParkingSite.id == camera.site_id).with_for_update(read=True, key_share=True))
        camera = db.scalar(select(Camera).where(Camera.id == camera_id).with_for_update().execution_options(populate_existing=True))
    return camera


def policy_view(camera, policy):
    consistent = policy is not None and policy.direction == camera.direction and policy.zone_id == camera.zone_id
    return {"camera_id": camera.id, "enabled": bool(policy and policy.enabled and camera.is_active and consistent),
            "minimum_confidence": policy.minimum_confidence if policy else 0.97,
            "max_age_seconds": policy.max_age_seconds if policy else 15,
            "direction": camera.direction, "type_source": "registered_vehicle",
            "updated_at": stamp(policy.updated_at) if policy else None,
            "enabled_at": stamp(policy.enabled_at) if policy else None,
            "requires_operator_workspace": True,
            "reason": "Chỉ dùng loại xe từ hồ sơ phương tiện đã có; xe lạ cần kiểm tra thủ công." if consistent or policy is None else "Hướng hoặc khu camera đã đổi. Quản lý cần bật lại quy tắc."}


def update_policy(db, actor, camera_id, body):
    lock_cash_operator(db, actor.id)
    camera = camera_for(db, actor, camera_id, manage=True, lock=True)
    if body.enabled and not camera.is_active:
        raise HTTPException(409, "Camera đang ngừng hoạt động.")
    now = business_now()
    policy = db.get(CameraAutomationPolicy, camera.id)
    if policy is None:
        policy = CameraAutomationPolicy(camera_id=camera.id)
        db.add(policy)
    policy.enabled = body.enabled
    policy.minimum_confidence = body.minimum_confidence
    policy.max_age_seconds = body.max_age_seconds
    policy.direction, policy.zone_id = camera.direction, camera.zone_id
    policy.updated_at, policy.updated_by_id = now, actor.id
    policy.enabled_at = now if body.enabled else None
    db.commit()
    return policy_view(camera, policy)


def event_view(event):
    return {"id": event.id, "camera_id": event.camera_id, "site_id": event.site_id,
            "observation_id": event.observation_key, "event_id": event.event_id,
            "direction": event.direction, "state": event.state, "license_plate": event.license_plate,
            "vehicle_type_id": event.vehicle_type_id, "type_source": "registered_vehicle" if event.vehicle_type_id else None,
            "session_id": event.session_id, "reason": event.reason,
            "captured_at": stamp(event.captured_at), "processed_at": stamp(event.processed_at)}


def _existing(db, actor, observation_id):
    event = db.scalar(select(VisionPassageEvent).where(VisionPassageEvent.observation_key == observation_id))
    if event is not None:
        _private_access(db, actor, event.site_id)
    return event


def _private_access(db, actor, site_id):
    try:
        require_site_access(db, actor, site_id)
    except HTTPException as failure:
        if failure.status_code in {403, 404}:
            raise HTTPException(404, "Ảnh không tồn tại hoặc đã hết thời hạn lưu.") from None
        raise


def _recognition_reason(observation, camera, policy, now):
    if not policy_view(camera, policy)["enabled"]:
        return "disabled", "Tự động chưa bật hoặc cấu hình camera đã thay đổi."
    if observation.review_status != "pending":
        return "manual", "Ảnh đã được nhân viên xử lý; tiếp tục theo thao tác thủ công."
    if observation.capture_source not in {"live_camera", "edge"}:
        return "manual", "Ảnh tải lên cần nhân viên kiểm tra; thời gian tải không chứng minh ảnh vừa được chụp."
    age = (now - observation.captured_at).total_seconds()
    if not 0 <= age <= policy.max_age_seconds or observation.captured_at < policy.enabled_at:
        return "manual", "Ảnh không còn mới hoặc được chụp trước lúc bật tự động."
    if observation.ocr_status != "recognized" or observation.engine != "yolo_rapidocr":
        return "manual", "Chưa có kết quả nhận diện biển số đủ điều kiện."
    detections = observation.detections or []
    if len(detections) != 1 or not isinstance(detections[0], dict):
        return "manual", "Ảnh phải có đúng một biển số; cần kiểm tra ảnh có nhiều xe."
    candidate = detections[0]
    key = plate_key(observation.suggested_plate)
    if not re.fullmatch(r"[0-9]{2}[A-Z][A-Z0-9]{0,2}[0-9]{4,6}", key) or plate_key(candidate.get("plate")) != key:
        return "manual", "Biển số không nhất quán hoặc chưa đúng định dạng."
    for score in (observation.confidence, candidate.get("confidence"), candidate.get("detector_confidence"), candidate.get("ocr_confidence")):
        if isinstance(score, bool) or not isinstance(score, (int, float)) or not math.isfinite(score) or not policy.minimum_confidence <= score <= 1:
            return "manual", "Điểm nhận diện chưa đạt ngưỡng. Nhân viên cần kiểm tra."
    return None


def _registered_vehicle(db, key):
    normalized = func.replace(func.replace(func.replace(func.upper(Vehicle.license_plate), " ", ""), ".", ""), "-", "")
    matches = list(db.scalars(select(Vehicle).where(normalized == key).limit(2)))
    if len(matches) != 1:
        return None
    vehicle = matches[0]
    type_row = db.get(VehicleType, vehicle.vehicle_type_id)
    return vehicle if type_row and type_row.is_active and type_row.requires_plate else None


def _decide(db, actor, camera, observation, policy, event):
    now = business_now()
    blocked = _recognition_reason(observation, camera, policy, now)
    if blocked:
        event.state, event.reason = blocked
        return
    vehicle = _registered_vehicle(db, event.plate_key)
    if vehicle is None:
        event.reason = "Chưa xác định được loại xe từ hồ sơ đang sử dụng. Hãy chọn loại xe và nhận thủ công."
        return
    event.vehicle_type_id = vehicle.vehicle_type_id
    if camera.zone_id is not None:
        zone = db.get(Zone, camera.zone_id)
        if zone is None or not zone.is_active or zone.site_id != camera.site_id:
            event.reason = "Khu của camera không còn hoạt động tại bãi này."
            return
    active = list(db.scalars(select(ParkingSession).where(ParkingSession.vehicle_id == vehicle.id,
        ParkingSession.status.in_(["active", "checking_out"])).limit(2)))
    if camera.direction == "entry":
        if active:
            current = active[0]
            slot = db.get(ParkingSlot, current.parking_slot_id) if current.parking_slot_id else None
            zone = db.get(Zone, slot.zone_id) if slot else None
            if len(active) == 1 and current.status == "active" and zone and zone.site_id == camera.site_id:
                event.state, event.session_id = "already_entered", current.id
                event.reason = "Xe đã có lượt đang gửi tại bãi; không tạo lượt trùng."
            else:
                event.reason = "Xe đang được xử lý hoặc đang gửi tại bãi khác."
            return
        recent_exit = db.scalar(select(ParkingSession.id).where(ParkingSession.vehicle_id == vehicle.id,
            ParkingSession.status == "completed", ParkingSession.check_out_time >= now - timedelta(seconds=30)))
        if recent_exit:
            event.reason = "Xe vừa ra bãi. Cần kiểm tra trước khi tạo lượt mới để tránh ảnh lặp."
            return
        admitted = ParkingService(db).check_in(vehicle.license_plate, vehicle.vehicle_type_id, actor.id,
            zone_id=camera.zone_id, _expected_site_id=camera.site_id, _commit=False)
        event.state, event.session_id = "entered", admitted["session_id"]
        event.reason = "Đã nhận xe; loại xe lấy từ hồ sơ phương tiện."
    else:
        if len(active) != 1 or active[0].status != "active":
            event.reason = "Không có đúng một lượt đang gửi để xác nhận xe ra."
            return
        current = active[0]
        slot = db.get(ParkingSlot, current.parking_slot_id) if current.parking_slot_id else None
        zone = db.get(Zone, slot.zone_id) if slot else None
        if not zone or zone.site_id != camera.site_id or (camera.zone_id is not None and zone.id != camera.zone_id):
            event.reason = "Lượt gửi không thuộc bãi hoặc khu camera này."
            return
        if observation.captured_at < current.check_in_time:
            event.reason = "Ảnh được chụp trước lượt gửi hiện tại."
            return
        event.session_id = current.id
        checkout = CheckoutService(db)
        quote = checkout.quote(current.id, actor.id)
        if quote["balance_due"] != 0:
            event.state = "waiting_payment"
            event.reason = "Xe còn phí cần thanh toán. Dùng tiền mặt hoặc QR rồi kiểm tra lại lúc xe ra."
            return
        checkout.confirm(CheckoutConfirmation(quote_token=quote["quote_token"], payment_confirmed=True,
            payment_method=None), actor.id, session_id=current.id, _commit=False)
        event.state = "exited"
        event.reason = "Đã ghi nhận xe ra sau khi máy chủ xác nhận không còn tiền cần thu."


def process_observation(db, actor, observation_id):
    old = _existing(db, actor, observation_id)
    if old is not None:
        return event_view(old)
    observation = db.scalar(select(VisionObservation).options(defer(VisionObservation.image_bytes, raiseload=True)).where(VisionObservation.id == observation_id))
    if observation is None:
        raise HTTPException(404, "Ảnh không tồn tại hoặc đã hết thời hạn lưu.")
    camera_id = observation.camera_id
    _private_access(db, actor, observation.site_id)
    lock_cash_operator(db, actor.id)
    camera = camera_for(db, actor, camera_id, lock=True)
    # Camera row serializes different staff processing the same frame on PG;
    # the operator no-op write already serializes SQLite writers.
    old = _existing(db, actor, observation_id)
    if old is not None:
        db.rollback()
        return event_view(old)
    observation = db.scalar(select(VisionObservation).options(defer(VisionObservation.image_bytes, raiseload=True))
        .where(VisionObservation.id == observation_id).with_for_update().execution_options(populate_existing=True))
    now = business_now()
    if observation is None or min(observation.expires_at, observation.observed_at + timedelta(hours=camera.retention_hours)) <= now:
        raise HTTPException(404, "Ảnh không tồn tại hoặc đã hết thời hạn lưu.")
    policy = db.get(CameraAutomationPolicy, camera.id)
    fields = dict(camera_id=camera.id, site_id=camera.site_id, observation_id=observation.id,
        observation_key=observation.id, event_id=observation.event_id, direction=camera.direction,
        state="manual", license_plate=observation.suggested_plate, plate_key=plate_key(observation.suggested_plate) or None,
        reason="Cần nhân viên kiểm tra.", actor_id=actor.id, captured_at=observation.captured_at, processed_at=now)
    event = VisionPassageEvent(**fields)
    db.add(event)
    try:
        db.flush()
        _decide(db, actor, camera, observation, policy, event)
        if event.session_id is None:
            # Failed OCR/unknown vehicles are not business parking records.
            # Keep only the decision key; their plates remain exclusively in
            # the short-lived private observation, never in durable history.
            event.license_plate = event.plate_key = None
            event.vehicle_type_id = None
        db.commit()
    except HTTPException as failure:
        db.rollback()
        if failure.status_code not in {400, 404, 409, 422}:
            raise
        # Admission/checkout already rolled back. Reacquire the same locks before
        # recording a manual outcome, so a concurrent successful winner prevails.
        lock_cash_operator(db, actor.id)
        camera_for(db, actor, camera_id, lock=True)
        old = _existing(db, actor, observation_id)
        if old is not None:
            db.rollback()
            return event_view(old)
        fields["observation_id"] = observation_id if db.get(VisionObservation, observation_id) else None
        detail = failure.detail if isinstance(failure.detail, str) else failure.detail.get("message", "Hãy kiểm tra lượt gửi trước khi thao tác.")
        fields["reason"] = f"Cần xử lý thủ công: {detail}"[:500]
        fields["license_plate"] = fields["plate_key"] = None
        event = VisionPassageEvent(**fields)
        db.add(event)
        db.commit()
    return event_view(event)
