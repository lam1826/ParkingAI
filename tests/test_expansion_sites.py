"""Functional site isolation and physical reservation guarantees (no provider/network)."""
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from core.clock import BUSINESS_TZ
from crud import parking_session as session_crud
from database import get_db
from expansion import reservations as service
from expansion.site_models import (FleetVehicle, Organization, OrganizationMembership, ParkingReservation,
                                   ParkingSite, SiteMembership, SiteWaitlist)
from expansion.portal_models import PortalAccountLink, PortalNotification, PortalVehicleOwnership
from expansion.site_router import router
from expansion.site_schemas import AllocationCreate, BookingWindow, ReservationCreate
from expansion.site_scope import require_site_access
from expansion.site_service import fleet_summary
from models.customer import Customer
from models.parking_session import ParkingSession
from models.monthly_pass import MonthlyPass
from models.parking_slot import ParkingSlot
from models.role import Role
from models.user import User
from models.vehicle import Vehicle
from models.zone import Zone
from schemas.parking_session import ParkingSessionCreate
from schemas.zone import ZoneUpdate
from routers.zone import update_zone
from services.auth_service import get_current_user
from services.parking_service import ParkingService


@pytest.fixture
def env(db_session, test_user, vehicle_type, parking_slot, vehicle, customer, price_config,
        business_reference_now, monkeypatch):
    now = business_reference_now.replace(microsecond=0)
    # This fixture exercises manager operations; the generic test_user fixture
    # is staff. Both account role and site membership must grant management.
    manager_role = db_session.scalar(select(Role).where(Role.name == "manager"))
    if manager_role is None:
        manager_role = Role(name="manager"); db_session.add(manager_role); db_session.flush()
    test_user.role = manager_role
    clock = {"now": now}
    monkeypatch.setattr(session_crud, "server_now", lambda: clock["now"])
    a, b = ParkingSite(name="Bãi A"), ParkingSite(name="Bãi B")
    db_session.add_all([a, b])
    db_session.flush()
    parking_slot.zone.site_id = a.id
    vehicle.customer_id = customer.id
    other = Vehicle(license_plate="51B11111", vehicle_type_id=vehicle_type.id, customer_id=customer.id)
    db_session.add_all([other, SiteMembership(site_id=a.id, user_id=test_user.id, role="manager")])
    customer_role = Role(name="customer")
    db_session.add(customer_role)
    db_session.flush()
    account = User(username="booking-customer", role_id=customer_role.id, full_name="Khách", password_hash="unused")
    stranger = User(username="booking-stranger", role_id=customer_role.id, full_name="Khách khác", password_hash="unused")
    customer2 = Customer(full_name="Khác", phone_number="0901000111")
    db_session.add_all([account, stranger, customer2])
    db_session.flush()
    db_session.add_all([
        PortalAccountLink(user_id=account.id, customer_id=customer.id, verification="manager", verified_by_id=test_user.id),
        PortalAccountLink(user_id=stranger.id, customer_id=customer2.id, verification="manager", verified_by_id=test_user.id),
        PortalVehicleOwnership(customer_id=customer.id, vehicle_id=vehicle.id, approved_by_id=test_user.id,
                               approved_at=now - timedelta(days=1)),
    ])
    db_session.commit()
    actor = {"user": test_user}
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_db] = lambda: db_session
    app.dependency_overrides[get_current_user] = lambda: actor["user"]
    return SimpleNamespace(db=db_session, staff=test_user, account=account, stranger=stranger,
                           a=a, b=b, slot=parking_slot, vehicle=vehicle, other=other,
                           clock=clock, actor=actor, client=TestClient(app), now=now, customer=customer)


def data(env, *, key="reservation-request-0001", vehicle=None, start=None, end=None, slot=None, site=None):
    return ReservationCreate(site_id=(site or env.a).id, vehicle_id=(vehicle or env.vehicle).id,
        slot_id=(slot or env.slot).id, start_at=(start or env.now).replace(tzinfo=BUSINESS_TZ),
        end_at=(end or env.now + timedelta(hours=2)).replace(tzinfo=BUSINESS_TZ), request_id=key)


def reserve(env, **kwargs):
    row = service.reserve(env.db, env.staff, data(env, **kwargs))
    env.db.commit()
    return row


def test_site_membership_required_even_for_global_manager(env):
    require_site_access(env.db, env.staff, env.a.id, "manager")
    with pytest.raises(HTTPException) as exc:
        require_site_access(env.db, env.staff, env.b.id)
    assert exc.value.status_code == 403
    assert env.client.get(f"/api/v2/sites/{env.b.id}/sessions").status_code == 403
    with pytest.raises(HTTPException) as exc:
        service.reserve(
            env.db,
            env.staff,
            data(env, key="foreign-site-oracle", vehicle=env.other, site=env.b),
        )
    assert exc.value.status_code == 403


def test_customer_catalog_never_leaks_vehicle_or_staff_data(env):
    env.actor["user"] = env.account
    assert len(env.client.get("/api/v2/sites").json()) == 2
    available = env.client.get(f"/api/v2/sites/{env.a.id}/availability")
    assert available.status_code == 200
    assert "license_plate" not in available.text and "customer_id" not in available.text
    assert env.client.get(f"/api/v2/sites/{env.a.id}/members").status_code == 403


def test_customer_only_approved_vehicle_and_own_reservations(env):
    env.actor["user"] = env.account
    body = data(env).model_dump(mode="json")
    response = env.client.post("/api/v2/me/reservations", json=body)
    assert response.status_code == 201, response.text
    assert "created_by_id" not in response.json()
    rid = response.json()["id"]
    assert response.json()["start_at"].endswith("+07:00")
    assert len(env.client.get("/api/v2/me/reservations").json()) == 1
    body.update(vehicle_id=env.other.id, request_id="unapproved-request-0001")
    assert env.client.post("/api/v2/me/reservations", json=body).status_code in {403, 404}
    env.actor["user"] = env.stranger
    assert env.client.get("/api/v2/me/reservations").json() == []
    assert env.client.post(f"/api/v2/me/reservations/{rid}/cancel").status_code == 404


@pytest.mark.parametrize("extra", [{"customer_id": 1}, {"price": 0}, {"is_occupied": True}, {"status": "arrived"}])
def test_booking_body_rejects_client_authority(env, extra):
    env.actor["user"] = env.account
    assert env.client.post("/api/v2/me/reservations", json={**data(env).model_dump(mode="json"), **extra}).status_code == 422


def test_customer_booking_rejects_start_beyond_thirty_days(env):
    env.actor["user"] = env.account
    body = data(
        env,
        start=env.now + timedelta(days=31),
        end=env.now + timedelta(days=31, hours=2),
    ).model_dump(mode="json")

    response = env.client.post("/api/v2/me/reservations", json=body)

    assert response.status_code == 422
    assert "30 ngày" in response.json()["detail"]
    assert env.db.scalar(select(func.count()).select_from(ParkingReservation)) == 0


def test_customer_has_a_bounded_number_of_active_reservations(env):
    env.actor["user"] = env.account
    for index in range(5):
        start = env.now + timedelta(hours=index * 2)
        body = data(
            env,
            key=f"customer-cap-{index:04}",
            start=start,
            end=start + timedelta(hours=1),
        ).model_dump(mode="json")
        assert env.client.post("/api/v2/me/reservations", json=body).status_code == 201

    start = env.now + timedelta(hours=12)
    rejected = env.client.post(
        "/api/v2/me/reservations",
        json=data(
            env,
            key="customer-cap-overflow",
            start=start,
            end=start + timedelta(hours=1),
        ).model_dump(mode="json"),
    )

    assert rejected.status_code == 409
    assert "tối đa 5" in rejected.json()["detail"]
    assert env.db.scalar(select(func.count()).select_from(ParkingReservation)) == 5


def test_duplicate_request_returns_same_booking_but_changed_content_conflicts(env):
    first = reserve(env)
    assert reserve(env).id == first.id
    with pytest.raises(HTTPException) as exc:
        reserve(env, end=env.now + timedelta(hours=3))
    assert exc.value.status_code == 409
    env.db.rollback()
    assert env.db.scalar(select(func.count()).select_from(ParkingReservation)) == 1


def test_terminal_booking_request_id_cannot_be_reused(env):
    row = reserve(env)
    service.cancel(env.db, env.account, row, customer=True)
    env.db.commit()

    with pytest.raises(HTTPException) as exc:
        reserve(env)

    assert exc.value.status_code == 409
    assert "mã yêu cầu mới" in exc.value.detail.lower()
    env.db.rollback()
    assert env.db.scalar(select(func.count()).select_from(ParkingReservation)) == 1


def test_overlap_rejected_adjacent_window_allowed(env):
    reserve(env)
    with pytest.raises(HTTPException) as exc:
        reserve(env, key="overlap-request-0002", vehicle=env.other)
    assert exc.value.status_code == 409
    env.db.rollback()
    later = reserve(env, key="adjacent-request-0003", vehicle=env.other,
                    start=env.now + timedelta(hours=2), end=env.now + timedelta(hours=3))
    assert later.status == "confirmed"


def test_same_vehicle_cannot_reserve_overlapping_different_slots(env):
    reserve(env)
    second = ParkingSlot(zone_id=env.slot.zone_id, vehicle_type_id=env.vehicle.vehicle_type_id, slot_name="A-02")
    env.db.add(second)
    env.db.commit()
    with pytest.raises(HTTPException) as exc:
        reserve(env, key="other-slot-request-0002", slot=second)
    assert exc.value.status_code == 409


@pytest.mark.parametrize("path", ["service", "crud"])
def test_future_booking_blocks_walk_in_on_both_claim_paths(env, path):
    reserve(env, start=env.now + timedelta(hours=1), end=env.now + timedelta(hours=2))
    if path == "service":
        with pytest.raises(HTTPException) as exc:
            ParkingService(env.db).check_in(env.other.license_plate, env.other.vehicle_type_id,
                                            env.staff.id, parking_slot_id=env.slot.id)
        assert exc.value.status_code == 409
    else:
        assert session_crud.claim_parking_slot(env.db, env.slot.id, vehicle_id=env.other.id,
                                               check_in_time=env.now) is False
        env.db.rollback()
    env.db.refresh(env.slot)
    assert env.slot.is_occupied is False
    assert env.db.scalar(select(func.count()).select_from(ParkingSession)) == 0


def test_walk_in_reports_future_reservation_instead_of_a_race(env):
    reserve(env, start=env.now + timedelta(hours=1), end=env.now + timedelta(hours=2))

    with pytest.raises(HTTPException) as exc:
        ParkingService(env.db).check_in(
            env.other.license_plate,
            env.other.vehicle_type_id,
            env.staff.id,
            parking_slot_id=env.slot.id,
        )

    assert exc.value.status_code == 409
    assert "đặt chỗ" in exc.value.detail.lower()


def test_arrival_is_atomic_and_replay_does_not_open_second_session(env):
    row = reserve(env)
    result = service.arrive(env.db, env.staff, row)
    env.db.commit()
    assert result.status == "arrived" and result.session_id
    assert service.arrive(env.db, env.staff, row).session_id == result.session_id
    assert env.db.scalar(select(func.count()).select_from(ParkingSession)) == 1
    with pytest.raises(HTTPException):
        service.cancel(env.db, env.account, row, customer=True)


def test_check_in_to_another_slot_is_rejected_before_creating_a_session(env):
    reservation = reserve(env)
    alternate = ParkingSlot(
        zone_id=env.slot.zone_id,
        vehicle_type_id=env.vehicle.vehicle_type_id,
        slot_name="A-ALTERNATE",
    )
    env.db.add(alternate)
    env.db.commit()

    with pytest.raises(HTTPException) as exc:
        ParkingService(env.db).check_in(
            env.vehicle.license_plate,
            env.vehicle.vehicle_type_id,
            env.staff.id,
            parking_slot_id=alternate.id,
        )

    env.db.refresh(reservation)
    env.db.refresh(alternate)
    assert exc.value.status_code == 409
    assert env.slot.slot_name in exc.value.detail
    assert reservation.status == "confirmed"
    assert reservation.session_id is None
    assert reservation.slot_id == env.slot.id
    assert alternate.is_occupied is False
    assert env.db.scalar(select(func.count()).select_from(ParkingSession)) == 0


def test_late_previous_vehicle_cannot_be_overwritten_by_next_booking(env):
    first = reserve(env)
    later = reserve(env, key="later-arrival-0002", vehicle=env.other,
                    start=env.now + timedelta(hours=2), end=env.now + timedelta(hours=3))
    service.arrive(env.db, env.staff, first)
    # The route commits only after arrival verifies the session binding.
    env.db.commit()
    env.clock["now"] += timedelta(hours=2)
    with pytest.raises(HTTPException) as exc:
        service.arrive(env.db, env.staff, later)
    env.db.rollback()
    assert exc.value.status_code == 409
    env.db.refresh(env.slot)
    assert env.slot.is_occupied
    assert env.db.scalar(select(func.count()).select_from(ParkingSession)) == 1


def test_no_show_boundary_releases_hold_and_expiry_is_idempotent(env):
    row = reserve(env)
    env.clock["now"] = row.arrival_deadline
    service.lock_slot(env.db, env.slot.id)
    assert service.expire_slot(env.db, env.slot.id, env.clock["now"]) == 1
    assert service.expire_slot(env.db, env.slot.id, env.clock["now"]) == 0
    assert service.admission_allowed(env.db, env.slot.id, vehicle_id=env.other.id, at=env.clock["now"])


def test_allocation_protects_space_but_does_not_make_stay_free(env):
    allocation = service.reserve(env.db, env.staff, AllocationCreate(**data(env).model_dump()), allocation=True)
    env.db.commit()
    assert not service.admission_allowed(env.db, env.slot.id, vehicle_id=env.other.id, at=env.now)
    env.db.rollback()
    result = ParkingService(env.db).check_in(env.vehicle.license_plate, env.vehicle.vehicle_type_id,
                                            env.staff.id, parking_slot_id=env.slot.id)
    assert result["monthly_pass_id"] is None
    assert env.db.get(ParkingSession, result["session_id"]).monthly_coverage_end is None


def test_v2_session_payload_excludes_internal_confirmation_and_image_fields(env):
    result = ParkingService(env.db).check_in(
        env.vehicle.license_plate,
        env.vehicle.vehicle_type_id,
        env.staff.id,
        parking_slot_id=env.slot.id,
    )
    session = env.db.get(ParkingSession, result["session_id"])
    payload = service.serialize(session)
    forbidden = {
        "checkout_quote_hash",
        "checkout_payment_method",
        "monthly_coverage_end",
        "image_in_url",
        "image_out_url",
        "staff_in_id",
        "staff_out_id",
    }
    assert forbidden.isdisjoint(payload)


def test_v2_session_metadata_timestamps_keep_their_utc_meaning():
    session = ParkingSession(
        id="utc-metadata-session",
        vehicle_id=1,
        check_in_time=datetime(2026, 9, 8, 10, 0),
        status="active",
        staff_in_id=1,
        created_at=datetime(2026, 9, 8, 3, 0),
        updated_at=datetime(2026, 9, 8, 3, 5),
    )

    payload = service.serialize(session)

    assert payload["created_at"].tzinfo == timezone.utc
    assert payload["updated_at"].tzinfo == timezone.utc
    assert payload["check_in_time"].utcoffset() == timedelta(hours=7)

    zone = Zone(
        id=1,
        name="UTC metadata zone",
        capacity=1,
        created_at=datetime(2026, 9, 8, 3, 0),
        updated_at=datetime(2026, 9, 8, 3, 5),
    )
    zone_payload = service.serialize(zone)
    assert zone_payload["created_at"].tzinfo == timezone.utc
    assert zone_payload["updated_at"].tzinfo == timezone.utc


def test_reservation_cannot_give_same_vehicle_a_second_slot_over_its_allocation(env):
    allocation = service.reserve(
        env.db,
        env.staff,
        AllocationCreate(**data(env, key="vehicle-allocation-0001").model_dump()),
        allocation=True,
    )
    second = ParkingSlot(
        zone_id=env.slot.zone_id,
        vehicle_type_id=env.vehicle.vehicle_type_id,
        slot_name="A-SECOND",
    )
    env.db.add(second)
    env.db.commit()

    with pytest.raises(HTTPException) as exc:
        reserve(env, key="vehicle-reservation-0002", slot=second)

    assert exc.value.status_code == 409
    assert allocation.slot_id == env.slot.id
    env.db.rollback()
    assert env.db.scalar(select(func.count()).select_from(ParkingReservation)) == 0


def test_waitlist_holds_no_capacity_then_offer_creates_exactly_one_booking(env):
    body = BookingWindow(**data(env).model_dump(exclude={"slot_id"}))
    row = service.join_waitlist(env.db, env.staff, body)
    env.db.commit()
    assert service.admission_allowed(env.db, env.slot.id, vehicle_id=env.other.id, at=env.now)
    offered = service.offer_waitlist(env.db, env.staff, row)
    env.db.commit()
    assert row.status == "offered"
    assert service.offer_waitlist(env.db, env.staff, row).id == offered.id
    assert env.db.scalar(select(func.count()).select_from(ParkingReservation)) == 1
    notifications = env.db.scalars(select(PortalNotification).where(
        PortalNotification.event_key == f"waitlist:{row.id}:offered",
    )).all()
    assert len(notifications) == 1
    assert "15 phút" in notifications[0].message


def test_foreign_site_resource_cannot_be_used_in_scoped_checkin(env):
    body = {"license_plate": env.vehicle.license_plate, "vehicle_type_id": env.vehicle.vehicle_type_id,
            "parking_slot_id": env.slot.id}
    assert env.client.post(f"/api/v2/sites/{env.b.id}/check-in", json=body).status_code == 403
    assert env.client.post(f"/api/v2/sites/{env.b.id}/reservations", json=data(env).model_dump(mode="json")).status_code == 422


def test_fleet_does_not_expose_history_before_vehicle_joined(env):
    org = Organization(site_id=env.a.id, name="Đội xe")
    env.db.add(org)
    env.db.flush()
    env.db.add_all([OrganizationMembership(organization_id=org.id, user_id=env.account.id),
                   FleetVehicle(organization_id=org.id, vehicle_id=env.vehicle.id, created_at=env.now + timedelta(minutes=1))])
    env.db.commit()
    ParkingService(env.db).check_in(env.vehicle.license_plate, env.vehicle.vehicle_type_id,
                                  env.staff.id, parking_slot_id=env.slot.id)
    summary = fleet_summary(env.db, env.account, org.id)
    assert summary["active_sessions"] == 0 and summary["sessions"] == []
    with pytest.raises(HTTPException) as exc:
        fleet_summary(env.db, env.stranger, org.id)
    assert exc.value.status_code == 403


def test_reservation_identity_and_source_have_database_backstops(env):
    row = reserve(env)
    row.slot_id = 999999
    with pytest.raises(IntegrityError):
        env.db.commit()
    env.db.rollback()
    row = env.db.get(ParkingReservation, row.id)
    row.status = "arrived"
    with pytest.raises(IntegrityError):
        env.db.commit()
    env.db.rollback()
    env.slot.is_active = False
    with pytest.raises(IntegrityError):
        env.db.commit()
    env.db.rollback()


def test_zone_cannot_be_deactivated_while_it_has_future_commitments(env):
    row = reserve(env, start=env.now + timedelta(hours=1), end=env.now + timedelta(hours=2))

    with pytest.raises(HTTPException) as exc:
        update_zone(env.slot.zone_id, ZoneUpdate(is_active=False), env.db)

    assert exc.value.status_code == 409
    assert "đặt chỗ" in exc.value.detail.lower()
    service.cancel(env.db, env.staff, row)
    env.db.commit()
    updated = update_zone(env.slot.zone_id, ZoneUpdate(is_active=False), env.db)
    assert updated.is_active is False


def test_zone_commitment_guard_rejects_direct_database_deactivation(env):
    reserve(env, start=env.now + timedelta(hours=1), end=env.now + timedelta(hours=2))
    zone = env.db.get(Zone, env.slot.zone_id)
    zone.is_active = False

    with pytest.raises(IntegrityError):
        env.db.commit()

    env.db.rollback()
    assert env.db.get(Zone, env.slot.zone_id).is_active is True


def test_zone_cannot_be_moved_to_another_site_after_assignment(env):
    env.slot.zone.site_id = env.b.id
    with pytest.raises(IntegrityError):
        env.db.commit()
    env.db.rollback()


def test_cancelled_waitlist_cannot_be_offered_or_hold_capacity(env):
    row = service.join_waitlist(env.db, env.staff, BookingWindow(**data(env).model_dump(exclude={"slot_id"})))
    env.db.commit()
    assert service.cancel_waitlist(env.db, env.account, row, customer=True).status == "cancelled"
    assert service.cancel_waitlist(env.db, env.account, row, customer=True).status == "cancelled"
    with pytest.raises(HTTPException) as exc:
        service.offer_waitlist(env.db, env.staff, row)
    assert exc.value.status_code == 409


def test_site_specific_portal_pass_does_not_apply_at_another_site(env):
    from expansion.portal_models import PortalOrder, SubscriptionPlan
    from services.payment_service import PaymentService
    period = MonthlyPass(customer_id=env.customer.id, vehicle_id=env.vehicle.id, pass_code="SITE-PASS-001",
                         price=100_000, start_date=env.now.date(), end_date=env.now.date() + timedelta(days=29))
    plan = SubscriptionPlan(name="Bãi A", site_id=env.a.id, vehicle_type_id=env.vehicle.vehicle_type_id,
                            duration_days=30, price=100_000)
    env.db.add_all([period, plan])
    env.db.flush()
    receipt = PaymentService.record_receipt(env.db, "monthly_pass", period.id, period.price, env.staff.id)
    env.db.add(PortalOrder(user_id=env.account.id, customer_id=env.customer.id, vehicle_id=env.vehicle.id,
                          plan_id=plan.id, site_id=env.a.id, amount=period.price, start_date=period.start_date,
                          end_date=period.end_date, payment_mode="manual", status="fulfilled",
                          idempotency_key="site-order-test-0001", expires_at=env.now + timedelta(minutes=15),
                          monthly_pass_id=period.id, receipt_id=receipt.id))
    env.db.commit()
    args = dict(vehicle_id=env.vehicle.id, vehicle_type_id=env.vehicle.vehicle_type_id, check_in_time=env.now)
    assert session_crud.resolve_check_in_monthly_pass_id(env.db, **args, site_id=env.a.id) == period.id
    assert session_crud.resolve_check_in_monthly_pass_id(env.db, **args, site_id=env.b.id) is None
    assert session_crud.resolve_check_in_monthly_pass_id(env.db, **args) is None


def test_legacy_monthly_pass_still_works_without_portal_site_restriction(env):
    period = MonthlyPass(customer_id=env.customer.id, vehicle_id=env.vehicle.id, pass_code="LEGACY-GLOBAL",
                         price=100_000, start_date=env.now.date(), end_date=env.now.date() + timedelta(days=29))
    env.db.add(period)
    env.db.commit()
    assert session_crud.resolve_check_in_monthly_pass_id(env.db, vehicle_id=env.vehicle.id,
        vehicle_type_id=env.vehicle.vehicle_type_id, check_in_time=env.now, site_id=env.b.id) == period.id


def test_site_catalog_reports_membership_role_and_never_exposes_it_to_customers(env):
    assert env.client.get("/api/v2/sites").json()[0]["role"] == "manager"
    member = env.db.scalar(select(SiteMembership).where(SiteMembership.site_id == env.a.id,
                                                       SiteMembership.user_id == env.staff.id))
    member.role = "staff"
    env.db.commit()
    assert env.client.get("/api/v2/sites").json()[0]["role"] == "staff"
    env.actor["user"] = env.account
    assert all("role" not in row for row in env.client.get("/api/v2/sites").json())


def test_manager_can_populate_scoped_site_and_capacity_is_enforced(env):
    root = f"/api/v2/sites/{env.a.id}"
    zone = env.client.post(root + "/zones", json={"name": "Bãi A - Khu mới", "capacity": 1})
    assert zone.status_code == 201, zone.text
    assert zone.json()["site_id"] == env.a.id
    body = {"zone_id": zone.json()["id"], "vehicle_type_id": env.vehicle.vehicle_type_id, "slot_name": "NEW-A-001"}
    slot = env.client.post(root + "/slots", json=body)
    assert slot.status_code == 201, slot.text
    assert slot.json()["is_occupied"] is False
    assert env.client.post(root + "/slots", json={**body, "slot_name": "NEW-A-002"}).status_code == 409
    assert env.client.post(root + "/slots", json={**body, "is_occupied": True}).status_code == 422
    assert env.client.post(root + "/zones", json={"name": "Hijack", "capacity": 3, "site_id": env.b.id}).status_code == 422


def test_scoped_configuration_cannot_target_foreign_site_or_zone(env):
    other_zone = Zone(site_id=env.b.id, name="Foreign zone", capacity=3)
    env.db.add(other_zone)
    env.db.commit()
    root = f"/api/v2/sites/{env.a.id}"
    assert env.client.post(root + "/slots", json={"zone_id": other_zone.id, "vehicle_type_id": env.vehicle.vehicle_type_id,
                                                 "slot_name": "FOREIGN"}).status_code == 404
    assert env.client.get(f"/api/v2/sites/{env.b.id}/zones").status_code == 403
    assert env.client.post(f"/api/v2/sites/{env.b.id}/zones", json={"name": "Denied", "capacity": 3}).status_code == 403
    env.actor["user"] = env.account
    assert env.client.get(root + "/zones").status_code == 403
    assert env.client.post(root + "/zones", json={"name": "Denied", "capacity": 3}).status_code == 403


def test_staff_membership_cannot_configure_site_even_with_global_management_role(env):
    member = env.db.scalar(select(SiteMembership).where(SiteMembership.site_id == env.a.id,
                                                       SiteMembership.user_id == env.staff.id))
    member.role = "staff"
    env.db.commit()
    assert env.client.post(f"/api/v2/sites/{env.a.id}/zones", json={"name": "Denied", "capacity": 3}).status_code == 403


def test_bookable_vehicle_lookup_is_scoped_bounded_and_has_no_customer_contacts(env):
    root = f"/api/v2/sites/{env.a.id}/vehicles"
    found = env.client.get(root, params={"q": env.vehicle.license_plate.lower()}).json()
    assert found == [{"id": env.vehicle.id, "license_plate": env.vehicle.license_plate, "vehicle_type_id": env.vehicle.vehicle_type_id}]
    assert len(env.client.get(root, params={"limit": 1}).json()) == 1
    assert env.client.get(root, params={"q": "%"}).json() == []
    assert env.client.get(f"/api/v2/sites/{env.b.id}/vehicles").status_code == 403
    env.actor["user"] = env.account
    assert env.client.get(root).status_code == 403


def test_plate_lookup_finds_active_session_before_pagination(env):
    ParkingService(env.db).check_in(env.vehicle.license_plate, env.vehicle.vehicle_type_id,
                                  env.staff.id, parking_slot_id=env.slot.id)
    root = f"/api/v2/sites/{env.a.id}/sessions"
    found = env.client.get(root, params={"license_plate": env.vehicle.license_plate.lower(), "status": "active", "limit": 1})
    assert found.status_code == 200, found.text
    assert len(found.json()) == 1
    assert found.json()[0]["license_plate"] == env.vehicle.license_plate
    assert env.client.get(root, params={"license_plate": "UNKNOWN", "status": "active"}).json() == []
    assert env.client.get(root, params={"license_plate": env.vehicle.license_plate, "status": "completed"}).json() == []
