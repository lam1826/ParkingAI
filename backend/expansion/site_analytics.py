"""Original assignment: server-grounded traffic, revenue and AI for one authorized lot."""
import hashlib
import json
import threading
from datetime import date, timedelta
from typing import Literal
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from core.clock import BUSINESS_TZ, business_now, business_today, day_bounds
from core.config import settings
from core.money import require_exact_vnd
from services.payment_service import signed_exact_vnd
from core.sql_time import day_bucket, hour_bucket
from database import get_db
from expansion.analytics_models import SiteAiAnalysis
from expansion.site_scope import require_site_access
from models.parking_session import ParkingSession
from models.parking_slot import ParkingSlot
from models.payment import Payment
from models.zone import Zone
from services.ai_service import AIService
from services.auth_service import get_current_user

router = APIRouter(prefix="/sites/{site_id}", tags=["Báo cáo và AI theo bãi"])
_provider_slot = threading.BoundedSemaphore(1)


def period_bounds(period, anchor):
    try:
        if anchor.year >= 9999:
            raise ValueError("unsupported year")
        start = anchor - timedelta(days=6 if period == "week" else 0)
        return day_bounds(start)[0], day_bounds(anchor)[1]
    except (ValueError, OverflowError) as error:
        raise HTTPException(422, "Ngày nằm ngoài phạm vi báo cáo được hỗ trợ.") from error


def summarize(db, actor, site_id, period="day", anchor_date=None):
    from expansion.site_service import availability
    site = require_site_access(db, actor, site_id)
    anchor = anchor_date or business_today()
    start, end = period_bounds(period, anchor)
    slot_ids = select(ParkingSlot.id).join(Zone).where(Zone.site_id == site_id)
    base = (ParkingSession.parking_slot_id.in_(slot_ids), ParkingSession.status != "cancelled")
    incoming = (*base, ParkingSession.check_in_time >= start, ParkingSession.check_in_time < end)
    hour = hour_bucket(ParkingSession.check_in_time)
    day = day_bucket(ParkingSession.check_in_time)
    hours = {int(h): count for h, count in db.execute(select(hour, func.count()).where(*incoming).group_by(hour))}
    days = {str(d): count for d, count in db.execute(select(day, func.count()).where(*incoming).group_by(day))}
    departed = db.scalar(select(func.count()).select_from(ParkingSession).where(*base,
        ParkingSession.check_out_time >= start, ParkingSession.check_out_time < end))
    parking = monthly = refunds = demo_receipts = demo_refunds = 0
    for source, kind, amount, method in db.execute(select(Payment.source_type, Payment.kind, Payment.amount, Payment.method).where(
        Payment.site_id == site_id, Payment.created_at >= start, Payment.created_at < end)):
        value = require_exact_vnd(amount)
        if method == "demo":
            if kind == "refund": demo_refunds += value
            else: demo_receipts += value
        elif kind == "refund": refunds += value
        elif source == "parking_session": parking += value
        else: monthly += value
    current = availability(db, site_id)
    zones = {}
    for slot in current.pop("slots"):
        z = zones.setdefault(slot["zone_id"], {"zone_id": slot["zone_id"], "name": slot["zone_name"], "total": 0, "occupied": 0, "available_now": 0, "reserved_slots": 0})
        z["total"] += 1
        z["occupied"] += int(slot["is_occupied"])
        z["available_now"] += int(slot["available_now"])
        z["reserved_slots"] += int(slot["reserved"])
    current.update(as_of=business_now().replace(tzinfo=BUSINESS_TZ).isoformat(), zones=list(zones.values()),
                   occupancy_rate=round(100 * current["occupied"] / current["total"], 2) if current["total"] else None)
    peak = max(hours.values(), default=0)
    return {"site_id": site_id, "site_name": site.name, "period": period, "start_date": str(start.date()),
            "end_date": str(anchor), "timezone": "Asia/Ho_Chi_Minh", "source": "database", "demo_mode": settings.PARKINGAI_SHOWCASE_MODE,
            "total_arrivals": sum(hours.values()), "total_departures": departed,
            "hourly_traffic": [{"hour": f"{h:02d}:00", "arrivals": hours.get(h, 0)} for h in range(24)],
            "daily_traffic": [{"date": str((start + timedelta(days=i)).date()), "arrivals": days.get(str((start + timedelta(days=i)).date()), 0)} for i in range((end-start).days)],
            "peak_hours": [f"{h:02d}:00" for h, count in sorted(hours.items()) if count == peak and peak > 0],
            "revenue": {"parking_revenue": require_exact_vnd(parking), "monthly_pass_revenue": require_exact_vnd(monthly),
                "refunds": require_exact_vnd(refunds), "total_revenue": signed_exact_vnd(parking + monthly - refunds),
                "demo_receipts": require_exact_vnd(demo_receipts), "demo_refunds": require_exact_vnd(demo_refunds)},
            "current_availability": current,
            "notes": ["Ngày cuối được tính trọn ngày; tuần là 7 ngày kết thúc ở ngày đã chọn.",
                "Cao điểm dựa trên lượt vào, gộp cùng giờ trong kỳ. Chỗ trống và tỷ lệ lấp đầy là thời điểm as_of, không phải số đo của kỳ lịch sử.",
                "Doanh thu là chứng từ thu trừ hoàn trong kỳ; loại khoản demo và lịch sử chưa xác định bãi.",
                "Chế độ đồ án có dữ liệu mẫu; không dùng để kết luận vận hành thực tế." if settings.PARKINGAI_SHOWCASE_MODE else "Không có năng suất nhân viên đã được đo trong dữ liệu này."]}


@router.get("/reports/summary")
def summary(site_id: int, response: Response, period: Literal["day", "week"] = "day", anchor_date: date | None = None,
            db=Depends(get_db), actor=Depends(get_current_user)):
    response.headers["Cache-Control"] = "no-store"
    return summarize(db, actor, site_id, period, anchor_date)


class AnalysisRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    kind: Literal["report", "question", "staff"]
    period: Literal["day", "week"] = "day"
    anchor_date: date = Field(default_factory=business_today)
    question: str = Field(default="", max_length=2000)
    request_id: UUID

    @model_validator(mode="after")
    def valid_request(self):
        period_bounds(self.period, self.anchor_date)
        if self.kind == "question" and not self.question:
            raise ValueError("Vui lòng nhập câu hỏi.")
        return self


def serialize_analysis(row):
    return {"id": row.id, "site_id": row.site_id, "kind": row.kind, "model": row.model, "content": row.content,
            "created_at": row.created_at.replace(tzinfo=BUSINESS_TZ).isoformat(),
            "period": row.context["period"], "start_date": row.context["start_date"], "end_date": row.context["end_date"],
            "source": "database", "generated_by_id": row.generated_by_id}


def history_query(db, actor, site_id):
    require_site_access(db, actor, site_id)
    query = select(SiteAiAnalysis).where(SiteAiAnalysis.site_id == site_id)
    if actor.role.name == "staff":
        query = query.where(SiteAiAnalysis.generated_by_id == actor.id)
    return query


@router.get("/ai/status")
def ai_status(site_id: int, response: Response, db=Depends(get_db), actor=Depends(get_current_user)):
    require_site_access(db, actor, site_id)
    response.headers["Cache-Control"] = "no-store"
    return {"enabled": settings.AI_ENABLED and bool(settings.GEMINI_API_KEY.strip()), "model": settings.GEMINI_MODEL,
            "provider": "Gemini", "requires_network": True}


@router.get("/ai/analyses")
def analyses(site_id: int, response: Response, limit: int = Query(20, ge=1, le=100), offset: int = Query(0, ge=0),
             db=Depends(get_db), actor=Depends(get_current_user)):
    response.headers["Cache-Control"] = "no-store"
    rows = db.scalars(history_query(db, actor, site_id).order_by(SiteAiAnalysis.created_at.desc(), SiteAiAnalysis.id.desc()).offset(offset).limit(limit))
    return [serialize_analysis(row) for row in rows]


@router.get("/ai/analyses/{analysis_id}")
def analysis(site_id: int, analysis_id: UUID, response: Response, db=Depends(get_db), actor=Depends(get_current_user)):
    row = db.scalar(history_query(db, actor, site_id).where(SiteAiAnalysis.id == str(analysis_id)))
    if row is None:
        raise HTTPException(404, "Không tìm thấy phân tích.")
    response.headers["Cache-Control"] = "no-store"
    return serialize_analysis(row)


@router.post("/ai/analyses", status_code=201)
def generate_analysis(site_id: int, body: AnalysisRequest, response: Response, db=Depends(get_db), actor=Depends(get_current_user)):
    require_site_access(db, actor, site_id)
    response.headers["Cache-Control"] = "no-store"
    input_hash = hashlib.sha256(json.dumps({"site_id": site_id, **body.model_dump(mode="json", exclude={"request_id"})}, sort_keys=True).encode()).hexdigest()
    existing_query = select(SiteAiAnalysis).where(SiteAiAnalysis.generated_by_id == actor.id, SiteAiAnalysis.request_id == str(body.request_id))
    def replay(row):
        if row.input_hash != input_hash:
            raise HTTPException(409, "Mã yêu cầu đã dùng cho nội dung khác. Hãy tạo yêu cầu mới.")
        return serialize_analysis(row)
    existing = db.scalar(existing_query)
    if existing is not None:
        return replay(existing)
    if not _provider_slot.acquire(blocking=False):
        raise HTTPException(429, "AI đang xử lý một yêu cầu khác. Vui lòng đợi rồi thử lại.", headers={"Retry-After": "3"})
    try:
        service = AIService(db, api_key=settings.GEMINI_API_KEY)
        context = summarize(db, actor, site_id, body.period, body.anchor_date)
        content = service.generate_scoped_analysis(context, body.kind, body.question)
        # A role/site grant may have been revoked during the provider request.
        db.expire_all()
        require_site_access(db, actor, site_id)
        row = SiteAiAnalysis(id=str(uuid4()), site_id=site_id, generated_by_id=actor.id,
            request_id=str(body.request_id), input_hash=input_hash, kind=body.kind, model=service.model_name,
            context=context, content=content)
        db.add(row)
        try:
            db.commit()
        except IntegrityError:
            db.rollback()
            existing = db.scalar(existing_query)
            if existing is None:
                raise HTTPException(409, "Dữ liệu vừa thay đổi. Hãy kiểm tra lịch sử trước khi thử lại.")
            return replay(existing)
        db.refresh(row)
        return serialize_analysis(row)
    finally:
        _provider_slot.release()
