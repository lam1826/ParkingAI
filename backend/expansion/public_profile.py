"""Published lot information for visitors, and its manager-only editor.

The anonymous endpoints return only what a manager has published plus the
already public catalog (active vehicle types, plan prices, walk-in rates).
They never expose plates, customers, sessions, revenue, credentials or
internal configuration. Missing information is reported as ``null`` so the
page can show "chưa cập nhật" instead of an invented value.
"""
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, EmailStr, Field, model_validator
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from core.clock import BUSINESS_TZ, business_now
from core.config import settings
from database import get_db
from expansion.gateway import PortalSettings
from expansion.portal_models import SubscriptionPlan
from expansion.site_models import ParkingSite
from expansion.site_scope import require_site_access
from models.parking_slot import ParkingSlot
from models.price_config import PriceConfig
from models.user import User
from models.vehicle_type import VehicleType
from models.zone import Zone
from services.auth_service import get_current_user

router = APIRouter(prefix="/api/v2", tags=["Public site profile"])


class PublicProfileUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    address: str = Field(default="", max_length=250)
    description: str | None = Field(default=None, max_length=2000)
    opening_hours: str | None = Field(default=None, max_length=500)
    contact_phone: str | None = Field(default=None, min_length=8, max_length=20, pattern=r"^\+?[0-9 .\-]+$")
    contact_email: EmailStr | None = Field(default=None, max_length=100)
    latitude: float | None = Field(default=None, ge=-90, le=90)
    longitude: float | None = Field(default=None, ge=-180, le=180)

    @model_validator(mode="after")
    def coordinates_come_in_pairs(self):
        if (self.latitude is None) != (self.longitude is None):
            raise ValueError("Cần nhập cả vĩ độ và kinh độ, hoặc để trống cả hai.")
        for name in ("description", "opening_hours", "contact_phone"):
            if getattr(self, name) == "":
                setattr(self, name, None)
        return self


def _aware(value: datetime | None):
    return value.replace(tzinfo=BUSINESS_TZ) if value is not None and value.tzinfo is None else value


def served_vehicle_types(db: Session, site_id: int):
    """Active vehicle types that have at least one active slot in an active zone of the site."""
    rows = db.execute(select(VehicleType.id, VehicleType.name, func.count(ParkingSlot.id))
        .join(ParkingSlot, ParkingSlot.vehicle_type_id == VehicleType.id)
        .join(Zone, Zone.id == ParkingSlot.zone_id)
        .where(Zone.site_id == site_id, Zone.is_active.is_(True), ParkingSlot.is_active.is_(True),
               VehicleType.is_active.is_(True))
        .group_by(VehicleType.id, VehicleType.name).order_by(VehicleType.id)).all()
    return [{"id": row[0], "name": row[1], "slot_count": row[2]} for row in rows]


def published_plans(db: Session, site_id: int):
    rows = db.execute(select(SubscriptionPlan, VehicleType.name).join(VehicleType, VehicleType.id == SubscriptionPlan.vehicle_type_id)
        .where(SubscriptionPlan.site_id == site_id, SubscriptionPlan.is_active.is_(True), VehicleType.is_active.is_(True))
        .order_by(SubscriptionPlan.product_kind, SubscriptionPlan.vehicle_type_id, SubscriptionPlan.price)).all()
    return [{"id": plan.id, "name": plan.name, "product_kind": plan.product_kind, "vehicle_type_id": plan.vehicle_type_id,
        "vehicle_type_name": type_name, "duration_days": plan.duration_days, "duration_minutes": plan.duration_minutes,
        "price": plan.price} for plan, type_name in rows]


def walk_in_rates(db: Session, vehicle_type_ids):
    """The active tariff per served vehicle type; the same table staff quote at the gate."""
    if not vehicle_type_ids:
        return []
    rows = db.execute(select(PriceConfig, VehicleType.name).join(VehicleType, VehicleType.id == PriceConfig.vehicle_type_id)
        .where(PriceConfig.is_active.is_(True), PriceConfig.vehicle_type_id.in_(vehicle_type_ids))
        .order_by(PriceConfig.vehicle_type_id)).all()
    return [{"vehicle_type_id": rate.vehicle_type_id, "vehicle_type_name": type_name, "ticket_type": rate.ticket_type,
        "price": rate.price, "effective_date": rate.effective_date} for rate, type_name in rows]


def capacity_summary(db: Session, site_id: int):
    zones = db.scalar(select(func.count(Zone.id)).where(Zone.site_id == site_id, Zone.is_active.is_(True))) or 0
    slots = db.scalar(select(func.count(ParkingSlot.id)).join(Zone, Zone.id == ParkingSlot.zone_id)
        .where(Zone.site_id == site_id, Zone.is_active.is_(True), ParkingSlot.is_active.is_(True))) or 0
    return {"zones": zones, "slots": slots}


def public_profile(db: Session, site: ParkingSite, *, catalog: bool = True):
    from expansion.online_payment_service import available_payment_modes
    types = served_vehicle_types(db, site.id) if catalog else []
    data = {
        "id": site.id,
        "name": site.name,
        "address": site.address or None,
        "description": site.public_description,
        "opening_hours": site.public_opening_hours,
        "contact": {"phone": site.public_contact_phone, "email": site.public_contact_email},
        "location": {"latitude": site.latitude, "longitude": site.longitude}
            if site.latitude is not None and site.longitude is not None else None,
        "profile_updated_at": _aware(site.public_profile_updated_at),
        "demo_labeled": bool(settings.PARKINGAI_SHOWCASE_MODE),
    }
    if catalog:
        data.update({
            "vehicle_types": types,
            "plans": published_plans(db, site.id),
            "walk_in_rates": walk_in_rates(db, [row["id"] for row in types]),
            "capacity": capacity_summary(db, site.id),
            "payment_modes": available_payment_modes(site.id, PortalSettings().DEMO_PAYMENTS_ENABLED),
            "booking_mode": site.customer_booking_mode,
        })
    return data


def _active_site(db: Session, site_id: int) -> ParkingSite:
    site = db.get(ParkingSite, site_id)
    if site is None or not site.is_active:
        raise HTTPException(404, "Không tìm thấy bãi đang hoạt động.")
    return site


@router.get("/public/sites")
def public_sites(db: Session = Depends(get_db)):
    """Minimal directory: names and addresses of active lots, nothing operational."""
    rows = db.scalars(select(ParkingSite).where(ParkingSite.is_active.is_(True)).order_by(ParkingSite.id))
    return {"items": [public_profile(db, row, catalog=False) for row in rows]}


@router.get("/public/sites/{site_id}")
def public_site(site_id: int, db: Session = Depends(get_db)):
    return public_profile(db, _active_site(db, site_id))


@router.get("/sites/{site_id}/public-profile")
def read_public_profile(site_id: int, db: Session = Depends(get_db), actor: User = Depends(get_current_user)):
    site = require_site_access(db, actor, site_id, "staff")
    return {**public_profile(db, site), "can_edit": _can_edit(db, actor, site_id),
        "updated_by_id": site.public_profile_updated_by_id}


def _can_edit(db, actor, site_id):
    try:
        require_site_access(db, actor, site_id, "manager")
    except HTTPException:
        return False
    return True


@router.put("/sites/{site_id}/public-profile")
def update_public_profile(site_id: int, body: PublicProfileUpdate, db: Session = Depends(get_db),
                          actor: User = Depends(get_current_user)):
    # Object-level authorization: membership as manager of THIS site (or global admin).
    site = require_site_access(db, actor, site_id, "manager")
    site.address = body.address
    site.public_description = body.description
    site.public_opening_hours = body.opening_hours
    site.public_contact_phone = body.contact_phone
    site.public_contact_email = str(body.contact_email) if body.contact_email else None
    site.latitude, site.longitude = body.latitude, body.longitude
    site.public_profile_updated_at = business_now()
    site.public_profile_updated_by_id = actor.id
    db.commit()
    db.refresh(site)
    return {**public_profile(db, site), "can_edit": True, "updated_by_id": site.public_profile_updated_by_id}
