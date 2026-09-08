"""Customer-only resources and explicit manager review endpoints (prefix /api/v2)."""
from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy import select, cast, String, or_

from database import get_db
from services.auth_service import get_current_user, RoleChecker
from services.payment_service import PaymentService
from core.clock import business_now
from expansion import portal_service as service
from expansion.portal_models import (
    PortalAccountLink, PortalLinkRequest, PortalVehicleRequest, PortalVehicleOwnership, PortalSessionGrant,
    SubscriptionPlan, PortalOrder, PortalNotification, PortalRefundRequest,
)
from expansion.portal_schemas import (
    ProfileCreate, LinkRequest, VehicleRequest, PlanCreate, OrderCreate,
    Simulation, Resolution, ManualCollection, RefundCreate, PlanUpdate,
)
from expansion.site_models import ParkingSite
from expansion.site_scope import allowed_site_ids
from models.customer import Customer
from models.vehicle import Vehicle
from models.vehicle_type import VehicleType
from models.parking_session import ParkingSession
from models.monthly_pass import MonthlyPass
from models.payment import Payment
from models.parking_slot import ParkingSlot
from models.zone import Zone
from models.user import User

router = APIRouter(tags=["Customer portal / DEMO payments"])
manager = RoleChecker("manager")
admin = RoleChecker("admin")


def fields(row, *names):
    return {name: getattr(row, name) for name in names}


def write(db, operation):
    try:
        result = operation()
        # Several idempotent service branches return an existing row after a
        # SQLite no-op lock. End that transaction before middleware/audit or
        # another writer needs the database.
        db.commit()
        return result
    except Exception:
        db.rollback()
        raise


def location(db, session):
    slot = db.get(ParkingSlot, session.parking_slot_id) if session.parking_slot_id else None
    zone = db.get(Zone, slot.zone_id) if slot else None
    return {"slot_name": slot.slot_name if slot else None, "zone_name": zone.name if zone else None}


@router.get("/me/profile")
def profile(db=Depends(get_db), user=Depends(get_current_user)):
    customer = db.scalar(select(Customer).join(PortalAccountLink,
        PortalAccountLink.customer_id == Customer.id).where(PortalAccountLink.user_id == user.id))
    return {"linked": customer is not None, "customer": fields(customer, "id", "full_name", "phone_number", "email") if customer else None}


@router.post("/me/profile")
def profile_create(data: ProfileCreate, db=Depends(get_db), user=Depends(get_current_user)):
    customer = write(db, lambda: service.create_profile(db, user, data))
    return {"linked": True, "customer": fields(customer, "id", "full_name", "phone_number", "email")}


@router.post("/me/link-requests")
def link_request(data: LinkRequest, db=Depends(get_db), user=Depends(get_current_user)):
    row = write(db, lambda: service.request_link(db, user, data))
    return fields(row, "id", "status", "created_at")


@router.get("/me/link-requests")
def links(db=Depends(get_db), user=Depends(get_current_user)):
    return {"items": [fields(row, "id", "status", "created_at") for row in db.scalars(
        select(PortalLinkRequest).where(PortalLinkRequest.user_id == user.id).order_by(PortalLinkRequest.created_at.desc()).limit(100))]}


@router.get("/catalog/vehicle-types")
def vehicle_types(db=Depends(get_db), user=Depends(get_current_user)):
    return {"items": [fields(row, "id", "name") for row in db.scalars(select(VehicleType).where(VehicleType.is_active.is_(True)).order_by(VehicleType.id))]}


@router.post("/me/vehicle-requests")
def vehicle_request(data: VehicleRequest, db=Depends(get_db), user=Depends(get_current_user)):
    row = write(db, lambda: service.request_vehicle(db, user, data))
    return fields(row, "id", "status", "license_plate", "vehicle_type_id", "created_at")


@router.get("/me/vehicle-requests")
def vehicle_requests(db=Depends(get_db), user=Depends(get_current_user)):
    customer = service.get_linked_customer(db, user)
    return {"items": [fields(row, "id", "status", "license_plate", "vehicle_type_id", "note", "created_at") for row in db.scalars(
        select(PortalVehicleRequest).where(PortalVehicleRequest.customer_id == customer.id).order_by(PortalVehicleRequest.created_at.desc()).limit(100))]}


@router.get("/me/vehicles")
def vehicles(db=Depends(get_db), user=Depends(get_current_user)):
    customer = service.get_linked_customer(db, user)
    rows = db.scalars(select(Vehicle).join(PortalVehicleOwnership, PortalVehicleOwnership.vehicle_id == Vehicle.id).where(
        Vehicle.customer_id == customer.id, PortalVehicleOwnership.customer_id == customer.id).order_by(Vehicle.id))
    items = []
    for row in rows:
        item = {**fields(row, "id", "license_plate", "vehicle_type_id"), "type_name": row.vehicle_type.name}
        active = db.scalar(select(ParkingSession).join(PortalSessionGrant,
            PortalSessionGrant.parking_session_id == ParkingSession.id).where(
            ParkingSession.vehicle_id == row.id, ParkingSession.status.in_(["active", "checking_out"]),
            PortalSessionGrant.customer_id == customer.id).limit(1))
        item.update(location(db, active) if active else {"slot_name": None, "zone_name": None})
        item["current_session_id"] = active.id if active else None
        item["current_slot"] = item["slot_name"]
        items.append(item)
    return {"items": items}


@router.get("/me/sessions")
def sessions(limit: int = Query(50, ge=1, le=100), offset: int = Query(0, ge=0), db=Depends(get_db), user=Depends(get_current_user)):
    customer = service.get_linked_customer(db, user)
    rows = db.scalars(select(ParkingSession).join(PortalSessionGrant,
        PortalSessionGrant.parking_session_id == ParkingSession.id).where(PortalSessionGrant.customer_id == customer.id)
        .order_by(ParkingSession.check_in_time.desc(), ParkingSession.id).offset(offset).limit(limit))
    return {"items": [{**fields(row, "id", "vehicle_id", "parking_slot_id", "check_in_time", "check_out_time", "parking_fee", "status"),
        "license_plate": db.get(Vehicle, row.vehicle_id).license_plate, **location(db, row)} for row in rows],
        "history_note": "Chỉ hiển thị lượt được xác nhận quyền sở hữu tại thời điểm xe vào; không tự cấp quyền cho lịch sử cũ."}


@router.get("/me/passes")
def passes(limit: int = Query(50, ge=1, le=100), offset: int = Query(0, ge=0), db=Depends(get_db), user=Depends(get_current_user)):
    customer = service.get_linked_customer(db, user)
    rows = db.scalars(select(MonthlyPass).where(MonthlyPass.customer_id == customer.id).order_by(MonthlyPass.start_date.desc(), MonthlyPass.id.desc()).offset(offset).limit(limit))
    return {"items": [{**fields(row, "id", "vehicle_id", "card_code", "price", "start_date", "end_date", "is_active"),
        "license_plate": db.get(Vehicle, row.vehicle_id).license_plate} for row in rows]}


@router.get("/plans")
def plans(db=Depends(get_db), user=Depends(get_current_user)):
    rows = db.execute(select(SubscriptionPlan, ParkingSite.name, VehicleType.name).join(ParkingSite,
        ParkingSite.id == SubscriptionPlan.site_id).join(VehicleType, VehicleType.id == SubscriptionPlan.vehicle_type_id)
        .where(SubscriptionPlan.is_active.is_(True), ParkingSite.is_active.is_(True), VehicleType.is_active.is_(True)).order_by(SubscriptionPlan.id))
    return {"items": [{**fields(row, "id", "name", "site_id", "vehicle_type_id", "duration_days", "price"),
        "site_name": site_name, "type_name": type_name} for row, site_name, type_name in rows]}


@router.post("/me/orders")
def order_create(data: OrderCreate, db=Depends(get_db), user=Depends(get_current_user)):
    return service.serialize_order(write(db, lambda: service.create_order(db, user, data)), owner=True)


@router.get("/me/orders")
def orders(limit: int = Query(50, ge=1, le=100), offset: int = Query(0, ge=0), db=Depends(get_db), user=Depends(get_current_user)):
    customer = service.get_linked_customer(db, user)
    rows = db.scalars(select(PortalOrder).where(PortalOrder.user_id == user.id, PortalOrder.customer_id == customer.id)
        .order_by(PortalOrder.created_at.desc(), PortalOrder.id).offset(offset).limit(limit))
    # QR generation is only necessary for the selected order detail.
    return {"items": [service.serialize_order(row) for row in rows]}


@router.get("/me/orders/{identity}")
def order_detail(identity: str, db=Depends(get_db), user=Depends(get_current_user)):
    return service.serialize_order(service.owned_order(db, user, identity), owner=True)


@router.post("/me/orders/{identity}/simulate")
def simulate(identity: str, data: Simulation, db=Depends(get_db), user=Depends(get_current_user)):
    return service.serialize_order(write(db, lambda: service.simulate(db, user, identity, data)), owner=True)


@router.post("/me/orders/{identity}/cancel")
def order_cancel(identity: str, db=Depends(get_db), user=Depends(get_current_user)):
    return service.serialize_order(write(db, lambda: service.cancel_order(db, user, identity)))


@router.get("/me/notifications")
def notifications(limit: int = Query(50, ge=1, le=100), offset: int = Query(0, ge=0), db=Depends(get_db), user=Depends(get_current_user)):
    customer = service.get_linked_customer(db, user)
    rows = db.scalars(select(PortalNotification).where(PortalNotification.customer_id == customer.id)
        .order_by(PortalNotification.created_at.desc(), PortalNotification.id).offset(offset).limit(limit))
    return {"items": [{**fields(row, "id", "message", "created_at", "read_at"),
        "is_read": row.read_at is not None, "title": "Thông báo ParkingAI"} for row in rows]}


@router.post("/me/notifications/{identity}/read")
def notification_read(identity: str, db=Depends(get_db), user=Depends(get_current_user)):
    customer = service.get_linked_customer(db, user)
    row = db.scalar(select(PortalNotification).where(PortalNotification.id == identity, PortalNotification.customer_id == customer.id))
    if row is None:
        raise HTTPException(404, "Không tìm thấy thông báo.")
    if row.read_at is None:
        row.read_at = business_now()
        db.commit()
    return fields(row, "id", "read_at")


@router.get("/me/receipts")
def receipts(limit: int = Query(50, ge=1, le=100), offset: int = Query(0, ge=0), db=Depends(get_db), user=Depends(get_current_user)):
    customer = service.get_linked_customer(db, user)
    own_periods = select(cast(MonthlyPass.id, String)).where(MonthlyPass.customer_id == customer.id)
    own_sessions = select(PortalSessionGrant.parking_session_id).where(PortalSessionGrant.customer_id == customer.id)
    rows = db.scalars(select(Payment).where(or_(
        (Payment.source_type == "monthly_pass") & Payment.source_id.in_(own_periods),
        (Payment.source_type == "parking_session") & Payment.source_id.in_(own_sessions)))
        .order_by(Payment.created_at.desc(), Payment.id).offset(offset).limit(limit))
    return {"items": [{key: value for key, value in PaymentService.serialize(db, row).items()
        if key not in {"collected_by_id", "shift_id"}} for row in rows]}


@router.get("/me/receipts/{identity}/pdf")
def receipt_pdf(identity: str, db=Depends(get_db), user=Depends(get_current_user)):
    customer = service.get_linked_customer(db, user)
    own_periods = select(cast(MonthlyPass.id, String)).where(MonthlyPass.customer_id == customer.id)
    own_sessions = select(PortalSessionGrant.parking_session_id).where(PortalSessionGrant.customer_id == customer.id)
    receipt = db.scalar(select(Payment).where(Payment.id == identity, or_(
        (Payment.source_type == "monthly_pass") & Payment.source_id.in_(own_periods),
        (Payment.source_type == "parking_session") & Payment.source_id.in_(own_sessions))))
    if receipt is None:
        raise HTTPException(404, "Không tìm thấy chứng từ của bạn.")
    from expansion.portal_documents import build_receipt_pdf
    label = "DEMO-" if receipt.method == "demo" else ""
    return Response(build_receipt_pdf(receipt, customer), media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="ParkingAI-{label}{receipt.id}.pdf"',
            "Cache-Control": "private, no-store"})


@router.post("/me/orders/{identity}/refund-requests")
def refund_create(identity: str, data: RefundCreate, db=Depends(get_db), user=Depends(get_current_user)):
    row = write(db, lambda: service.request_refund(db, user, identity, data.reason))
    return fields(row, "id", "order_id", "reason", "status", "created_at")


@router.get("/me/refund-requests")
def refunds(db=Depends(get_db), user=Depends(get_current_user)):
    customer = service.get_linked_customer(db, user)
    rows = db.scalars(select(PortalRefundRequest).where(PortalRefundRequest.customer_id == customer.id).order_by(PortalRefundRequest.created_at.desc()).limit(100))
    return {"items": [fields(row, "id", "order_id", "reason", "status", "note", "created_at", "refund_payment_id") for row in rows]}


@router.get("/portal/admin/link-requests")
def admin_links(db=Depends(get_db), actor=Depends(manager)):
    rows = db.scalars(select(PortalLinkRequest).where(PortalLinkRequest.status == "pending").order_by(PortalLinkRequest.created_at).limit(100))
    return {"items": [{**fields(row, "id", "user_id", "phone_number", "note", "status", "created_at"),
        "username": db.get(User, row.user_id).username,
        "user_full_name": db.get(User, row.user_id).full_name,
        "requester_role": db.get(User, row.user_id).role.name} for row in rows]}


@router.post("/portal/admin/link-requests/{identity}/resolve")
def admin_link_resolve(identity: str, data: Resolution, db=Depends(get_db), actor=Depends(manager)):
    row = write(db, lambda: service.resolve_link(db, actor, identity, data.approve))
    return fields(row, "id", "status")


@router.get("/portal/admin/vehicle-requests")
def admin_vehicles(db=Depends(get_db), actor=Depends(manager)):
    rows = db.scalars(select(PortalVehicleRequest).where(PortalVehicleRequest.status == "pending").order_by(PortalVehicleRequest.created_at).limit(100))
    items = []
    for row in rows:
        link = db.scalar(select(PortalAccountLink).where(PortalAccountLink.customer_id == row.customer_id))
        requester = db.get(User, link.user_id) if link else None
        items.append({**fields(row, "id", "customer_id", "license_plate", "vehicle_type_id", "note", "status", "created_at"),
            "customer_name": db.get(Customer, row.customer_id).full_name,
            "type_name": db.get(VehicleType, row.vehicle_type_id).name,
            "username": requester.username if requester else None,
            "requester_role": requester.role.name if requester else None})
    return {"items": items}


@router.post("/portal/admin/vehicle-requests/{identity}/resolve")
def admin_vehicle_resolve(identity: str, data: Resolution, db=Depends(get_db), actor=Depends(manager)):
    row = write(db, lambda: service.resolve_vehicle(db, actor, identity, data.approve))
    return fields(row, "id", "status")


@router.get("/portal/admin/account-links")
def admin_account_links(db=Depends(get_db), actor=Depends(manager)):
    from expansion.site_scope import is_global_admin
    rows = db.scalars(select(PortalAccountLink).order_by(PortalAccountLink.created_at.desc()).limit(100))
    items = []
    for row in rows:
        user = db.get(User, row.user_id)
        customer = db.get(Customer, row.customer_id)
        items.append({**fields(row, "id", "user_id", "customer_id", "verification", "created_at"),
            "username": user.username,
            "user_full_name": user.full_name,
            "requester_role": user.role.name,
            "customer_name": customer.full_name,
            "phone_number": customer.phone_number,
            "can_unlink": is_global_admin(actor)})
    return {"items": items}


@router.delete("/portal/admin/account-links/{user_id}", status_code=204)
def admin_account_unlink(user_id: int, db=Depends(get_db), actor=Depends(admin)):
    write(db, lambda: service.unlink_account(db, actor, user_id))
    return Response(status_code=204)


@router.post("/portal/admin/plans")
def admin_plan_create(data: PlanCreate, db=Depends(get_db), actor=Depends(manager)):
    row = write(db, lambda: service.create_plan(db, actor, data))
    return fields(row, "id", "name", "site_id", "vehicle_type_id", "duration_days", "price", "is_active")


@router.get("/portal/admin/plans")
def admin_plans(db=Depends(get_db), actor=Depends(manager)):
    from expansion.site_scope import is_global_admin
    query = select(SubscriptionPlan).order_by(SubscriptionPlan.id)
    if not is_global_admin(actor):
        query = query.where(SubscriptionPlan.site_id.in_(allowed_site_ids(db, actor)))
    rows = db.scalars(query)
    return {"items": [{**fields(row, "id", "name", "site_id", "vehicle_type_id", "duration_days", "price", "is_active"),
        "site_name": db.get(ParkingSite, row.site_id).name if row.site_id else None,
        "type_name": db.get(VehicleType, row.vehicle_type_id).name} for row in rows]}


@router.patch("/portal/admin/plans/{identity}")
def admin_plan_update(identity: int, data: PlanUpdate, db=Depends(get_db), actor=Depends(manager)):
    row = write(db, lambda: service.update_plan(db, actor, identity, data))
    return fields(row, "id", "name", "site_id", "vehicle_type_id", "duration_days", "price", "is_active")


@router.get("/portal/admin/orders")
def admin_orders(limit: int = Query(50, ge=1, le=100), offset: int = Query(0, ge=0), db=Depends(get_db), actor=Depends(manager)):
    rows = db.scalars(select(PortalOrder).where(PortalOrder.site_id.in_(allowed_site_ids(db, actor)))
        .order_by(PortalOrder.created_at.desc(), PortalOrder.id).offset(offset).limit(limit))
    return {"items": [{**service.serialize_order(row), "customer_name": db.get(Customer, row.customer_id).full_name,
        "username": db.get(User, row.user_id).username, "license_plate": db.get(Vehicle, row.vehicle_id).license_plate,
        "site_name": db.get(ParkingSite, row.site_id).name} for row in rows]}


@router.post("/portal/admin/orders/{identity}/collect")
def admin_collect(identity: str, data: ManualCollection, db=Depends(get_db), actor=Depends(manager)):
    row = write(db, lambda: service.collect_manual(db, actor, identity, data.payment_method))
    return service.serialize_order(row)


@router.post("/portal/admin/orders/{identity}/review")
def admin_order_review(identity: str, data: Resolution, db=Depends(get_db), actor=Depends(manager)):
    return service.serialize_order(write(db, lambda: service.resolve_review(db, actor, identity, data)))


@router.get("/portal/admin/refund-requests")
def admin_refunds(db=Depends(get_db), actor=Depends(manager)):
    rows = db.scalars(select(PortalRefundRequest).join(PortalOrder, PortalOrder.id == PortalRefundRequest.order_id)
        .where(PortalOrder.site_id.in_(allowed_site_ids(db, actor)))
        .order_by(PortalRefundRequest.created_at.desc()).limit(100))
    return {"items": [{**fields(row, "id", "order_id", "customer_id", "reason", "status", "created_at"),
        "customer_name": db.get(Customer, row.customer_id).full_name} for row in rows]}


@router.post("/portal/admin/refund-requests/{identity}/resolve")
def admin_refund_resolve(identity: str, data: Resolution, db=Depends(get_db), actor=Depends(manager)):
    row = write(db, lambda: service.resolve_refund(db, actor, identity, data))
    return fields(row, "id", "status", "refund_payment_id", "note")
