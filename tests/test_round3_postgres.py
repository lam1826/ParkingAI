"""Real PostgreSQL adversarial schedules; never use an application database."""
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from threading import Barrier, local
from time import sleep
from uuid import uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy import event, func, select
from sqlalchemy.orm import Session

from test_postgres_integration import _isolated_checkout_postgres, POSTGRES_TEST_URL
from core.clock import business_now, BUSINESS_TZ
from expansion import reservations
from expansion.portal_models import PortalAccountLink, PortalVehicleOwnership
from expansion.site_models import ParkingSite, ParkingReservation
from expansion.site_schemas import ReservationCreate
from models import Customer, ParkingSlot, Role, User, Vehicle, VehicleType, Zone
from models import ParkingSession, MonthlyPass
from models.payment import Payment
from models.cash_shift import CashShift
from services.cash_shift_service import CashShiftService
from services.payment_service import PaymentService
from services.checkout_service import CheckoutService
from schemas.checkout import CheckoutConfirmation

pytestmark = pytest.mark.skipif(not POSTGRES_TEST_URL, reason="Requires isolated PostgreSQL service")


def test_postgres_availability_batches_future_commitments_at_same_instant(monkeypatch):
    from crud import parking_session as session_crud
    from expansion.site_schemas import AllocationCreate
    from expansion.site_service import availability
    with _isolated_checkout_postgres() as engine:
        now = business_now().replace(microsecond=0)
        clock = {"now": now}
        monkeypatch.setattr(session_crud, "server_now", lambda: clock["now"])
        with Session(engine) as db:
            role, site = Role(name="admin"), ParkingSite(name="Availability batch")
            owner, kind = Customer(full_name="Read query customer", phone_number="BATCH-OWNER"), VehicleType(name="Batch car")
            db.add_all([role, site, owner, kind]); db.flush()
            actor = User(username="batch-admin", role_id=role.id, full_name="Batch", password_hash="unused")
            zone = Zone(name="Batch zone", site_id=site.id, capacity=3)
            db.add_all([actor, zone]); db.flush()
            vehicles = [Vehicle(license_plate=f"BATCH-{i}", vehicle_type_id=kind.id, customer_id=owner.id) for i in range(2)]
            slots = [ParkingSlot(slot_name=f"BATCH-{i}", vehicle_type_id=kind.id, zone_id=zone.id) for i in range(3)]
            db.add_all(vehicles + slots); db.flush()
            for index, schema in enumerate((ReservationCreate, AllocationCreate)):
                reservations.reserve(db, actor, schema(site_id=site.id, slot_id=slots[index].id,
                    vehicle_id=vehicles[index].id, start_at=(now + timedelta(hours=1)).replace(tzinfo=BUSINESS_TZ),
                    end_at=(now + timedelta(hours=2)).replace(tzinfo=BUSINESS_TZ), request_id=uuid4().hex),
                    allocation=(index == 1))
            db.commit()
            site_id = site.id
        statements = []
        def record(_connection, _cursor, sql, _parameters, _context, _many):
            if sql.lstrip().upper().startswith("SELECT"):
                statements.append(sql)
        event.listen(engine, "before_cursor_execute", record)
        try:
            with Session(engine) as db:
                result = availability(db, site_id)
                assert result["total"] == 3 and result["available_now"] == 1 and result["reserved_slots"] == 2
                assert len(statements) <= 2
                clock["now"] = now + timedelta(hours=2)
                assert availability(db, site_id)["available_now"] == 3
        finally:
            event.remove(engine, "before_cursor_execute", record)


def test_customer_booking_cap_serializes_different_vehicles():
    with _isolated_checkout_postgres() as engine:
        now = business_now()
        with Session(engine) as db:
            role, site = Role(name="customer"), ParkingSite(name="Cap race")
            owner, kind = Customer(full_name="Cap customer", phone_number="CAP-OWNER"), VehicleType(name="Cap car")
            db.add_all([role, site, owner, kind]); db.flush()
            actor = User(username="cap-customer", role_id=role.id, full_name="Cap", password_hash="unused")
            zone = Zone(name="Cap zone", site_id=site.id, capacity=3)
            db.add_all([actor, zone]); db.flush()
            db.add(PortalAccountLink(user_id=actor.id, customer_id=owner.id, verification="test"))
            vehicles = [Vehicle(license_plate=f"CAP-{i}", vehicle_type_id=kind.id, customer_id=owner.id) for i in range(3)]
            slots = [ParkingSlot(slot_name=f"CAP-{i}", vehicle_type_id=kind.id, zone_id=zone.id) for i in range(3)]
            db.add_all(vehicles + slots); db.flush()
            db.add_all([PortalVehicleOwnership(customer_id=owner.id, vehicle_id=v.id, approved_by_id=actor.id, approved_at=now-timedelta(days=1)) for v in vehicles])
            db.commit()
            actor_id, site_id = actor.id, site.id
            vehicle_ids, slot_ids = [v.id for v in vehicles], [s.id for s in slots]
            for i in range(4):
                start = (now + timedelta(days=1, hours=i * 2)).replace(tzinfo=BUSINESS_TZ)
                reservations.reserve(db, actor, ReservationCreate(site_id=site_id, vehicle_id=vehicle_ids[0], slot_id=slot_ids[0],
                    start_at=start, end_at=start+timedelta(hours=1), request_id=uuid4().hex), customer=True)
                db.commit()
        gate, visited = Barrier(2, timeout=10), local()
        def before_lock(connection, cursor, statement, parameters, context, many):
            sql = statement.upper()
            if "FOR " in sql and ("FROM VEHICLES" in sql or "FROM CUSTOMERS" in sql) and not getattr(visited, "seen", False):
                visited.seen = True
                gate.wait()
        def after_count(connection, cursor, statement, parameters, context, many):
            if "count(" in statement.lower() and "parking_reservations" in statement:
                sleep(.2)  # Both old, independently vehicle-locked reads see four.
        def book(index):
            with Session(engine) as db:
                start = (now + timedelta(days=2)).replace(tzinfo=BUSINESS_TZ)
                try:
                    reservations.reserve(db, db.get(User, actor_id), ReservationCreate(site_id=site_id,
                        vehicle_id=vehicle_ids[index], slot_id=slot_ids[index], start_at=start,
                        end_at=start+timedelta(hours=1), request_id=uuid4().hex), customer=True)
                    db.commit()
                    return 201
                except HTTPException as exc:
                    db.rollback()
                    return exc.status_code
        event.listen(engine, "before_cursor_execute", before_lock)
        event.listen(engine, "after_cursor_execute", after_count)
        try:
            with ThreadPoolExecutor(max_workers=2) as pool:
                futures = [pool.submit(book, i) for i in (1, 2)]
                results = [future.result(timeout=20) for future in futures]
        finally:
            event.remove(engine, "before_cursor_execute", before_lock)
            event.remove(engine, "after_cursor_execute", after_count)
        assert sorted(results) == [201, 409]
        with Session(engine) as db:
            assert db.scalar(select(func.count()).select_from(ParkingReservation)) == 5


@pytest.mark.parametrize("scenario", ["same_slot", "waitlist_retry", "checkout_retry", "close_during_checkout", "close_retry", "refund_retry", "refund_bound", "qr_retry"])
def test_postgres_business_races_preserve_single_effect(scenario, monkeypatch):
    from expansion.showcase_seed import seed, ACCOUNTS
    from expansion.site_models import SiteWaitlist
    from expansion import portal_service
    from expansion.portal_schemas import OrderCreate, Simulation
    from expansion.site_schemas import BookingWindow

    monkeypatch.setenv("DEMO_PAYMENTS_ENABLED", "true")
    with _isolated_checkout_postgres() as engine:
        with Session(engine) as db:
            manifest = seed(db, "demopgtest", {name: "$2b$12$" + chr(65+i)*53 for i, name in enumerate(ACCOUNTS)})
            db.commit()
            ids = manifest["ids"]
            staff, manager = db.get(User, ids["staff_a"]), db.get(User, ids["manager_a"])
            shift = CashShiftService.open_shift(db, staff, opening_cash=100000, site_id=ids["site_a"])
            shift_id = shift.id; db.commit()
            quote = CheckoutService(db).quote(ids["initial_session_a"], staff.id)
            confirmation = CheckoutConfirmation(quote_token=quote["quote_token"], payment_confirmed=True, payment_method="cash")
            if scenario.startswith("refund"):
                CheckoutService(db).confirm(confirmation, staff.id, session_id=ids["initial_session_a"])
                original = db.scalar(select(Payment).where(Payment.source_id == ids["initial_session_a"]))
                payment_id, paid = original.id, original.amount
                assert paid > 0
            if scenario == "waitlist_retry":
                start = (business_now()+timedelta(hours=2)).replace(tzinfo=BUSINESS_TZ)
                row = reservations.join_waitlist(db, db.get(User, ids["customer_a"]), BookingWindow(site_id=ids["site_a"],
                    vehicle_id=ids["owned_a_0"], start_at=start, end_at=start+timedelta(hours=1), request_id=uuid4().hex), customer=True)
                waitlist_id = row.id; db.commit()
            if scenario == "qr_retry":
                account = db.get(User, ids["customer_a"])
                order = portal_service.create_order(db, account, OrderCreate(plan_id=ids[f"plan_a_{ids['type_Ô tô']}"],
                    vehicle_id=ids["owned_a_0"], idempotency_key=uuid4().hex, payment_mode="demo"))
                order_id, demo_token = order.id, order.demo_token
                db.commit()
        gate = Barrier(2, timeout=10)
        def perform(index):
            with Session(engine) as db:
                actor = db.get(User, ids["staff_a"])
                gate.wait()
                try:
                    if scenario == "same_slot":
                        suffix = "a" if index == 0 else "b"
                        start = (business_now()+timedelta(hours=2)).replace(tzinfo=BUSINESS_TZ)
                        result = reservations.reserve(db, db.get(User, ids["customer_"+suffix]), ReservationCreate(
                            site_id=ids["site_a"], slot_id=ids["slot_a_0"], vehicle_id=ids["owned_"+suffix+"_0"],
                            start_at=start, end_at=start+timedelta(hours=1), request_id=uuid4().hex), customer=True)
                    elif scenario == "waitlist_retry":
                        result = reservations.offer_waitlist(db, actor, db.get(SiteWaitlist, waitlist_id))
                    elif scenario == "checkout_retry" or (scenario == "close_during_checkout" and index == 0):
                        result = CheckoutService(db).confirm(confirmation, actor.id, session_id=ids["initial_session_a"])
                    elif scenario in {"close_retry", "close_during_checkout"}:
                        result = CashShiftService.close_shift(db, shift_id, actor, counted_cash=100000)
                    elif scenario.startswith("refund"):
                        result = PaymentService.refund(db, payment_id, db.get(User, ids["manager_a"]), amount=paid,
                            method="cash", reason="PG race", idempotency_key="same-refund-key" if scenario == "refund_retry" else uuid4().hex)
                    else:
                        result = portal_service.simulate(db, db.get(User, ids["customer_a"]), order_id, Simulation(token=demo_token, outcome="success"))
                    identity = result.get("id") if isinstance(result, dict) else result.id
                    db.commit()
                    return 200, identity
                except HTTPException as error:
                    db.rollback()
                    return error.status_code, None
        with ThreadPoolExecutor(max_workers=2) as workers:
            futures = [workers.submit(perform, i) for i in range(2)]
            results = [future.result(timeout=25) for future in futures]
        expected = [200, 409] if scenario in {"same_slot", "close_retry", "refund_bound"} else [200, 200]
        assert sorted(status for status, _ in results) == expected, (scenario, results)
        if scenario in {"waitlist_retry", "checkout_retry", "refund_retry", "qr_retry"}:
            assert results[0][1] == results[1][1]
        with Session(engine) as db:
            receipts = db.scalars(select(Payment).where(Payment.source_id == ids["initial_session_a"], Payment.kind == "receipt")).all()
            if scenario in {"checkout_retry", "close_during_checkout", "refund_retry", "refund_bound"}:
                assert len(receipts) == 1 and receipts[0].site_id == ids["site_a"]
                assert not db.get(ParkingSlot, ids["slot_a_8"]).is_occupied
            if scenario.startswith("refund"):
                refunds = db.scalars(select(Payment).where(Payment.original_payment_id == payment_id)).all()
                assert len(refunds) == 1 and refunds[0].amount == paid and refunds[0].site_id == ids["site_a"]
            if scenario == "close_during_checkout":
                closed = db.get(CashShift, shift_id)
                assert closed.status == "closed"
                expected_cash = 100000 + (receipts[0].amount if receipts[0].shift_id == shift_id else 0)
                assert closed.expected_cash == expected_cash
            if scenario == "qr_retry":
                assert db.scalar(select(func.count()).select_from(MonthlyPass)) == 1
                payments = db.scalars(select(Payment).where(Payment.method == "demo")).all()
                assert len(payments) == 1 and payments[0].site_id == ids["site_a"]
                assert PaymentService.revenue_breakdown(db, business_now()-timedelta(days=1), business_now()+timedelta(days=1))["total_revenue"] == 0
