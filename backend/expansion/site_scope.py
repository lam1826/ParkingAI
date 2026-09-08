"""Object-level site authorization shared by portal, camera and operations."""
from fastapi import HTTPException
from sqlalchemy import select

from expansion.site_models import ParkingSite, SiteMembership
from models.zone import Zone


def is_global_admin(user):
    return bool(user.is_active and user.role and user.role.name == "admin")


def allowed_site_ids(db, user):
    """Return a SQL SELECT usable in IN predicates; never infer access from role alone."""
    query = select(ParkingSite.id).where(ParkingSite.is_active.is_(True))
    if is_global_admin(user):
        return query
    if not user.is_active or not user.role or user.role.name not in {"staff", "manager"}:
        return query.where(False)
    return query.where(ParkingSite.id.in_(select(SiteMembership.site_id).where(SiteMembership.user_id == user.id)))


def scoped_zone_ids(db, user):
    return select(Zone.id).where(Zone.site_id.in_(allowed_site_ids(db, user)))


def require_site_access(db, user, site_id, minimum_role="staff"):
    if minimum_role not in {"staff", "manager"}:
        raise ValueError("Unsupported site role")
    site = db.get(ParkingSite, site_id)
    if site is None or not site.is_active:
        raise HTTPException(404, "Không tìm thấy bãi đang hoạt động.")
    if is_global_admin(user):
        return site
    if not user.is_active or not user.role or user.role.name not in {"staff", "manager"}:
        raise HTTPException(403, "Bạn không có quyền vận hành bãi này.")
    if minimum_role == "manager" and user.role.name != "manager":
        raise HTTPException(403, "Tài khoản không còn quyền quản lý. Hãy liên hệ quản trị viên.")
    membership = db.scalar(select(SiteMembership).where(
        SiteMembership.site_id == site_id, SiteMembership.user_id == user.id,
    ))
    if membership is None or (minimum_role == "manager" and membership.role != "manager"):
        raise HTTPException(403, "Bạn không có quyền thực hiện thao tác tại bãi này.")
    return site


def require_public_site(db, site_id):
    site = db.get(ParkingSite, site_id)
    if site is None or not site.is_active:
        raise HTTPException(404, "Không tìm thấy bãi đang hoạt động.")
    return site
