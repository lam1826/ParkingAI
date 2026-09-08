"""Bounded image decoding and optional, local-only YOLO + PaddleOCR ONNX inference."""
import ast
import hashlib
import hmac
import importlib.util
import io
import math
import os
import re
import threading
import warnings
from datetime import timedelta
from pathlib import Path

from fastapi import HTTPException
from PIL import Image, ImageOps, UnidentifiedImageError
from sqlalchemy import delete, func, select, update
from sqlalchemy.exc import IntegrityError

from core.clock import BUSINESS_TZ, business_now
from expansion.site_scope import require_public_site
from expansion.site_models import ParkingSite
from expansion.vision_models import Camera, VisionObservation

MAX_IMAGE_BYTES = 2 * 1024 * 1024
MAX_IMAGE_PIXELS = 12_000_000
MAX_SITE_OBSERVATIONS = 500
_engine_lock = threading.Lock()
_inference_lock = threading.Lock()
_engine = None
_engine_path = None


def decode_image(content: bytes, mime: str):
    if not content or len(content) > MAX_IMAGE_BYTES:
        raise HTTPException(413, "Ảnh phải có dữ liệu và không vượt quá 2 MB.")
    expected = {"image/jpeg": "JPEG", "image/png": "PNG"}.get(mime)
    if expected is None:
        raise HTTPException(415, "Chỉ nhận ảnh JPEG hoặc PNG.")
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(io.BytesIO(content)) as check:
                phone_jpeg = expected == "JPEG" and check.format == "MPO"
                if (check.format != expected and not phone_jpeg) or (not phone_jpeg and getattr(check, "n_frames", 1) != 1):
                    raise ValueError("format")
                if check.width * check.height > MAX_IMAGE_PIXELS or min(check.size) < 16:
                    raise ValueError("dimensions")
                check.verify()
            with Image.open(io.BytesIO(content)) as source:
                # JPEG gain maps from phone cameras are MPO secondary frames.
                # Decode only the primary photo; no secondary frame or EXIF is
                # retained in the canonical, single-frame JPEG below.
                source.seek(0)
                image = ImageOps.exif_transpose(source).convert("RGB")
                image.thumbnail((1600, 1600))
                clean = Image.new("RGB", image.size)
                clean.paste(image)
                encoded = io.BytesIO()
                clean.save(encoded, "JPEG", quality=85)
                return clean, encoded.getvalue()
    except (UnidentifiedImageError, OSError, ValueError, SyntaxError, Image.DecompressionBombError, Image.DecompressionBombWarning) as exc:
        raise HTTPException(422, "Ảnh không hợp lệ, quá nhiều điểm ảnh hoặc không khớp định dạng.") from exc


def model_status():
    configured = os.getenv("PARKING_VISION_ENGINE", "disabled")
    path = Path(os.getenv("PARKING_VISION_MODEL", ""))
    available = configured == "yolo_rapidocr" and path.is_file() and path.suffix.lower() == ".onnx"
    dependencies = all(importlib.util.find_spec(name) is not None for name in ("onnxruntime", "rapidocr_onnxruntime", "numpy"))
    return {"engine": configured, "available": bool(available and dependencies),
            "reason": "Sẵn sàng dùng model cục bộ; cần kiểm tra kết quả trên ảnh thật." if available and dependencies
            else "Chưa cấu hình YOLO biển số ONNX và thư viện OCR cục bộ. Có thể nhập biển số thủ công.",
            "human_confirmation_required": True, "accuracy_measured": False}


def normalize_candidate(text):
    compact = re.sub(r"[^A-Z0-9]", "", text.upper())
    if not 5 <= len(compact) <= 15 or not any(c.isdigit() for c in compact):
        return None
    match = re.fullmatch(r"(\d{2}[A-Z]\d?)(\d{5})", compact)
    if match:
        prefix, number = match.groups()
        return f"{prefix}-{number[:3]}.{number[3:]}"
    return compact


def _iou(first, second):
    x1, y1 = max(first[0], second[0]), max(first[1], second[1])
    x2, y2 = min(first[2], second[2]), min(first[3], second[3])
    intersection = max(0, x2 - x1) * max(0, y2 - y1)
    union = (first[2] - first[0]) * (first[3] - first[1]) + (second[2] - second[0]) * (second[3] - second[1]) - intersection
    return intersection / union if union > 0 else 0


class YoloRapidOCR:
    """YOLOv8 raw ONNX output only. No torch pickle or model/network downloads."""
    def __init__(self, model_path):
        import onnxruntime as ort
        from rapidocr_onnxruntime import RapidOCR

        options = ort.SessionOptions()
        options.intra_op_num_threads = 2
        options.inter_op_num_threads = 1
        self.detector = ort.InferenceSession(str(model_path), sess_options=options, providers=["CPUExecutionProvider"])
        self.input = self.detector.get_inputs()[0]
        shape = self.input.shape
        if len(shape) != 4 or shape[1] != 3 or shape[2:] != [640, 640]:
            raise ValueError("Expected a 640px YOLOv8 NCHW export")
        names = ast.literal_eval(self.detector.get_modelmeta().custom_metadata_map.get("names", "{}"))
        if not isinstance(names, dict):
            raise ValueError("Detector class metadata is required")
        self.plate_classes = [int(key) for key, value in names.items() if re.search(r"plate|licen[cs]e|bi[eể]n", str(value), re.I)]
        if not self.plate_classes:
            raise ValueError("Generic COCO weights are not license-plate weights")
        # RapidOCR 1.4.4 distributes its PaddleOCR ONNX models inside the wheel.
        # Missing package/model files raise; this adapter never downloads them.
        self.ocr = RapidOCR(intra_op_num_threads=2, inter_op_num_threads=1)

    def recognize(self, image):
        import numpy as np

        ratio = min(640 / image.width, 640 / image.height)
        size = (round(image.width * ratio), round(image.height * ratio))
        left, top = (640 - size[0]) // 2, (640 - size[1]) // 2
        canvas = Image.new("RGB", (640, 640), (114, 114, 114))
        canvas.paste(image.resize(size), (left, top))
        pixels = np.asarray(canvas, dtype=np.float32).transpose(2, 0, 1)[None] / 255.0
        output = self.detector.run(None, {self.input.name: pixels})[0]
        if output.ndim != 3 or output.shape[0] != 1 or output.shape[1] > 128:
            raise ValueError("Unsupported YOLO output")
        boxes = []
        for row in output[0].T:
            if max(self.plate_classes) + 4 >= len(row) or not np.all(np.isfinite(row)):
                continue
            confidence = max(float(row[4 + label]) for label in self.plate_classes)
            if confidence < 0.3:
                continue
            cx, cy, width, height = [float(value) for value in row[:4]]
            box = [max(0, round((cx - width / 2 - left) / ratio)), max(0, round((cy - height / 2 - top) / ratio)),
                   min(image.width, round((cx + width / 2 - left) / ratio)), min(image.height, round((cy + height / 2 - top) / ratio))]
            if box[2] - box[0] >= 20 and box[3] - box[1] >= 8:
                boxes.append((confidence, box))
        selected = []
        for confidence, box in sorted(boxes, key=lambda item: item[0], reverse=True):
            if any(_iou(box, item["box"]) > 0.45 for item in selected):
                continue
            crop = image.crop(tuple(box))
            if crop.width < 320:
                crop = crop.resize((320, max(16, round(crop.height * 320 / crop.width))))
            lines, _ = self.ocr(np.asarray(crop)[:, :, ::-1].copy(), use_cls=False)
            lines = lines or []
            # Reading order supports one and two-line plates. OCR text is data.
            lines.sort(key=lambda line: (round(min(point[1] for point in line[0]) / 10), min(point[0] for point in line[0])))
            plate = normalize_candidate("".join(str(line[1]) for line in lines))
            scores = [float(line[2]) for line in lines if math.isfinite(float(line[2]))]
            text_confidence = min(scores) if scores else 0.0
            selected.append({"box": box, "plate": plate, "confidence": round(min(1.0, max(0.0, confidence * text_confidence)), 4),
                             "detector_confidence": round(min(1.0, confidence), 4)})
            if len(selected) >= 5:
                break
        return selected


def recognize_image(image):
    global _engine, _engine_path
    status = model_status()
    if not status["available"]:
        return {"ocr_status": "unavailable", "engine": status["engine"], "detections": [], "suggested_plate": None, "confidence": None}
    if not _inference_lock.acquire(blocking=False):
        raise HTTPException(429, "Bộ nhận diện đang xử lý ảnh khác. Thử lại sau vài giây.")
    try:
        path = Path(os.environ["PARKING_VISION_MODEL"]).resolve()
        with _engine_lock:
            if _engine is None or _engine_path != path:
                _engine = YoloRapidOCR(path)
                _engine_path = path
        detections = _engine.recognize(image)
        recognized = [item for item in detections if item["plate"]]
        best = max(recognized, key=lambda item: item["confidence"]) if recognized else None
        return {"ocr_status": "recognized" if best else "no_plate", "engine": "yolo_rapidocr",
                "detections": detections, "suggested_plate": best["plate"] if best else None,
                "confidence": best["confidence"] if best else None}
    except HTTPException:
        raise
    except Exception:
        # Do not expose model paths, external-library traces, or OCR snippets.
        return {"ocr_status": "error", "engine": "yolo_rapidocr", "detections": [], "suggested_plate": None, "confidence": None}
    finally:
        _inference_lock.release()


def purge_expired(db, site_id=None):
    statement = delete(VisionObservation).where(VisionObservation.expires_at <= business_now())
    if site_id is not None:
        statement = statement.where(VisionObservation.site_id == site_id)
    return db.execute(statement).rowcount


def ingest_observation(db, camera, metadata, content, mime, edge_token_hash=None):
    now = business_now()
    require_public_site(db, camera.site_id)
    if not camera.is_active:
        raise HTTPException(409, "Camera đang ngừng hoạt động.")
    digest = hashlib.sha256(content).hexdigest()
    existing = db.scalar(select(VisionObservation).where(VisionObservation.camera_id == camera.id,
                          VisionObservation.event_id == str(metadata.event_id)))
    if existing:
        if existing.image_hash != digest:
            raise HTTPException(409, "Mã ảnh đã được dùng cho nội dung khác.")
        if existing.expires_at <= now:
            raise HTTPException(410, "Ảnh đã hết thời hạn lưu.")
        return existing
    captured = metadata.captured_at.astimezone(BUSINESS_TZ).replace(tzinfo=None) if metadata.captured_at else now
    if captured > now + timedelta(minutes=5) or captured < now - timedelta(hours=24):
        raise HTTPException(422, "Thời điểm chụp phải trong 24 giờ qua và không vượt quá 5 phút tương lai.")
    count = db.scalar(select(func.count()).select_from(VisionObservation).where(
        VisionObservation.camera_id == camera.id, VisionObservation.observed_at > now - timedelta(minutes=1)))
    if count >= 30:
        raise HTTPException(429, "Camera đạt giới hạn 30 ảnh/phút. Vui lòng đợi.")
    image, encoded = decode_image(content, mime)
    result = recognize_image(image)
    # A no-op non-key UPDATE locks this site's quota on both SQLite and
    # PostgreSQL. Site then camera is the common order; OCR holds neither lock.
    claimed = db.execute(update(ParkingSite).where(ParkingSite.id == camera.site_id,
        ParkingSite.is_active.is_(True)).values(name=ParkingSite.name))
    if claimed.rowcount != 1:
        raise HTTPException(409, "Bãi vừa ngừng hoạt động. Ảnh chưa được lưu.")
    camera = db.scalar(select(Camera).where(Camera.id == camera.id).with_for_update(key_share=True)
                       .execution_options(populate_existing=True))
    if not camera.is_active:
        raise HTTPException(409, "Camera vừa ngừng hoạt động. Ảnh chưa được lưu.")
    if edge_token_hash is not None and (not camera.edge_token_hash or not hmac.compare_digest(camera.edge_token_hash, edge_token_hash)):
        raise HTTPException(401, "Khóa camera vừa được thu hồi. Ảnh chưa được lưu.")
    now = business_now()
    existing = db.scalar(select(VisionObservation).where(VisionObservation.camera_id == camera.id,
                         VisionObservation.event_id == str(metadata.event_id)))
    if existing:
        if existing.image_hash != digest:
            raise HTTPException(409, "Mã ảnh đã được dùng cho nội dung khác.")
        return existing
    count = db.scalar(select(func.count()).select_from(VisionObservation).where(
        VisionObservation.camera_id == camera.id, VisionObservation.observed_at > now - timedelta(minutes=1)))
    if count >= 30:
        raise HTTPException(429, "Camera đạt giới hạn 30 ảnh/phút. Vui lòng đợi.")
    purge_expired(db, camera.site_id)
    count = db.scalar(select(func.count()).select_from(VisionObservation).where(VisionObservation.site_id == camera.site_id))
    if count >= MAX_SITE_OBSERVATIONS:
        raise HTTPException(409, "Bãi đã lưu tối đa 500 ảnh. Xóa ảnh cũ trước khi tiếp tục.")
    observation = VisionObservation(camera_id=camera.id, site_id=camera.site_id, event_id=str(metadata.event_id),
        image_hash=digest, image_bytes=encoded, image_width=image.width, image_height=image.height,
        observed_at=now, captured_at=captured, expires_at=now + timedelta(hours=camera.retention_hours), **result)
    db.add(observation)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        winner = db.scalar(select(VisionObservation).where(VisionObservation.camera_id == camera.id,
                           VisionObservation.event_id == str(metadata.event_id)))
        if winner is None or winner.image_hash != digest:
            raise HTTPException(409, "Ảnh vừa được ghi hoặc cấu hình đã thay đổi. Hãy tải lại.")
        return winner
    db.refresh(observation)
    return observation


def serialize_observation(observation, camera):
    def stamp(value):
        return value.replace(tzinfo=BUSINESS_TZ).isoformat() if value else None
    return {"id": observation.id, "camera_id": observation.camera_id, "site_id": observation.site_id,
            "event_id": observation.event_id, "observed_at": stamp(observation.observed_at),
            "captured_at": stamp(observation.captured_at), "expires_at": stamp(observation.expires_at),
            "ocr_status": observation.ocr_status, "engine": observation.engine,
            "suggested_plate": observation.suggested_plate, "confidence": observation.confidence,
            "detections": observation.detections, "review_status": observation.review_status,
            "confirmed_plate": observation.confirmed_plate, "reviewed_at": stamp(observation.reviewed_at),
            "image_width": observation.image_width, "image_height": observation.image_height,
            "image_url": f"/api/v2/vision/observations/{observation.id}/image",
            "next_action": ({"kind": "check_in" if camera.direction == "entry" else "checkout_lookup",
                             "license_plate": observation.confirmed_plate, "zone_id": camera.zone_id}
                            if observation.review_status == "accepted" else None)}


if __name__ == "__main__":
    import argparse
    from database import SessionLocal
    parser = argparse.ArgumentParser(description="Remove expired private ALPR images and observations.")
    parser.add_argument("command", choices=["purge-expired"])
    parser.parse_args()
    with SessionLocal() as session:
        removed = purge_expired(session)
        session.commit()
        print(f"Expired observations removed: {removed}")
