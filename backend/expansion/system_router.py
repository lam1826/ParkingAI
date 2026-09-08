"""Capabilities and the authorization boundary for legacy global operations."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select

from database import get_db
from core.config import settings
from expansion.gateway import PortalSettings
from expansion.site_models import ParkingSite, SiteMembership
from expansion.site_scope import is_global_admin
from services.auth_service import get_current_user

router = APIRouter(prefix="/api/v2/system", tags=["System capabilities"])


def legacy_workspace_allowed(db, user):
    if is_global_admin(user):
        return True
    if not user.is_active or not user.role or user.role.name not in {"staff", "manager"}:
        return False
    # Include closed sites: historical data must remain scoped as well.
    sites = list(db.scalars(select(ParkingSite).limit(2)))
    if len(sites) > 1:
        return False
    if not sites:  # Compatibility with an as-yet unassigned single-site fixture.
        return True
    membership = db.scalar(select(SiteMembership).where(
        SiteMembership.site_id == sites[0].id, SiteMembership.user_id == user.id,
    ))
    return bool(sites[0].is_active and membership and
                (user.role.name != "manager" or membership.role == "manager"))


def require_legacy_workspace(db=Depends(get_db), user=Depends(get_current_user)):
    if not legacy_workspace_allowed(db, user):
        raise HTTPException(403, "Chức năng toàn hệ thống chỉ dành cho quản trị viên khi có nhiều bãi. Hãy sử dụng mục Vận hành bãi được phân quyền.")
    return user


@router.get("/capabilities")
def capabilities(db=Depends(get_db), user=Depends(get_current_user)):
    return {
        "legacy_workspace_allowed": legacy_workspace_allowed(db, user),
        "demo_payments_enabled": PortalSettings().DEMO_PAYMENTS_ENABLED,
        "scope": "single_operator",
        "camera_confirmation_required": True,
        "site_finance_enabled": True,
        "site_analytics_enabled": True,
        "showcase_mode": settings.PARKINGAI_SHOWCASE_MODE,
    }
