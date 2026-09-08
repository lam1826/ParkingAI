"""Phone image capture and optional camera uploads, all scoped to a parking site."""
import hashlib
import hmac
import secrets
import threading
import uuid
from types import SimpleNamespace

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from pydantic import ValidationError
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool
from starlette.formparsers import MultiPartException, MultiPartParser

from core.clock import business_now
from database import get_db
from expansion.site_scope import require_site_access
from expansion.vision_models import Camera, VisionObservation
from expansion.vision_schemas import CameraCreate, CameraUpdate, ObservationReview, ObservationUpload
from expansion.vision_service import (
    MAX_IMAGE_BYTES,
    ingest_observation,
    model_status,
    prepare_observation,
    purge_expired,
    serialize_observation,
)
from models.user import User
from models.zone import Zone
from services.auth_service import RoleChecker, get_current_user

router = APIRouter(prefix="/api/v2", tags=["Camera nhận diện thử nghiệm"])
_upload_gate = threading.BoundedSemaphore(value=1)


async def _admit_upload():
    """Shed concurrent camera work before authentication opens a DB session."""
    if not _upload_gate.acquire(blocking=False):
        raise HTTPException(429, "Hệ thống đang xử lý một ảnh khác. Vui lòng thử lại sau vài giây.", headers={"Retry-After": "3"})
    try:
        yield
    finally:
        _upload_gate.release()


def _camera(db, user, camera_id, minimum_role="staff"):
    camera = db.get(Camera, camera_id)
    if camera is None:
        raise HTTPException(404, "Không tìm thấy camera.")
    require_site_access(db, user, camera.site_id, minimum_role=minimum_role)
    return camera


def _camera_json(camera):
    return {"id": camera.id, "site_id": camera.site_id, "zone_id": camera.zone_id, "name": camera.name,
            "direction": camera.direction, "is_active": camera.is_active, "retention_hours": camera.retention_hours,
            "edge_enabled": camera.edge_token_hash is not None}


def _save(db):
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(409, "Tên camera đã được dùng hoặc khu vực không còn hợp lệ.") from exc


@router.get("/cameras")
def cameras(site_id: int = Query(gt=0), db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    require_site_access(db, user, site_id)
    return [_camera_json(camera) for camera in db.scalars(select(Camera).where(Camera.site_id == site_id).order_by(Camera.id)).all()]


@router.post("/cameras", status_code=201, dependencies=[Depends(RoleChecker("manager"))])
def create_camera(body: CameraCreate, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    require_site_access(db, user, body.site_id, minimum_role="manager")
    if body.zone_id is not None:
        zone = db.get(Zone, body.zone_id)
        if zone is None or zone.site_id != body.site_id or not zone.is_active:
            raise HTTPException(422, "Khu vực phải thuộc bãi được chọn và đang hoạt động.")
    camera = Camera(**body.model_dump())
    db.add(camera)
    _save(db)
    return _camera_json(camera)


@router.patch("/cameras/{camera_id}", dependencies=[Depends(RoleChecker("manager"))])
def update_camera(camera_id: int, body: CameraUpdate, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    camera = _camera(db, user, camera_id, "manager")
    for name, value in body.model_dump(exclude_unset=True).items():
        setattr(camera, name, value)
    if not camera.is_active:
        camera.edge_token_hash = None
    _save(db)
    return _camera_json(camera)


@router.delete("/cameras/{camera_id}", dependencies=[Depends(RoleChecker("manager"))])
def disable_camera(camera_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    camera = _camera(db, user, camera_id, "manager")
    camera.is_active = False
    camera.edge_token_hash = None
    _save(db)
    return _camera_json(camera)


@router.post("/cameras/{camera_id}/edge-token", dependencies=[Depends(RoleChecker("manager"))])
def rotate_edge_token(camera_id: int, response: Response, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    camera = _camera(db, user, camera_id, "manager")
    if not camera.is_active:
        raise HTTPException(409, "Camera đang ngừng hoạt động.")
    token = secrets.token_urlsafe(32)
    camera.edge_token_hash = hashlib.sha256(token.encode()).hexdigest()
    _save(db)
    response.headers["Cache-Control"] = "no-store"
    return {"camera_id": camera.id, "token": token}


@router.get("/vision/status", dependencies=[Depends(RoleChecker("staff"))])
def status():
    return model_status()


async def _read_upload(request):
    # Consume a bounded raw body before multipart parsing; UploadFile alone
    # would spool an arbitrarily large request to disk before endpoint checks.
    limit = MAX_IMAGE_BYTES + 16_384
    body = bytearray()
    async for chunk in request.stream():
        if len(body) + len(chunk) > limit:
            raise HTTPException(413, "Ảnh tải lên vượt giới hạn 2 MB.")
        body.extend(chunk)
    async def stream():
        yield bytes(body)
    try:
        form = await MultiPartParser(request.headers, stream(), max_files=1, max_fields=3, max_part_size=512).parse()
    except (MultiPartException, ValueError) as exc:
        raise HTTPException(422, "Yêu cầu phải gồm một ảnh JPEG/PNG và thông tin camera hợp lệ.") from exc
    try:
        if len(form.getlist("file")) != 1 or set(form) - {"file", "camera_id", "event_id", "captured_at"}:
            raise HTTPException(422, "Chỉ gửi một file ảnh và thông tin camera được hỗ trợ.")
        if any(len(form.getlist(key)) > 1 for key in ("camera_id", "event_id", "captured_at")):
            raise HTTPException(422, "Trường dữ liệu bị lặp.")
        file = form.get("file")
        if not hasattr(file, "read"):
            raise HTTPException(422, "Thiếu file ảnh.")
        try:
            metadata = ObservationUpload(camera_id=form.get("camera_id"), event_id=form.get("event_id") or str(uuid.uuid4()),
                                         captured_at=form.get("captured_at") or None)
        except ValidationError as exc:
            raise HTTPException(422, "Thông tin camera, mã sự kiện hoặc thời điểm chụp không hợp lệ.") from exc
        return metadata, await file.read(MAX_IMAGE_BYTES + 1), file.content_type
    finally:
        await form.close()


@router.post(
    "/vision/observations",
    status_code=201,
    dependencies=[Depends(_admit_upload), Depends(RoleChecker("staff"))],
)
async def upload_observation(request: Request, response: Response, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    actor = SimpleNamespace(
        id=user.id,
        is_active=user.is_active,
        role=SimpleNamespace(name=user.role.name),
    )
    # Authentication is read-only. Release its transaction before receiving
    # the body or running CPU-heavy image work.
    db.rollback()
    metadata, content, mime = await _read_upload(request)
    _camera(db, actor, metadata.camera_id)
    db.rollback()
    prepared = await run_in_threadpool(prepare_observation, metadata, content, mime)
    camera = _camera(db, actor, metadata.camera_id)
    observation = await run_in_threadpool(ingest_observation, db, camera, metadata, prepared)
    response.headers["Cache-Control"] = "no-store"
    return serialize_observation(observation, camera)


@router.post("/vision/edge-events", status_code=201, dependencies=[Depends(_admit_upload)])
async def edge_observation(request: Request, response: Response, db: Session = Depends(get_db)):
    token = request.headers.get("x-camera-token", "")
    if not 32 <= len(token) <= 128:
        raise HTTPException(401, "Khóa camera không hợp lệ.")
    metadata, content, mime = await _read_upload(request)
    camera = db.get(Camera, metadata.camera_id)
    digest = hashlib.sha256(token.encode()).hexdigest()
    if camera is None or not camera.is_active or not camera.edge_token_hash or not hmac.compare_digest(camera.edge_token_hash, digest):
        raise HTTPException(401, "Khóa camera không hợp lệ.")
    db.rollback()
    prepared = await run_in_threadpool(prepare_observation, metadata, content, mime)
    camera = db.get(Camera, metadata.camera_id)
    if camera is None:
        raise HTTPException(401, "Khóa camera không hợp lệ.")
    observation = await run_in_threadpool(ingest_observation, db, camera, metadata, prepared, digest)
    response.headers["Cache-Control"] = "no-store"
    # A capture token can write only to its camera, never read image/plate data.
    return {"id": observation.id, "event_id": observation.event_id, "received": True}


@router.get("/vision/observations")
def observations(response: Response, site_id: int = Query(gt=0), limit: int = Query(25, ge=1, le=100), offset: int = Query(0, ge=0),
                 db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    require_site_access(db, user, site_id)
    rows = db.execute(select(VisionObservation, Camera).join(Camera).where(
        VisionObservation.site_id == site_id, VisionObservation.expires_at > business_now()
    ).order_by(VisionObservation.observed_at.desc(), VisionObservation.id).offset(offset).limit(limit)).all()
    response.headers["Cache-Control"] = "no-store"
    return [serialize_observation(observation, camera) for observation, camera in rows]


def _observation(db, user, observation_id, lock=False):
    query = select(VisionObservation).where(VisionObservation.id == observation_id, VisionObservation.expires_at > business_now())
    if lock:
        query = query.with_for_update()
    observation = db.scalar(query)
    if observation is None:
        raise HTTPException(404, "Ảnh không tồn tại hoặc đã hết thời hạn lưu.")
    try:
        require_site_access(db, user, observation.site_id)
    except HTTPException as exc:
        # Another site's identifier must look exactly like a missing one.
        if exc.status_code in {403, 404}:
            raise HTTPException(404, "Ảnh không tồn tại hoặc đã hết thời hạn lưu.") from None
        raise
    return observation


@router.get("/vision/observations/{observation_id}/image")
def observation_image(observation_id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    observation = _observation(db, user, observation_id)
    return Response(observation.image_bytes, media_type="image/jpeg", headers={"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"})


@router.post("/vision/observations/{observation_id}/review", dependencies=[Depends(RoleChecker("staff"))])
def review_observation(observation_id: str, body: ObservationReview, response: Response,
                       db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    observation = _observation(db, user, observation_id, lock=True)
    decision = "accepted" if body.decision == "accept" else "rejected"
    if observation.review_status != "pending":
        if observation.review_status != decision or observation.confirmed_plate != body.license_plate:
            raise HTTPException(409, "Ảnh đã được xác nhận với nội dung khác.")
    else:
        changed = db.execute(update(VisionObservation).where(
            VisionObservation.id == observation.id,
            VisionObservation.review_status == "pending",
            VisionObservation.expires_at > business_now(),
        ).values(review_status=decision, confirmed_plate=body.license_plate,
                 reviewed_by_id=user.id, reviewed_at=business_now()))
        db.commit()
        db.refresh(observation)
        if changed.rowcount != 1 and (observation.review_status != decision or observation.confirmed_plate != body.license_plate):
            raise HTTPException(409, "Ảnh đã được người khác xác nhận hoặc hết hạn. Hãy tải lại.")
    response.headers["Cache-Control"] = "no-store"
    return serialize_observation(observation, db.get(Camera, observation.camera_id))


@router.delete("/vision/observations/{observation_id}", status_code=204, dependencies=[Depends(RoleChecker("manager"))])
def delete_observation(observation_id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    observation = _observation(db, user, observation_id)
    require_site_access(db, user, observation.site_id, minimum_role="manager")
    db.delete(observation)
    db.commit()


@router.post("/vision/purge-expired", dependencies=[Depends(RoleChecker("manager"))])
def purge_site(site_id: int = Query(gt=0), db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    require_site_access(db, user, site_id, minimum_role="manager")
    count = purge_expired(db, site_id)
    db.commit()
    return {"removed": count}
