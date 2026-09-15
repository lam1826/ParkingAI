"""Scope, retention and temporal interpretation around the pure CPU baseline."""
import hashlib
import json
from datetime import timedelta

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import defer

from core.clock import BUSINESS_TZ, business_now
from expansion import occupancy_engine as engine
from expansion.occupancy_models import OccupancyCalibration, OccupancyCalibrationSlot, OccupancyObservation
from expansion.site_scope import require_site_access
from expansion.vision_models import Camera, VisionObservation
from models.parking_slot import ParkingSlot
from models.user import User
from models.vehicle_type import VehicleType
from models.zone import Zone


def iso(value):
    return value.replace(tzinfo=BUSINESS_TZ).isoformat() if value else None


def _camera(db, user, site_id, camera_id, *, manage=False, lock=False):
    require_site_access(db, user, site_id, minimum_role="manager" if manage else "staff")
    query = select(Camera).where(Camera.id == camera_id, Camera.site_id == site_id)
    if lock:
        query = query.with_for_update()
    camera = db.scalar(query.execution_options(populate_existing=True))
    if camera is None:
        raise HTTPException(404, "Không tìm thấy camera tại bãi này.")
    if (manage or lock) and not camera.is_active:
        raise HTTPException(409, "Camera đã ngừng hoạt động.")
    return camera


def _image(db, camera, observation_id, *, content=False):
    query = select(VisionObservation).where(VisionObservation.id == observation_id,
        VisionObservation.camera_id == camera.id, VisionObservation.site_id == camera.site_id)
    if not content:
        query = query.options(defer(VisionObservation.image_bytes, raiseload=True))
    return db.scalar(query.execution_options(populate_existing=True)) if observation_id else None


def _expiry(image, camera):
    return min(image.expires_at, image.observed_at + timedelta(hours=camera.retention_hours)) if image else None


def _available(image, camera, now):
    return image is not None and now < _expiry(image, camera)


def _latest_calibration(db, camera):
    return db.scalar(select(OccupancyCalibration).where(OccupancyCalibration.camera_id == camera.id)
        .order_by(OccupancyCalibration.version.desc()).limit(1))


def _slots(db, camera, regions, *, require_active=False):
    ids = [region["slot_id"] for region in regions]
    rows = db.execute(select(ParkingSlot, Zone, VehicleType).join(Zone, ParkingSlot.zone_id == Zone.id)
        .join(VehicleType, ParkingSlot.vehicle_type_id == VehicleType.id)
        .where(ParkingSlot.id.in_(ids), Zone.site_id == camera.site_id)).all()
    found = {slot.id: (slot, zone, kind) for slot, zone, kind in rows}
    if require_active and (len(found) != len(ids) or any(not slot.is_active or not zone.is_active or not kind.is_active
        or (camera.zone_id is not None and zone.id != camera.zone_id) for slot, zone, kind in rows)):
        raise HTTPException(409, "Chọn các chỗ đang hoạt động, thuộc bãi và khu vực của camera.")
    return found


def _slot_identity(slot):
    return {"slot_name": slot.slot_name, "zone_id": slot.zone_id, "vehicle_type_id": slot.vehicle_type_id,
        "slot_created_at": slot.created_at.isoformat() if slot.created_at else None}


def _calibration_json(db, camera, calibration, now):
    if calibration is None:
        return None
    reference = _image(db, camera, calibration.reference_observation_id)
    available = _available(reference, camera, now) and reference.image_hash == calibration.reference_image_hash
    expiry = _expiry(reference, camera) if reference else min(calibration.reference_expires_at,
        calibration.reference_observed_at + timedelta(hours=camera.retention_hours))
    return {"id": calibration.id, "version": calibration.version, "camera_id": camera.id,
        "reference_observation_id": calibration.reference_id_snapshot, "reference_image_available": bool(available),
        "reference_width": calibration.reference_width, "reference_height": calibration.reference_height,
        "valid_until": iso(expiry), "regions": calibration.regions, "settings": calibration.settings,
        "engine": calibration.engine, "settings_schema_version": calibration.settings_schema_version,
        "created_at": iso(calibration.created_at), "created_by_id": calibration.created_by_id}


def view(db, user, site_id, camera_id):
    camera = _camera(db, user, site_id, camera_id)
    now = business_now()
    calibration = _latest_calibration(db, camera)
    result = {"camera_id": camera.id, "server_now": iso(now), "engine": engine.status(),
        "calibration": _calibration_json(db, camera, calibration, now), "latest": None,
        "valid_until": None, "source_image_available": False, "readings": []}
    if calibration is None:
        return result
    latest = db.scalar(select(OccupancyObservation).where(OccupancyObservation.calibration_id == calibration.id)
        .order_by(OccupancyObservation.measured_at.desc(), OccupancyObservation.received_at.desc(), OccupancyObservation.id.desc()).limit(1))
    reference = _image(db, camera, calibration.reference_observation_id)
    source = _image(db, camera, latest.source_observation_id) if latest else None
    reason = "camera_disabled" if not camera.is_active else "reference_expired" if not result["calibration"]["reference_image_available"] else "no_observation" if latest is None else None
    if latest:
        result["latest"] = {"id": latest.id, "calibration_id": calibration.id, "calibration_version": calibration.version,
            "source_observation_id": latest.source_id_snapshot, "source_image_hash": latest.source_image_hash,
            "measured_at": iso(latest.measured_at), "received_at": iso(latest.received_at),
            "analyzed_at": iso(latest.analyzed_at), "quality": latest.quality, "engine": latest.engine}
        source_available = _available(source, camera, now) and source.image_hash == latest.source_image_hash
        result["source_image_available"] = bool(source_available)
        source_expiry = _expiry(source, camera) if source else min(latest.expires_at, latest.received_at + timedelta(hours=camera.retention_hours))
        result["latest"]["source_image_valid_until"] = iso(source_expiry)
        ref_expiry = _expiry(reference, camera) if reference else min(calibration.reference_expires_at, calibration.reference_observed_at + timedelta(hours=camera.retention_hours))
        valid_until = min(source_expiry, ref_expiry, latest.measured_at + timedelta(seconds=calibration.settings["stale_after_seconds"]))
        result["valid_until"] = iso(valid_until)
        reason = reason or ("source_expired" if not source_available else "future_capture" if latest.measured_at > now else "stale_capture" if now >= valid_until else None)
    found = _slots(db, camera, calibration.regions)
    readings = {reading["slot_id"]: reading for reading in latest.readings} if latest else {}
    for region in calibration.regions:
        slot, zone, kind = found.get(region["slot_id"], (None, None, None))
        active = bool(slot and slot.is_active and zone.is_active and kind.is_active and (camera.zone_id is None or zone.id == camera.zone_id))
        business_state = ("occupied" if slot.is_occupied else "empty") if active else "inactive"
        reading = readings.get(region["slot_id"], {})
        mapping_changed = bool(slot and any(region.get(name) != value for name, value in _slot_identity(slot).items()))
        current_reason = "slot_inactive" if not active else "slot_mapping_changed" if mapping_changed else reason or reading.get("reason")
        state = "unknown" if not active or reason or mapping_changed else reading.get("state", "unknown")
        result["readings"].append({**region, "slot_name": slot.slot_name if slot else f"#{region['slot_id']}",
            "zone_name": zone.name if zone else None, "state": state, "raw_state": reading.get("raw_state", "unknown"),
            "change_ratio": reading.get("change_ratio"), "reason": current_reason, "business_state": business_state,
            "mismatch": state != business_state if state != "unknown" and active else None})
    return result


def _hash(body):
    return hashlib.sha256(json.dumps(body, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def prepare_calibration(db, user, site_id, body):
    camera = _camera(db, user, site_id, body.camera_id, manage=True)
    payload = body.model_dump(mode="json")
    fingerprint = _hash(payload)
    prior = db.scalar(select(OccupancyCalibration).where(OccupancyCalibration.camera_id == camera.id, OccupancyCalibration.request_id == body.request_id))
    if prior:
        if prior.payload_hash != fingerprint:
            raise HTTPException(409, "Mã yêu cầu đã dùng cho cấu hình khác.")
        return {"existing": _calibration_json(db, camera, prior, business_now())}
    regions = payload["regions"]
    _slots(db, camera, regions, require_active=True)
    reference = _image(db, camera, str(body.reference_observation_id), content=True)
    if not _available(reference, camera, business_now()):
        raise HTTPException(409, "Ảnh nền không còn được lưu. Chọn ảnh nền mới.")
    prepared = {"user_id": user.id, "site_id": site_id, "payload": payload, "payload_hash": fingerprint,
        "reference_hash": reference.image_hash, "content": bytes(reference.image_bytes)}
    db.rollback()  # CPU work must not hold a transaction or model instances.
    return prepared


def _save(db):
    try:
        db.commit()
    except IntegrityError as error:
        db.rollback()
        raise HTTPException(409, "Cấu hình hoặc ảnh vừa được xử lý ở yêu cầu khác. Làm mới rồi thử lại cùng yêu cầu.") from error


def finish_calibration(db, prepared, validation):
    body = prepared["payload"]
    db.expire_all()
    user = db.get(User, prepared["user_id"])
    if user is None:
        raise HTTPException(403, "Tài khoản không còn quyền truy cập.")
    camera = _camera(db, user, prepared["site_id"], body["camera_id"], manage=True, lock=True)
    prior = db.scalar(select(OccupancyCalibration).where(OccupancyCalibration.camera_id == camera.id, OccupancyCalibration.request_id == body["request_id"]))
    if prior:
        if prior.payload_hash != prepared["payload_hash"]:
            raise HTTPException(409, "Mã yêu cầu đã dùng cho cấu hình khác.")
        return _calibration_json(db, camera, prior, business_now())
    slots = _slots(db, camera, body["regions"], require_active=True)
    reference = _image(db, camera, body["reference_observation_id"])
    if not _available(reference, camera, business_now()) or reference.image_hash != prepared["reference_hash"]:
        raise HTTPException(409, "Ảnh nền đã thay đổi hoặc hết hạn. Chọn lại ảnh nền.")
    prior = _latest_calibration(db, camera)
    row = OccupancyCalibration(site_id=camera.site_id, camera_id=camera.id, version=prior.version + 1 if prior else 1,
        reference_observation_id=reference.id, reference_id_snapshot=reference.id, reference_image_hash=reference.image_hash,
        reference_width=validation["width"], reference_height=validation["height"], reference_observed_at=reference.observed_at,
        reference_expires_at=reference.expires_at, regions=[{**region, **_slot_identity(slots[region["slot_id"]][0])} for region in body["regions"]], settings=body["settings"],
        request_id=body["request_id"], payload_hash=prepared["payload_hash"], created_by_id=user.id)
    db.add(row)
    try:
        db.flush()
        db.add_all([OccupancyCalibrationSlot(calibration_id=row.id, slot_id=region["slot_id"]) for region in row.regions])
    except IntegrityError as error:
        db.rollback()
        raise HTTPException(409, "Chỗ đỗ vừa thay đổi. Làm mới và khoanh lại vùng.") from error
    _save(db)
    return _calibration_json(db, camera, row, business_now())


def prepare_analysis(db, user, site_id, body):
    camera = _camera(db, user, site_id, body.camera_id)
    if not camera.is_active:
        raise HTTPException(409, "Camera đã ngừng hoạt động.")
    calibration = _latest_calibration(db, camera)
    if calibration is None or calibration.id != str(body.calibration_id):
        raise HTTPException(409, "Cấu hình đã thay đổi. Làm mới trước khi phân tích.")
    prior = db.scalar(select(OccupancyObservation).where(OccupancyObservation.calibration_id == calibration.id,
        OccupancyObservation.source_id_snapshot == str(body.observation_id)))
    if prior:
        return {"existing": view(db, user, site_id, camera.id)}
    reference = _image(db, camera, calibration.reference_observation_id, content=True)
    source = _image(db, camera, str(body.observation_id), content=True)
    now = business_now()
    if not _available(reference, camera, now) or reference.image_hash != calibration.reference_image_hash:
        raise HTTPException(409, "Ảnh nền đã hết hạn. Quản lý cần tạo cấu hình từ ảnh nền mới.")
    if not _available(source, camera, now):
        raise HTTPException(404, "Ảnh được chọn không còn được lưu tại camera này.")
    reason = "future_capture" if source.captured_at > now else "stale_capture" if now >= source.captured_at + timedelta(seconds=calibration.settings["stale_after_seconds"]) else None
    prepared = {"user_id": user.id, "site_id": site_id, "camera_id": camera.id, "calibration_id": calibration.id,
        "source_id": source.id, "source_hash": source.image_hash, "reference_hash": reference.image_hash,
        "reference": bytes(reference.image_bytes), "content": bytes(source.image_bytes),
        "regions": calibration.regions, "settings": calibration.settings, "skip_reason": reason}
    db.rollback()
    return prepared


def _consensus(db, calibration, source, result):
    needed = calibration.settings["confirmation_frames"]
    if needed == 1:
        return result
    previous = list(db.scalars(select(OccupancyObservation).where(OccupancyObservation.calibration_id == calibration.id,
        OccupancyObservation.measured_at < source.captured_at,
        OccupancyObservation.measured_at > source.captured_at - timedelta(seconds=calibration.settings["stale_after_seconds"]))
        .order_by(OccupancyObservation.measured_at.desc()).limit(needed - 1)))
    for reading in result["readings"]:
        if reading["raw_state"] == "unknown":
            continue
        if len(previous) < needed - 1 or len({item.measured_at for item in previous}) < needed - 1:
            reading.update(state="unknown", reason="insufficient_history")
        elif any(next((old["raw_state"] for old in item.readings if old["slot_id"] == reading["slot_id"]), "unknown") != reading["raw_state"] for item in previous):
            reading.update(state="unknown", reason="unstable_observations")
    return result


def finish_analysis(db, prepared, result):
    db.expire_all()
    user = db.get(User, prepared["user_id"])
    if user is None:
        raise HTTPException(403, "Tài khoản không còn quyền truy cập.")
    camera = _camera(db, user, prepared["site_id"], prepared["camera_id"], lock=True)
    calibration = _latest_calibration(db, camera)
    if calibration is None or calibration.id != prepared["calibration_id"]:
        raise HTTPException(409, "Cấu hình đã thay đổi trong khi phân tích. Làm mới rồi thử lại.")
    prior = db.scalar(select(OccupancyObservation).where(OccupancyObservation.calibration_id == calibration.id,
        OccupancyObservation.source_id_snapshot == prepared["source_id"]))
    if prior:
        return view(db, user, camera.site_id, camera.id)
    reference = _image(db, camera, calibration.reference_observation_id)
    source = _image(db, camera, prepared["source_id"])
    now = business_now()
    if not _available(reference, camera, now) or reference.image_hash != prepared["reference_hash"] or not _available(source, camera, now) or source.image_hash != prepared["source_hash"]:
        raise HTTPException(409, "Ảnh đã hết hạn hoặc thay đổi trong khi phân tích. Chọn ảnh mới.")
    result = _consensus(db, calibration, source, result)
    row = OccupancyObservation(calibration_id=calibration.id, source_observation_id=source.id,
        source_id_snapshot=source.id, source_image_hash=source.image_hash, measured_at=source.captured_at,
        received_at=source.observed_at, expires_at=source.expires_at, analyzed_by_id=user.id,
        quality=result["quality"], readings=result["readings"])
    db.add(row)
    _save(db)
    return view(db, user, camera.site_id, camera.id)
