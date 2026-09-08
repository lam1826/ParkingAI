"""Site-scoped forecast, deterministic operational alerts and staffing scenarios."""
from collections import Counter
from datetime import timedelta
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from core.clock import BUSINESS_TZ, business_now
from database import get_db
from expansion.forecast import MAX_HISTORY_DAYS, build_forecast, build_staff_plan
from expansion.site_scope import require_site_access
from models.parking_session import ParkingSession
from models.parking_slot import ParkingSlot
from models.zone import Zone
from services.auth_service import get_current_user

router = APIRouter(prefix="/api/v2/insights", tags=["Dự báo và cảnh báo"])


def _zones(db, user, site_id, zone_id=None):
    require_site_access(db, user, site_id)
    if zone_id is not None:
        zone = db.get(Zone, zone_id)
        if zone is None or zone.site_id != site_id:
            raise HTTPException(403, "Khu vực không thuộc bãi được chọn.")
    query = select(Zone.id).where(Zone.site_id == site_id)
    return query.where(Zone.id == zone_id) if zone_id is not None else query


def forecast_for_site(db, user, site_id, zone_id=None, horizon_hours=24):
    now = business_now()
    zone_ids = _zones(db, user, site_id, zone_id)
    start = now - timedelta(days=MAX_HISTORY_DAYS)
    rows = db.execute(select(ParkingSession.check_in_time, ParkingSession.check_out_time).join(
        ParkingSlot, ParkingSlot.id == ParkingSession.parking_slot_id).where(
        ParkingSlot.zone_id.in_(zone_ids), ParkingSession.status != "cancelled",
        or_(ParkingSession.check_in_time >= start, ParkingSession.check_out_time >= start),
        ParkingSession.check_in_time < now
    ).order_by(ParkingSession.check_in_time).limit(100_001)).all()
    if len(rows) > 100_000:
        raise HTTPException(422, "Kỳ dữ liệu quá lớn cho chế độ đồ án. Hãy chọn một khu vực.")
    arrivals, departures = Counter(), Counter()
    for incoming, outgoing in rows:
        arrivals[incoming.replace(minute=0, second=0, microsecond=0)] += 1
        if outgoing is not None and outgoing < now:
            departures[outgoing.replace(minute=0, second=0, microsecond=0)] += 1
    result = build_forecast(arrivals, departures, now, horizon_hours)
    result.update(site_id=site_id, zone_id=zone_id)
    result["warnings"].append("Chỉ tính các lượt có vị trí thuộc bãi; lượt legacy chưa gắn bãi không được gộp tự động.")
    return result


@router.get("/forecast")
def forecast(response: Response, site_id: int = Query(gt=0), zone_id: int | None = Query(None, gt=0), horizon_hours: int = Query(24, ge=1, le=48),
             db: Session = Depends(get_db), user=Depends(get_current_user)):
    response.headers["Cache-Control"] = "no-store"
    return forecast_for_site(db, user, site_id, zone_id, horizon_hours)


class StaffPlanRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    site_id: int = Field(gt=0)
    zone_id: int | None = Field(default=None, gt=0)
    horizon_hours: int = Field(default=24, ge=1, le=48)
    service_seconds_per_vehicle: float = Field(ge=5, le=600)
    utilization_target: float = Field(default=.8, ge=.3, le=.95)
    min_staff: int = Field(default=1, ge=0, le=50)
    max_staff: int = Field(default=10, ge=1, le=50)
    service_time_source: Literal["assumed", "measured"] = "assumed"
    measurement_samples: int = Field(default=0, ge=0, le=100_000)

    @model_validator(mode="after")
    def bounds(self):
        if self.max_staff < self.min_staff:
            raise ValueError("max_staff phải lớn hơn hoặc bằng min_staff.")
        if self.service_time_source == "measured" and self.measurement_samples < 30:
            raise ValueError("Năng suất đo thực tế cần ít nhất 30 mẫu được ghi nhận.")
        return self


@router.post("/staff-plan")
def staff_plan(body: StaffPlanRequest, response: Response, db: Session = Depends(get_db), user=Depends(get_current_user)):
    forecast = forecast_for_site(db, user, body.site_id, body.zone_id, body.horizon_hours)
    result = build_staff_plan(forecast, service_seconds=body.service_seconds_per_vehicle,
        utilization=body.utilization_target, min_staff=body.min_staff, max_staff=body.max_staff)
    result["assumptions"].update(service_time_source=body.service_time_source, measurement_samples=body.measurement_samples,
                                  measurement_verified=False)
    result.update(site_id=body.site_id, zone_id=body.zone_id, forecast_backtest=forecast["backtest"], coverage=forecast["coverage"])
    result["warnings"].append("Năng suất là tham số do người dùng cung cấp; hệ thống chưa tự đo hoặc xác minh mẫu.")
    response.headers["Cache-Control"] = "no-store"
    return result


@router.get("/anomalies")
def anomalies(response: Response, site_id: int = Query(gt=0), zone_id: int | None = Query(None, gt=0),
              stale_hours: int = Query(24, ge=1, le=720), db: Session = Depends(get_db), user=Depends(get_current_user)):
    zones = _zones(db, user, site_id, zone_id)
    now = business_now()
    rows = db.execute(select(ParkingSession.id, ParkingSession.check_in_time, ParkingSession.parking_slot_id).join(
        ParkingSlot, ParkingSlot.id == ParkingSession.parking_slot_id).where(
        ParkingSlot.zone_id.in_(zones), ParkingSession.status == "active")).all()
    items = []
    active_slots = set()
    for session_id, incoming, slot_id in rows:
        active_slots.add(slot_id)
        age = (now - incoming).total_seconds() / 3600
        if age >= stale_hours:
            items.append({"code": "long_stay", "severity": "info", "session_id": session_id,
                          "message": "Lượt gửi kéo dài cần kiểm tra; có thể là khách gửi dài ngày.",
                          "evidence": {"duration_hours": round(age, 1), "threshold_hours": stale_hours}})
    for slot in db.scalars(select(ParkingSlot).where(ParkingSlot.zone_id.in_(zones))):
        if slot.is_occupied != (slot.id in active_slots):
            items.append({"code": "occupancy_mismatch", "severity": "warning", "slot_id": slot.id,
                          "message": "Cờ vị trí và lượt đang gửi không khớp; cần đối chiếu thủ công.",
                          "evidence": {"flag_occupied": slot.is_occupied, "has_active_session": slot.id in active_slots}})
    response.headers["Cache-Control"] = "no-store"
    return {"site_id": site_id, "as_of": now.replace(tzinfo=BUSINESS_TZ).isoformat(), "items": items[:100],
            "total": len(items), "rules": ["long_stay", "occupancy_mismatch"],
            "note": "Cảnh báo theo quy tắc, không kết luận gian lận và không tự sửa dữ liệu."}
