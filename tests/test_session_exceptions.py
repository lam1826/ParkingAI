"""Exceptions preserve admission identity, money and physical occupancy together."""
from datetime import timedelta
from types import SimpleNamespace

import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import event, func, select, text
from sqlalchemy.exc import IntegrityError

from crud import parking_session as session_crud
from database import get_db
from expansion.site_models import ParkingSite, SiteMembership
from expansion.site_router import router
from expansion.system_router import require_legacy_workspace
from models.cash_shift import CashShift
from models.parking_session import ParkingSession
from models.parking_session_event import ParkingSessionEvent
from models.payment import Payment
from models.price_config import PriceConfig
from models.role import Role
from models.user import User
from models.vehicle import Vehicle
from routers.parking_session import router as legacy_router
from schemas.checkout import CheckoutConfirmation
from services.auth_service import RoleChecker, get_current_user
from services.checkout_service import CheckoutService
from services.parking_service import ParkingService
from services.ticket_service import get_ticket
from test_expansion_sites import env as booking_env, reserve


@pytest.fixture
def env(db_session, test_user, manager_user, vehicle_type, parking_slot, vehicle, price_config,
        business_reference_now, monkeypatch):
    clock = {"now": business_reference_now.replace(microsecond=0)}
    # manager_user deliberately promotes test_user in the common fixture;
    # exception/checkout tests need two genuinely separate actors.
    test_user = User(username="exception_staff", role=db_session.scalar(select(Role).where(Role.name == "staff")),
                     password_hash="unused", full_name="Nhân viên ngoại lệ")
    db_session.add(test_user)
    monkeypatch.setattr(session_crud, "server_now", lambda: clock["now"])
    site = ParkingSite(name="Bãi ngoại lệ")
    db_session.add(site)
    db_session.flush()
    parking_slot.zone.site_id = site.id
    vehicle.customer_id = None
    db_session.add_all([SiteMembership(site_id=site.id, user_id=manager_user.id, role="manager"),
                        SiteMembership(site_id=site.id, user_id=test_user.id, role="staff")])
    db_session.commit()
    active = ParkingService(db_session).check_in(vehicle.license_plate, vehicle_type.id, test_user.id,
                                                parking_slot_id=parking_slot.id, _expected_site_id=site.id)
    session = db_session.get(ParkingSession, active["session_id"])
    actor = {"user": manager_user}
    app = FastAPI()
    app.include_router(router)
    app.include_router(legacy_router, prefix="/api/v1/parking-sessions",
                       dependencies=[Depends(RoleChecker("staff")), Depends(require_legacy_workspace)])
    app.dependency_overrides[get_db] = lambda: db_session
    app.dependency_overrides[get_current_user] = lambda: actor["user"]
    with TestClient(app) as client:
        yield SimpleNamespace(db=db_session, staff=test_user, manager=manager_user, actor=actor, site=site,
                              vehicle=vehicle, slot=parking_slot, session=session, rate=price_config,
                              clock=clock, client=client, base=f"/api/v2/sites/{site.id}/sessions/{session.id}")


def body(**changes):
    return {"reason": "Nhập nhầm lượt tại cổng", "request_id": "exception-001", **changes}


def counts(env):
    return {model.__tablename__: env.db.scalar(select(func.count()).select_from(model))
            for model in (ParkingSession, ParkingSessionEvent, Payment)}


def confirm(env, session_id=None):
    quote = CheckoutService(env.db).quote(session_id or env.session.id, env.staff.id)
    return CheckoutConfirmation(quote_token=quote["quote_token"], payment_confirmed=True,
                                payment_method="cash" if quote["parking_fee"] else None)


def test_cancel_is_atomic_idempotent_keeps_history_and_no_money(env):
    shift = CashShift(staff_id=env.manager.id, site_id=env.site.id, opening_cash=50000, opened_at=env.clock["now"])
    env.db.add(shift); env.db.commit()
    response = env.client.post(env.base + "/cancel", json=body())
    assert response.status_code == 200, response.text
    result = response.json()
    assert result["status"] == "cancelled" and result["next_action"] == "none"
    assert result["event"]["actor_id"] == env.manager.id
    assert result["event"]["before_state"]["status"] == "active"
    assert result["event"]["after_state"]["status"] == "cancelled"
    env.db.refresh(env.slot); env.db.refresh(env.session); env.db.refresh(shift)
    assert env.slot.is_occupied is False
    assert env.session.parking_fee is None and env.session.check_out_time is None and env.session.staff_out_id is None
    assert shift.status == "open" and shift.opening_cash == 50000 and shift.counted_cash is None
    assert counts(env) == {"parking_sessions": 1, "parking_session_events": 1, "payments": 0}
    assert env.client.post(env.base + "/cancel", json=body()).json() == result
    assert env.client.post(env.base + "/cancel", json=body(reason="Nội dung khác")).status_code == 409
    assert env.client.get(f"/api/v2/sites/{env.site.id}/sessions?status=cancelled").json()[0]["id"] == env.session.id
    assert get_ticket(env.db, env.session.id)["status"] == "cancelled"


@pytest.mark.parametrize("action", ["cancel", "lost-ticket", "correct-plate"])
@pytest.mark.parametrize("global_role,membership", [("staff", "staff"), ("staff", "manager"), ("manager", "staff")])
def test_exception_requires_both_manager_grants(env, action, global_role, membership):
    role = env.db.scalar(select(Role).where(Role.name == global_role))
    env.manager.role = role
    member = env.db.scalar(select(SiteMembership).where(SiteMembership.user_id == env.manager.id))
    member.role = membership
    env.db.commit()
    payload = body(license_plate="59A77777") if action == "correct-plate" else body()
    assert env.client.post(env.base + "/" + action, json=payload).status_code == 403
    assert counts(env) == {"parking_sessions": 1, "parking_session_events": 0, "payments": 0}
    assert env.slot.is_occupied


@pytest.mark.parametrize("changes", [{"reason": "   "}, {"reason": "a"}, {"request_id": ""}, {"parking_fee": 0}, {"staff_out_id": 1}, {"status": "cancelled"}])
def test_exception_body_rejects_missing_reason_and_client_authority(env, changes):
    assert env.client.post(env.base + "/cancel", json=body(**changes)).status_code == 422
    assert counts(env)["parking_session_events"] == 0


def test_scope_is_enforced_and_staff_can_read_operational_evidence(env):
    other = ParkingSite(name="Bãi khác"); env.db.add(other); env.db.commit()
    assert env.client.post(f"/api/v2/sites/{other.id}/sessions/{env.session.id}/cancel", json=body()).status_code == 403
    assert env.client.post(env.base + "/lost-ticket", json=body()).status_code == 200
    env.actor["user"] = env.staff
    detail = env.client.get(env.base + "/exceptions")
    assert detail.status_code == 200
    assert detail.json()["events"][0]["action"] == "lost_ticket"
    assert all(not item["allowed"] for item in detail.json()["eligibility"].values())
    # The same legacy endpoint remains denied when the installation has multiple lots.
    assert env.client.post(f"/api/v1/parking-sessions/{env.session.id}/cancel", json=body()).status_code == 403


def test_lost_ticket_preserves_quote_and_normal_checkout_fee_shift(env):
    env.clock["now"] += timedelta(hours=2)
    shift = CashShift(staff_id=env.staff.id, site_id=env.site.id, opening_cash=20000, opened_at=env.clock["now"])
    env.db.add(shift); env.db.commit()
    confirmation = confirm(env)
    expected_fee = CheckoutService(env.db).quote(env.session.id, env.staff.id)["parking_fee"]
    response = env.client.post(env.base + "/lost-ticket", json=body(reason="Khách làm mất vé giấy"))
    assert response.status_code == 200, response.text
    assert response.json()["next_action"] == "checkout" and response.json()["status"] == "active"
    assert env.slot.is_occupied and counts(env)["payments"] == 0
    CheckoutService(env.db).confirm(confirmation, env.staff.id, session_id=env.session.id)
    payments = list(env.db.scalars(select(Payment)))
    assert len(payments) == 1 and payments[0].amount == expected_fee and payments[0].shift_id == shift.id
    assert env.client.post(env.base + "/cancel", json=body(request_id="different")).status_code == 409
    assert env.client.post(env.base + "/lost-ticket", json=body(request_id="different")).status_code == 409
    replay = env.client.post(env.base + "/lost-ticket", json=body(reason="Khách làm mất vé giấy"))
    assert replay.status_code == 200 and replay.json()["next_action"] == "none"
    assert counts(env)["parking_session_events"] == 1


def test_cancel_invalidates_an_already_issued_checkout_quote(env):
    confirmation = confirm(env)
    assert env.client.post(env.base + "/cancel", json=body()).status_code == 200
    from fastapi import HTTPException
    with pytest.raises(HTTPException) as error:
        CheckoutService(env.db).confirm(confirmation, env.staff.id, session_id=env.session.id)
    assert error.value.status_code == 409
    assert counts(env)["payments"] == 0


def test_cancel_refuses_portal_grant_without_releasing_occupancy(env, customer):
    from expansion.portal_models import PortalSessionGrant
    env.db.add(PortalSessionGrant(parking_session_id=env.session.id, customer_id=customer.id)); env.db.commit()
    response = env.client.post(env.base + "/cancel", json=body())
    assert response.status_code == 409 and "hồ sơ" in response.text
    assert env.slot.is_occupied and env.session.status == "active"
    assert counts(env)["parking_session_events"] == 0


def test_failed_evidence_insert_rolls_back_cancel_and_slot(env):
    def reject(conn, cursor, statement, parameters, context, executemany):
        if statement.lstrip().upper().startswith("INSERT INTO PARKING_SESSION_EVENTS"):
            raise IntegrityError("INSERT", {}, Exception("simulated evidence failure"))
    engine = env.db.get_bind()
    event.listen(engine, "before_cursor_execute", reject)
    try:
        response = env.client.post(env.base + "/cancel", json=body())
    finally:
        event.remove(engine, "before_cursor_execute", reject)
    assert response.status_code == 409
    env.db.refresh(env.session); env.db.refresh(env.slot)
    assert env.session.status == "active" and env.slot.is_occupied
    assert counts(env)["parking_session_events"] == 0


def test_event_and_related_session_cannot_be_rewritten_or_deleted(env):
    response = env.client.post(env.base + "/lost-ticket", json=body())
    assert response.status_code == 200, response.text
    event_id = response.json()["event"]["id"]
    for sql, args in [
        ("UPDATE parking_session_events SET reason='rewritten' WHERE id=:id", {"id": event_id}),
        ("DELETE FROM parking_session_events WHERE id=:id", {"id": event_id}),
        ("INSERT OR REPLACE INTO parking_session_events (id,session_id,site_id,action,reason,request_id,actor_id,actor_username,created_at,before_state,after_state,replacement_session_id) SELECT id,session_id,site_id,action,'silently rewritten',request_id,actor_id,actor_username,created_at,before_state,after_state,replacement_session_id FROM parking_session_events WHERE id=:id", {"id": event_id}),
        ("DELETE FROM parking_sessions WHERE id=:id", {"id": env.session.id}),
        ("INSERT OR REPLACE INTO parking_sessions SELECT * FROM parking_sessions WHERE id=:id", {"id": env.session.id}),
    ]:
        with pytest.raises(IntegrityError):
            env.db.execute(text(sql), args); env.db.commit()
        env.db.rollback()
    admin = Role(name="admin"); env.db.add(admin); env.db.flush(); env.manager.role = admin; env.db.commit()
    assert env.client.delete(f"/api/v1/parking-sessions/{env.session.id}").status_code == 409


def test_correction_preserves_time_rate_and_slot_without_rewriting_vehicle(env):
    original_time = env.session.check_in_time
    original_plate = env.vehicle.license_plate
    original_price = env.session.rate_unit_price
    env.clock["now"] += timedelta(hours=2)
    response = env.client.post(env.base + "/correct-plate", json=body(license_plate=" 59a77777 "))
    assert response.status_code == 200, response.text
    result = response.json()
    replacement = env.db.get(ParkingSession, result["replacement_session_id"])
    env.db.refresh(env.vehicle); env.db.refresh(env.slot)
    assert env.vehicle.license_plate == original_plate and env.session.status == "cancelled"
    assert replacement.status == "active" and replacement.check_in_time == original_time
    assert replacement.rate_unit_price == original_price and replacement.rate_config_id == env.rate.id
    assert replacement.parking_slot_id == env.slot.id and env.slot.is_occupied
    assert get_ticket(env.db, replacement.id)["license_plate"] == "59A77777"
    assert get_ticket(env.db, env.session.id)["status"] == "cancelled"
    detail = env.client.get(f"/api/v2/sites/{env.site.id}/sessions/{replacement.id}/exceptions").json()
    assert detail["events"][0]["session_id"] == env.session.id
    assert result["event"]["before_state"]["license_plate"] == original_plate
    assert result["event"]["after_state"]["license_plate"] == "59A77777"
    assert counts(env) == {"parking_sessions": 2, "parking_session_events": 1, "payments": 0}
    assert env.client.post(env.base + "/correct-plate", json=body(license_plate="59A77777")).json() == result
    confirmation = confirm(env, replacement.id)
    CheckoutService(env.db).confirm(confirmation, env.staff.id, session_id=replacement.id)
    assert replacement.parking_fee == original_price * 2
    assert env.db.scalar(select(Payment)).source_id == replacement.id


def test_correction_refuses_bound_source_and_rolls_back_new_vehicle(env, customer):
    env.vehicle.customer_id = customer.id; env.db.commit()
    response = env.client.post(env.base + "/correct-plate", json=body(license_plate="59A77777"))
    assert response.status_code == 409
    assert env.db.scalar(select(Vehicle).where(Vehicle.license_plate == "59A77777")) is None
    assert counts(env)["parking_sessions"] == 1 and env.slot.is_occupied


def test_correction_refuses_bound_target(env, customer):
    target = Vehicle(license_plate="59A77777", vehicle_type_id=env.vehicle.vehicle_type_id, customer_id=customer.id)
    env.db.add(target); env.db.commit()
    assert env.client.post(env.base + "/correct-plate", json=body(license_plate=target.license_plate)).status_code == 409
    assert counts(env)["parking_sessions"] == 1 and env.slot.is_occupied


def test_correction_refuses_plate_already_parked(env):
    target = Vehicle(license_plate="59A77777", vehicle_type_id=env.vehicle.vehicle_type_id)
    env.db.add(target); env.db.flush()
    other = ParkingSession(vehicle_id=target.id, parking_slot_id=None, check_in_time=env.clock["now"],
                           staff_in_id=env.staff.id, status="active")
    env.db.add(other); env.db.commit()
    response = env.client.post(env.base + "/correct-plate", json=body(license_plate=target.license_plate))
    assert response.status_code == 409 and "đang có lượt" in response.text
    assert counts(env)["parking_sessions"] == 2 and env.slot.is_occupied


def test_correction_refuses_vehicle_type_change(env):
    from models.vehicle_type import VehicleType
    different = VehicleType(name="Loại xe khác"); env.db.add(different); env.db.flush()
    target = Vehicle(license_plate="59A77777", vehicle_type_id=different.id)
    env.db.add(target); env.db.commit()
    assert env.client.post(env.base + "/correct-plate", json=body(license_plate=target.license_plate)).status_code == 409
    assert counts(env)["parking_sessions"] == 1 and env.slot.is_occupied


def test_correction_evidence_failure_rolls_back_both_sessions(env):
    def reject(conn, cursor, statement, parameters, context, executemany):
        if statement.lstrip().upper().startswith("INSERT INTO PARKING_SESSION_EVENTS"):
            raise IntegrityError("INSERT", {}, Exception("simulated evidence failure"))
    engine = env.db.get_bind(); event.listen(engine, "before_cursor_execute", reject)
    try:
        response = env.client.post(env.base + "/correct-plate", json=body(license_plate="59A77777"))
    finally:
        event.remove(engine, "before_cursor_execute", reject)
    assert response.status_code == 409
    env.db.refresh(env.session); env.db.refresh(env.slot)
    assert env.session.status == "active" and env.slot.is_occupied
    assert counts(env) == {"parking_sessions": 1, "parking_session_events": 0, "payments": 0}
    assert env.db.scalar(select(Vehicle).where(Vehicle.license_plate == "59A77777")) is None


def test_correction_retains_deleted_tariff_snapshot_when_new_price_exists(env):
    source_rate_id, source_price = env.session.rate_config_id, env.session.rate_unit_price
    source_time = env.session.check_in_time
    env.rate.is_active = False
    env.db.flush()
    env.db.delete(env.rate)
    newer = PriceConfig(vehicle_type_id=env.vehicle.vehicle_type_id, ticket_type="HOURLY", price=source_price * 4,
                        effective_date=source_time.date() + timedelta(days=1), is_active=True)
    env.db.add(newer); env.db.commit()
    env.clock["now"] += timedelta(days=1, hours=2)
    response = env.client.post(env.base + "/correct-plate", json=body(license_plate="59A77777"))
    assert response.status_code == 200, response.text
    replacement = env.db.get(ParkingSession, response.json()["replacement_session_id"])
    assert replacement.check_in_time == source_time and replacement.rate_config_id == source_rate_id
    quote = CheckoutService(env.db).quote(replacement.id, env.staff.id)
    assert quote["billing_basis"]["unit_price"] == source_price
    assert quote["parking_fee"] == source_price * 26


def test_legacy_session_without_snapshot_cannot_be_reinvented(env):
    assert env.client.post(env.base + "/cancel", json=body()).status_code == 200
    legacy = ParkingSession(vehicle_id=env.vehicle.id, parking_slot_id=env.slot.id,
                            check_in_time=env.clock["now"], staff_in_id=env.staff.id, status="active")
    env.slot.is_occupied = True
    env.db.add(legacy); env.db.commit()
    endpoint = f"/api/v2/sites/{env.site.id}/sessions/{legacy.id}"
    response = env.client.post(endpoint + "/correct-plate", json=body(license_plate="59A77777"))
    assert response.status_code == 409 and "Lượt cũ" in response.text
    assert env.db.get(ParkingSession, legacy.id).status == "active" and env.slot.is_occupied
    assert env.db.scalar(select(Vehicle).where(Vehicle.license_plate == "59A77777")) is None


def test_monthly_session_cancellation_preserves_prepaid_rights(env, customer):
    from models.monthly_pass import MonthlyPass
    assert env.client.post(env.base + "/cancel", json=body()).status_code == 200
    monthly_pass = MonthlyPass(customer_id=customer.id, vehicle_id=env.vehicle.id, price=200000,
                               start_date=env.clock["now"].date(), end_date=env.clock["now"].date() + timedelta(days=30))
    env.db.add(monthly_pass); env.db.commit()
    # The next real admission captures the newly created entitlement.
    admitted = ParkingService(env.db).check_in(env.vehicle.license_plate, env.vehicle.vehicle_type_id, env.staff.id,
                                               parking_slot_id=env.slot.id, _expected_site_id=env.site.id)
    source = env.db.get(ParkingSession, admitted["session_id"])
    assert source.monthly_pass_id == monthly_pass.id
    response = env.client.post(f"/api/v2/sites/{env.site.id}/sessions/{source.id}/cancel", json=body())
    assert response.status_code == 409
    env.db.refresh(monthly_pass); env.db.refresh(env.slot)
    assert monthly_pass.is_active and source.status == "active" and env.slot.is_occupied


def test_arrived_reservation_cancellation_preserves_booking_commitment(booking_env):
    from expansion import reservations
    booking = reserve(booking_env)
    reservations.arrive(booking_env.db, booking_env.staff, booking)
    booking_env.db.commit()
    response = booking_env.client.post(f"/api/v2/sites/{booking_env.a.id}/sessions/{booking.session_id}/cancel", json=body())
    assert response.status_code == 409
    booking_env.db.refresh(booking); booking_env.db.refresh(booking_env.slot)
    assert booking.status == "arrived" and booking_env.slot.is_occupied
    assert booking_env.db.scalar(select(func.count()).select_from(ParkingSessionEvent)) == 0


def test_scoped_ticket_can_be_reprinted_only_by_authorized_operator(env):
    ticket = env.client.get(env.base + "/ticket")
    assert ticket.status_code == 200 and ticket.json()["session_id"] == env.session.id
    other = ParkingSite(name="Bãi không có quyền"); env.db.add(other); env.db.commit()
    assert env.client.get(f"/api/v2/sites/{other.id}/sessions/{env.session.id}/ticket").status_code == 403


def test_cancelled_session_is_terminal_at_database(env):
    assert env.client.post(env.base + "/cancel", json=body()).status_code == 200
    with pytest.raises(IntegrityError):
        env.db.execute(text("UPDATE parking_sessions SET status='active' WHERE id=:id"), {"id": env.session.id})
        env.db.commit()
    env.db.rollback()
    assert env.db.get(ParkingSession, env.session.id).status == "cancelled"


def test_database_rejects_unrelated_replacement_audit_link(env):
    assert env.client.post(env.base + "/cancel", json=body()).status_code == 200
    target = Vehicle(license_plate="59A77777", vehicle_type_id=env.vehicle.vehicle_type_id)
    env.db.add(target); env.db.flush()
    unrelated = ParkingSession(vehicle_id=target.id, parking_slot_id=env.slot.id,
                               check_in_time=env.clock["now"] + timedelta(minutes=1), staff_in_id=env.staff.id,
                               status="active", **{field: getattr(env.session, field) for field in (
                                   "billing_policy_version", "rate_config_id", "rate_ticket_type", "rate_unit_price", "rate_effective_date")})
    env.db.add(unrelated); env.db.commit()
    with pytest.raises(IntegrityError, match="replacement must preserve"):
        env.db.add(ParkingSessionEvent(session_id=env.session.id, site_id=env.site.id, action="plate_corrected",
            reason="Giả lập liên kết lượt không hợp lệ", request_id="invalid-link", actor_id=env.manager.id,
            actor_username=env.manager.username, before_state={}, after_state={}, replacement_session_id=unrelated.id))
        env.db.commit()
    env.db.rollback()
    assert env.db.scalar(select(func.count()).select_from(ParkingSessionEvent)) == 1


@pytest.mark.parametrize("complete_free", [False, True])
def test_admin_cannot_delete_admitted_snapshot_even_without_receipt(env, complete_free):
    if complete_free:
        CheckoutService(env.db).confirm(confirm(env), env.staff.id, session_id=env.session.id)
        assert env.session.parking_fee == 0
    admin = Role(name="admin"); env.db.add(admin); env.db.flush(); env.manager.role = admin; env.db.commit()
    response = env.client.delete(f"/api/v1/parking-sessions/{env.session.id}")
    assert response.status_code == 409 and "căn cứ giá" in response.text
    assert counts(env)["payments"] == 0 and counts(env)["parking_sessions"] == 1
    with pytest.raises(IntegrityError, match="snapshot history"):
        env.db.execute(text("DELETE FROM parking_sessions WHERE id=:id"), {"id": env.session.id})
        env.db.commit()
    env.db.rollback()
