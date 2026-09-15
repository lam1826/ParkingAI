"""Explicit private-frame analysis; no worker or camera/network access."""
import threading

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool

from database import get_db
from expansion import occupancy_engine as engine, occupancy_service as service
from expansion.occupancy_schemas import CalibrationCreate, OccupancyAnalyze
from models.user import User
from services.auth_service import get_current_user

router = APIRouter(prefix="/api/v2/sites/{site_id}/occupancy", tags=["Quan sát chỗ đỗ qua ảnh"])
_gate = threading.BoundedSemaphore(value=1)


async def _admit():
    if not _gate.acquire(blocking=False):
        raise HTTPException(429, "Đang xử lý một ảnh khác. Vui lòng thử lại sau vài giây.", headers={"Retry-After": "3"})
    try:
        yield
    finally:
        _gate.release()


async def _cpu(function, *args):
    try:
        return await run_in_threadpool(function, *args)
    except ImportError as error:
        raise HTTPException(503, "Runtime OpenCV chưa sẵn sàng trên máy chủ.") from error
    except ValueError as error:
        raise HTTPException(422, str(error)) from error


@router.get("")
def occupancy(site_id: int, response: Response, camera_id: int = Query(gt=0),
              db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    response.headers["Cache-Control"] = "no-store"
    return service.view(db, user, site_id, camera_id)


@router.post("/calibrations", dependencies=[Depends(_admit)])
async def calibrate(site_id: int, body: CalibrationCreate, response: Response,
                    db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    response.headers["Cache-Control"] = "no-store"
    prepared = service.prepare_calibration(db, user, site_id, body)
    if "existing" in prepared:
        return prepared["existing"]
    validation = await _cpu(engine.validate_reference, prepared["content"], prepared["payload"]["regions"], prepared["payload"]["settings"])
    return service.finish_calibration(db, prepared, validation)


@router.post("/analyze", dependencies=[Depends(_admit)])
async def analyze(site_id: int, body: OccupancyAnalyze, response: Response,
                  db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    response.headers["Cache-Control"] = "no-store"
    prepared = service.prepare_analysis(db, user, site_id, body)
    if "existing" in prepared:
        return prepared["existing"]
    result = engine.unknown(prepared["regions"], prepared["skip_reason"]) if prepared["skip_reason"] else await _cpu(
        engine.analyze, prepared["reference"], prepared["content"], prepared["regions"], prepared["settings"])
    return service.finish_analysis(db, prepared, result)
