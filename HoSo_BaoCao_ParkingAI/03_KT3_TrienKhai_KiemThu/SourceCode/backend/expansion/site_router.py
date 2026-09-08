"""Scoped operations. The unscoped legacy API is restricted separately at app entry."""
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError, OperationalError
from sqlalchemy.orm import Session
from typing import Literal

from database import get_db
from expansion import reservations as booking
from expansion.site_models import (FleetVehicle, GuaranteedAllocation, Organization, OrganizationMembership,
                                   ParkingReservation, ParkingSite, SiteMembership, SiteWaitlist)
from expansion.site_schemas import (AllocationCreate, BookingWindow, FleetVehicleCreate, OrganizationCreate,
                                    OrganizationMemberCreate, ReservationCreate, SiteCheckIn, SiteCreate, SiteMemberCreate,
                                    SiteZoneCreate, SiteSlotCreate)
from expansion.site_scope import allowed_site_ids, is_global_admin, require_public_site, require_site_access
from expansion import site_service
from models.parking_slot import ParkingSlot
from models.user import User
from models.vehicle import Vehicle
from models.zone import Zone
from schemas.checkout import CheckoutConfirmation, CheckoutQuoteResponse
from services.auth_service import get_current_user

router = APIRouter(prefix="/api/v2", tags=["Sites and reservations"])


def _save(db, action):
    try:
        result = action()
        db.commit()
        return booking.serialize(result)
    except HTTPException:
        db.rollback()
        raise
    except (IntegrityError, OperationalError) as exc:
        db.rollback()
        raise HTTPException(409, "Dữ liệu vừa thay đổi hoặc mã yêu cầu đã được sử dụng. Hãy tải lại.") from exc


def _record(db, model, record_id, site_id=None):
    row = db.get(model, record_id)
    if row is None or (site_id is not None and row.site_id != site_id):
        raise HTTPException(404, "Không tìm thấy bản ghi.")
    return row


PageLimit = Query(50, ge=1, le=100)
PageOffset = Query(0, ge=0)
ReservationStatus = Literal["confirmed", "arrived", "cancelled", "expired"]
AllocationStatus = Literal["active", "cancelled"]
WaitlistStatus = Literal["waiting", "offered", "cancelled"]


def _booking_page(db, query, model, *, status, from_at, to_at, limit, offset, order=None):
    """Authorization and scope predicates are applied by the caller before this page filter.

    Rows overlapping [from_at, to_at) are kept so a booking that started earlier but is
    still running in the window is not dropped. `id` breaks ties for equal timestamps.
    """
    from_at = booking.local_time(from_at) if from_at is not None else None
    to_at = booking.local_time(to_at) if to_at is not None else None
    if from_at is not None and to_at is not None and to_at <= from_at:
        raise HTTPException(422, "Thời điểm kết thúc bộ lọc phải sau thời điểm bắt đầu.")
    if status:
        query = query.where(model.status == status)
    if from_at is not None:
        query = query.where(model.end_at > from_at)
    if to_at is not None:
        query = query.where(model.start_at < to_at)
    order = order or (model.start_at.desc(), model.id.desc())
    return [booking.serialize(row) for row in db.scalars(query.order_by(*order).offset(offset).limit(limit))]


@router.get("/sites")
def sites(db: Session = Depends(get_db), actor: User = Depends(get_current_user)):
    # Public fields only. A customer needs a catalog to choose a parking site.
    query = select(ParkingSite).where(ParkingSite.is_active.is_(True)).order_by(ParkingSite.id)
    if actor.role.name != "customer":
        query = query.where(ParkingSite.id.in_(allowed_site_ids(db, actor)))
    memberships = dict(db.execute(select(SiteMembership.site_id, SiteMembership.role).where(
        SiteMembership.user_id == actor.id)).all())
    result = []
    for row in db.scalars(query):
        data = booking.serialize(row)
        if actor.role.name != "customer":
            data["role"] = "admin" if is_global_admin(actor) else memberships.get(row.id, "staff")
        result.append(data)
    return result


@router.post("/sites", status_code=201)
def create_site(body: SiteCreate, db: Session = Depends(get_db), actor: User = Depends(get_current_user)):
    return _save(db, lambda: site_service.create_site(db, actor, body))


@router.get("/sites/{site_id}/availability")
def site_availability(site_id: int, db: Session = Depends(get_db), actor: User = Depends(get_current_user)):
    if actor.role.name != "customer":
        require_site_access(db, actor, site_id)
    return site_service.availability(db, site_id)


@router.get("/sites/{site_id}/zones")
def site_zones(site_id: int, db: Session = Depends(get_db), actor: User = Depends(get_current_user)):
    require_site_access(db, actor, site_id)
    return [booking.serialize(row) for row in db.scalars(select(Zone).where(Zone.site_id == site_id).order_by(Zone.id))]


@router.get("/sites/{site_id}/vehicles")
def bookable_vehicles(site_id: int, q: str = Query("", max_length=20), limit: int = Query(20, ge=1, le=100),
                      db: Session = Depends(get_db), actor: User = Depends(get_current_user)):
    require_site_access(db, actor, site_id)
    # Customers and vehicles belong to the single operator. This staff catalog
    # exposes only identity needed for booking, never customer contact/history.
    query = select(Vehicle).where(Vehicle.customer_id.is_not(None))
    if q.strip():
        query = query.where(Vehicle.license_plate.contains(q.strip().upper(), autoescape=True))
    return [{"id": row.id, "license_plate": row.license_plate, "vehicle_type_id": row.vehicle_type_id}
            for row in db.scalars(query.order_by(Vehicle.license_plate).limit(limit))]


@router.post("/sites/{site_id}/zones", status_code=201)
def create_site_zone(site_id: int, body: SiteZoneCreate, db: Session = Depends(get_db), actor: User = Depends(get_current_user)):
    require_site_access(db, actor, site_id, "manager")
    from crud.zone import get_zone_by_name
    if get_zone_by_name(db, body.name):
        raise HTTPException(409, "Tên khu vực đã tồn tại trong hệ thống. Hãy thêm tên bãi vào tên khu vực.")
    def create():
        row = Zone(site_id=site_id, **body.model_dump())
        db.add(row)
        db.flush()
        return row
    return _save(db, create)


@router.post("/sites/{site_id}/slots", status_code=201)
def create_site_slot(site_id: int, body: SiteSlotCreate, db: Session = Depends(get_db), actor: User = Depends(get_current_user)):
    require_site_access(db, actor, site_id, "manager")
    from crud.parking_slot import get_parking_slot_by_name, count_parking_slots_by_zone
    from models.vehicle_type import VehicleType
    def create():
        zone = db.scalar(select(Zone).where(Zone.id == body.zone_id, Zone.site_id == site_id).with_for_update())
        if zone is None or not zone.is_active:
            raise HTTPException(404, "Không tìm thấy khu vực đang hoạt động tại bãi này.")
        vehicle_type = db.get(VehicleType, body.vehicle_type_id)
        if vehicle_type is None or not vehicle_type.is_active:
            raise HTTPException(404, "Không tìm thấy loại xe đang hoạt động.")
        if get_parking_slot_by_name(db, body.slot_name):
            raise HTTPException(409, "Mã vị trí đã tồn tại trong hệ thống.")
        if count_parking_slots_by_zone(db, zone.id) >= zone.capacity:
            raise HTTPException(409, "Khu vực đã đạt sức chứa tối đa.")
        row = ParkingSlot(**body.model_dump())
        db.add(row)
        db.flush()
        return row
    return _save(db, create)


@router.get("/sites/{site_id}/members")
def members(site_id: int, db: Session = Depends(get_db), actor: User = Depends(get_current_user)):
    require_site_access(db, actor, site_id, "manager")
    return [booking.serialize(row) for row in db.scalars(select(SiteMembership).where(SiteMembership.site_id == site_id))]


@router.post("/sites/{site_id}/members")
def add_member(site_id: int, body: SiteMemberCreate, db: Session = Depends(get_db), actor: User = Depends(get_current_user)):
    return _save(db, lambda: site_service.set_member(db, actor, site_id, body))


@router.delete("/sites/{site_id}/members/{user_id}", status_code=204)
def remove_member(site_id: int, user_id: int, db: Session = Depends(get_db), actor: User = Depends(get_current_user)):
    if not is_global_admin(actor):
        raise HTTPException(403, "Chỉ quản trị viên hệ thống được thu hồi quyền theo bãi.")
    require_public_site(db, site_id)
    row = db.scalar(select(SiteMembership).where(SiteMembership.site_id == site_id, SiteMembership.user_id == user_id))
    if row:
        db.delete(row)
        db.commit()


@router.get("/sites/{site_id}/sessions")
def sessions(site_id: int, limit: int = Query(100, ge=1, le=100), offset: int = Query(0, ge=0),
             license_plate: str | None = Query(None, max_length=20), status: Literal["active", "completed"] | None = None,
             db: Session = Depends(get_db), actor: User = Depends(get_current_user)):
    return site_service.site_sessions(db, actor, site_id, limit=limit, offset=offset,
                                      license_plate=license_plate, status=status)


@router.post("/sites/{site_id}/check-in", status_code=201)
def check_in(site_id: int, body: SiteCheckIn, db: Session = Depends(get_db), actor: User = Depends(get_current_user)):
    require_site_access(db, actor, site_id)
    slot = db.scalar(select(ParkingSlot).join(Zone).where(ParkingSlot.id == body.parking_slot_id, Zone.site_id == site_id))
    if slot is None:
        raise HTTPException(404, "Vị trí không thuộc bãi này.")
    from services.parking_service import ParkingService
    return ParkingService(db).check_in(body.license_plate, body.vehicle_type_id, actor.id,
                                      parking_slot_id=slot.id, _expected_site_id=site_id)


@router.get("/sites/{site_id}/sessions/{session_id}/checkout-quote", response_model=CheckoutQuoteResponse)
def checkout_quote(site_id: int, session_id: str, response: Response,
                   db: Session = Depends(get_db), actor: User = Depends(get_current_user)):
    site_service.scoped_session(db, actor, site_id, session_id)
    from services.checkout_service import CheckoutService
    response.headers["Cache-Control"] = "no-store"
    return CheckoutService(db).quote(session_id, actor.id)


@router.put("/sites/{site_id}/sessions/{session_id}/check-out")
def checkout(site_id: int, session_id: str, body: CheckoutConfirmation,
             db: Session = Depends(get_db), actor: User = Depends(get_current_user)):
    site_service.scoped_session(db, actor, site_id, session_id)
    from services.checkout_service import CheckoutService
    return booking.serialize(CheckoutService(db).confirm(body, actor.id, session_id=session_id))


@router.get("/me/reservations")
def my_reservations(site_id: int | None = Query(None, gt=0), status: ReservationStatus | None = None,
                    from_at: datetime | None = None, to_at: datetime | None = None,
                    limit: int = PageLimit, offset: int = PageOffset,
                    db: Session = Depends(get_db), actor: User = Depends(get_current_user)):
    from expansion.portal_service import get_linked_customer
    owner = get_linked_customer(db, actor)
    query = select(ParkingReservation).where(ParkingReservation.customer_id == owner.id)
    if site_id is not None:
        query = query.where(ParkingReservation.site_id == site_id)
    return _booking_page(db, query, ParkingReservation, status=status, from_at=from_at, to_at=to_at, limit=limit, offset=offset)


@router.post("/me/reservations", status_code=201)
def my_reserve(body: ReservationCreate, db: Session = Depends(get_db), actor: User = Depends(get_current_user)):
    return _save(db, lambda: booking.reserve(db, actor, body, customer=True))


@router.post("/me/reservations/{reservation_id}/cancel")
def my_cancel(reservation_id: str, db: Session = Depends(get_db), actor: User = Depends(get_current_user)):
    return _save(db, lambda: booking.cancel(db, actor, _record(db, ParkingReservation, reservation_id), customer=True))


@router.get("/sites/{site_id}/reservations")
def site_reservations(site_id: int, status: ReservationStatus | None = None, vehicle_id: int | None = Query(None, gt=0),
                      from_at: datetime | None = None, to_at: datetime | None = None,
                      limit: int = PageLimit, offset: int = PageOffset,
                      db: Session = Depends(get_db), actor: User = Depends(get_current_user)):
    require_site_access(db, actor, site_id)
    query = select(ParkingReservation).where(ParkingReservation.site_id == site_id)
    if vehicle_id is not None:
        query = query.where(ParkingReservation.vehicle_id == vehicle_id)
    return _booking_page(db, query, ParkingReservation, status=status, from_at=from_at, to_at=to_at, limit=limit, offset=offset)


@router.post("/sites/{site_id}/reservations", status_code=201)
def site_reserve(site_id: int, body: ReservationCreate, db: Session = Depends(get_db), actor: User = Depends(get_current_user)):
    if body.site_id != site_id:
        raise HTTPException(422, "Bãi trong nội dung không khớp URL.")
    return _save(db, lambda: booking.reserve(db, actor, body))


@router.post("/sites/{site_id}/reservations/{reservation_id}/cancel")
def site_cancel(site_id: int, reservation_id: str, db: Session = Depends(get_db), actor: User = Depends(get_current_user)):
    require_site_access(db, actor, site_id)
    return _save(db, lambda: booking.cancel(db, actor, _record(db, ParkingReservation, reservation_id, site_id)))


@router.post("/sites/{site_id}/reservations/{reservation_id}/arrive")
def site_arrive(site_id: int, reservation_id: str, db: Session = Depends(get_db), actor: User = Depends(get_current_user)):
    require_site_access(db, actor, site_id)
    return _save(db, lambda: booking.arrive(db, actor, _record(db, ParkingReservation, reservation_id, site_id)))


@router.post("/sites/{site_id}/reservations/expire")
def expire(site_id: int, db: Session = Depends(get_db), actor: User = Depends(get_current_user)):
    require_site_access(db, actor, site_id)
    from crud.parking_session import server_now
    now, count = server_now(), 0
    for slot_id in db.scalars(select(ParkingSlot.id).join(Zone).where(Zone.site_id == site_id).order_by(ParkingSlot.id)):
        booking.lock_slot(db, slot_id)
        count += booking.expire_slot(db, slot_id, now)
    db.commit()
    return {"expired": count}


@router.get("/sites/{site_id}/allocations")
def allocations(site_id: int, status: AllocationStatus | None = None, vehicle_id: int | None = Query(None, gt=0),
                from_at: datetime | None = None, to_at: datetime | None = None,
                limit: int = PageLimit, offset: int = PageOffset,
                db: Session = Depends(get_db), actor: User = Depends(get_current_user)):
    require_site_access(db, actor, site_id)
    query = select(GuaranteedAllocation).where(GuaranteedAllocation.site_id == site_id)
    if vehicle_id is not None:
        query = query.where(GuaranteedAllocation.vehicle_id == vehicle_id)
    return _booking_page(db, query, GuaranteedAllocation, status=status, from_at=from_at, to_at=to_at, limit=limit, offset=offset)


@router.post("/sites/{site_id}/allocations", status_code=201)
def allocate(site_id: int, body: AllocationCreate, db: Session = Depends(get_db), actor: User = Depends(get_current_user)):
    if body.site_id != site_id:
        raise HTTPException(422, "Bãi trong nội dung không khớp URL.")
    return _save(db, lambda: booking.reserve(db, actor, body, allocation=True))


@router.post("/sites/{site_id}/allocations/{allocation_id}/cancel")
def cancel_allocation(site_id: int, allocation_id: str, db: Session = Depends(get_db), actor: User = Depends(get_current_user)):
    require_site_access(db, actor, site_id, "manager")
    return _save(db, lambda: booking.cancel(db, actor, _record(db, GuaranteedAllocation, allocation_id, site_id)))


@router.get("/sites/{site_id}/waitlist")
def waitlist(site_id: int, status: WaitlistStatus | None = None, from_at: datetime | None = None, to_at: datetime | None = None,
             limit: int = PageLimit, offset: int = PageOffset,
             db: Session = Depends(get_db), actor: User = Depends(get_current_user)):
    require_site_access(db, actor, site_id)
    # Queue order: earliest request first, so offers follow arrival of the request.
    query = select(SiteWaitlist).where(SiteWaitlist.site_id == site_id)
    return _booking_page(db, query, SiteWaitlist, status=status, from_at=from_at, to_at=to_at, limit=limit, offset=offset,
                         order=(SiteWaitlist.created_at.asc(), SiteWaitlist.id.asc()))


@router.post("/sites/{site_id}/waitlist", status_code=201)
def join_site_waitlist(site_id: int, body: BookingWindow, db: Session = Depends(get_db), actor: User = Depends(get_current_user)):
    if body.site_id != site_id:
        raise HTTPException(422, "Bãi trong nội dung không khớp URL.")
    return _save(db, lambda: booking.join_waitlist(db, actor, body))


@router.get("/me/waitlist")
def my_waitlist(site_id: int | None = Query(None, gt=0), status: WaitlistStatus | None = None,
                from_at: datetime | None = None, to_at: datetime | None = None,
                limit: int = PageLimit, offset: int = PageOffset,
                db: Session = Depends(get_db), actor: User = Depends(get_current_user)):
    from expansion.portal_service import get_linked_customer
    owner = get_linked_customer(db, actor)
    query = select(SiteWaitlist).where(SiteWaitlist.customer_id == owner.id)
    if site_id is not None:
        query = query.where(SiteWaitlist.site_id == site_id)
    return _booking_page(db, query, SiteWaitlist, status=status, from_at=from_at, to_at=to_at, limit=limit, offset=offset,
                         order=(SiteWaitlist.created_at.desc(), SiteWaitlist.id.desc()))


@router.post("/me/waitlist", status_code=201)
def join_my_waitlist(body: BookingWindow, db: Session = Depends(get_db), actor: User = Depends(get_current_user)):
    return _save(db, lambda: booking.join_waitlist(db, actor, body, customer=True))


@router.post("/sites/{site_id}/waitlist/{waitlist_id}/offer")
def offer(site_id: int, waitlist_id: str, db: Session = Depends(get_db), actor: User = Depends(get_current_user)):
    require_site_access(db, actor, site_id)
    return _save(db, lambda: booking.offer_waitlist(db, actor, _record(db, SiteWaitlist, waitlist_id, site_id)))


@router.post("/sites/{site_id}/waitlist/{waitlist_id}/cancel")
def cancel_site_waitlist(site_id: int, waitlist_id: str, db: Session = Depends(get_db), actor: User = Depends(get_current_user)):
    require_site_access(db, actor, site_id)
    return _save(db, lambda: booking.cancel_waitlist(db, actor, _record(db, SiteWaitlist, waitlist_id, site_id)))


@router.post("/me/waitlist/{waitlist_id}/cancel")
def cancel_my_waitlist(waitlist_id: str, db: Session = Depends(get_db), actor: User = Depends(get_current_user)):
    return _save(db, lambda: booking.cancel_waitlist(db, actor, _record(db, SiteWaitlist, waitlist_id), customer=True))


@router.get("/sites/{site_id}/organizations")
def organizations(site_id: int, db: Session = Depends(get_db), actor: User = Depends(get_current_user)):
    require_site_access(db, actor, site_id)
    return [booking.serialize(row) for row in db.scalars(select(Organization).where(Organization.site_id == site_id))]


@router.get("/me/organizations")
def my_organizations(db: Session = Depends(get_db), actor: User = Depends(get_current_user)):
    return [booking.serialize(row) for row in db.scalars(select(Organization).join(OrganizationMembership).where(
        OrganizationMembership.user_id == actor.id, Organization.is_active.is_(True)))]


@router.post("/sites/{site_id}/organizations", status_code=201)
def create_organization(site_id: int, body: OrganizationCreate, db: Session = Depends(get_db), actor: User = Depends(get_current_user)):
    require_site_access(db, actor, site_id, "manager")
    def create():
        row = Organization(site_id=site_id, name=body.name)
        db.add(row)
        db.flush()
        return row
    return _save(db, create)


@router.get("/organizations/{organization_id}/fleet")
def fleet(organization_id: int, limit: int = PageLimit, offset: int = PageOffset,
          db: Session = Depends(get_db), actor: User = Depends(get_current_user)):
    return site_service.fleet_summary(db, actor, organization_id, limit=limit, offset=offset)


@router.post("/organizations/{organization_id}/members")
def fleet_member(organization_id: int, body: OrganizationMemberCreate,
                 db: Session = Depends(get_db), actor: User = Depends(get_current_user)):
    site_service.require_organization(db, actor, organization_id, manage=True)
    user = db.get(User, body.user_id)
    if user is None or not user.is_active:
        raise HTTPException(404, "Không tìm thấy tài khoản đang hoạt động.")
    def create():
        row = db.scalar(select(OrganizationMembership).where(OrganizationMembership.organization_id == organization_id,
                                                            OrganizationMembership.user_id == body.user_id))
        if row is None:
            row = OrganizationMembership(organization_id=organization_id, user_id=body.user_id)
            db.add(row)
            db.flush()
        return row
    return _save(db, create)


@router.post("/organizations/{organization_id}/fleet", status_code=201)
def add_fleet_vehicle(organization_id: int, body: FleetVehicleCreate,
                     db: Session = Depends(get_db), actor: User = Depends(get_current_user)):
    site_service.require_organization(db, actor, organization_id, manage=True)
    if db.get(Vehicle, body.vehicle_id) is None:
        raise HTTPException(404, "Không tìm thấy xe.")
    def create():
        row = db.scalar(select(FleetVehicle).where(FleetVehicle.organization_id == organization_id,
                                                  FleetVehicle.vehicle_id == body.vehicle_id))
        if row is None:
            row = FleetVehicle(organization_id=organization_id, vehicle_id=body.vehicle_id)
            db.add(row)
            db.flush()
        return row
    return _save(db, create)


@router.delete("/organizations/{organization_id}/members/{user_id}", status_code=204)
def remove_fleet_member(organization_id: int, user_id: int, db: Session = Depends(get_db), actor: User = Depends(get_current_user)):
    site_service.require_organization(db, actor, organization_id, manage=True)
    row = db.scalar(select(OrganizationMembership).where(OrganizationMembership.organization_id == organization_id,
                                                        OrganizationMembership.user_id == user_id))
    if row:
        db.delete(row)
        db.commit()


@router.delete("/organizations/{organization_id}/fleet/{vehicle_id}", status_code=204)
def remove_fleet_vehicle(organization_id: int, vehicle_id: int, db: Session = Depends(get_db), actor: User = Depends(get_current_user)):
    site_service.require_organization(db, actor, organization_id, manage=True)
    row = db.scalar(select(FleetVehicle).where(FleetVehicle.organization_id == organization_id, FleetVehicle.vehicle_id == vehicle_id))
    if row:
        db.delete(row)
        db.commit()
