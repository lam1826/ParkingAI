import os
import pytest
pytestmark = pytest.mark.skipif(not os.getenv("POSTGRES_TEST_URL"), reason="Disposable PostgreSQL required")
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from datetime import timedelta
from threading import Barrier, Lock, get_ident

from fastapi.testclient import TestClient
from sqlalchemy import event, func, select
from sqlalchemy.orm import Session

from core.clock import business_now
from database import get_db
from expansion.site_models import ParkingSite, SiteMembership
from main import app
from models import ParkingSession, ParkingSlot, PriceConfig, Role, User, VehicleType, Zone
from services.auth_service import AuthService
from test_postgres_integration import _isolated_checkout_postgres


def _seed(engine, rounds, layout):
    now = business_now()
    with Session(engine) as db:
        role, kind, site = Role(name="staff"), VehicleType(name="Race car"), ParkingSite(name="Race lot")
        db.add_all([role, kind, site]); db.flush()
        users = [User(username=f"op-{k}", password_hash=f"unused-{k}", full_name=f"Operator {k}",
                      role_id=role.id, is_active=True) for k in "ab"]
        db.add_all(users); db.flush()
        db.add_all([SiteMembership(site_id=site.id, user_id=u.id, role="staff") for u in users])
        db.add(PriceConfig(vehicle_type_id=kind.id, ticket_type="HOURLY", price=10000,
                           effective_date=(now - timedelta(days=1)).date()))
        pairs = []
        for r in range(rounds):
            if layout == "same_zone":
                zone = Zone(name=f"Z{r}", site_id=site.id, capacity=2); db.add(zone); db.flush()
                slots = [ParkingSlot(slot_name=f"R{r}-P{i}", vehicle_type_id=kind.id, zone_id=zone.id) for i in range(2)]
            else:  # control: different zones of the same site
                zones = [Zone(name=f"Z{r}-{i}", site_id=site.id, capacity=1) for i in range(2)]
                db.add_all(zones); db.flush()
                slots = [ParkingSlot(slot_name=f"R{r}-P{i}", vehicle_type_id=kind.id, zone_id=zones[i].id) for i in range(2)]
            db.add_all(slots); db.flush()
            pairs.append((slots[0].id, slots[1].id))
        db.commit()
        tokens = [AuthService().create_access_token(user_id=u.id, username=u.username, role="staff",
                                                    password_hash=u.password_hash) for u in users]
        return site.id, kind.id, pairs, tokens


@contextmanager
def _pg_app(engine):
    def override_get_db():
        db = Session(engine)
        try:
            yield db
        finally:
            db.close()
    app.dependency_overrides[get_db] = override_get_db
    errors, guard = [], Lock()

    def on_error(context):
        err = context.original_exception
        with guard:
            errors.append((type(err).__name__, getattr(err, "sqlstate", None),
                           " ".join(str(err).split())[:220]))
    event.listen(engine, "handle_error", on_error)
    try:
        yield errors
    finally:
        event.remove(engine, "handle_error", on_error)
        app.dependency_overrides.pop(get_db, None)


def _race(engine, rounds, layout, mode="explicit", pause_after_share=False):
    site_id, kind_id, pairs, tokens = _seed(engine, rounds, layout)
    clients = [TestClient(app, raise_server_exceptions=False) for _ in range(2)]
    outcomes = []
    with _pg_app(engine) as errors:
        for r, (s0, s1) in enumerate(pairs):
            if r:
                # Retire the previous round's leftover free slot so auto-assign targets this round's zone.
                with Session(engine) as db:
                    db.execute(ParkingSlot.__table__.update().where(
                        ParkingSlot.id.in_(pairs[r - 1]), ParkingSlot.is_occupied.is_(False)).values(is_active=False))
                    db.commit()
            start = Barrier(2, timeout=10)
            share_barrier, seen, seen_lock = Barrier(2, timeout=5), set(), Lock()

            def after(connection, cursor, statement, parameters, context, executemany):
                if "FOR SHARE OF zones" not in statement:
                    return
                with seen_lock:
                    first = get_ident() not in seen
                    seen.add(get_ident())
                if first:
                    try:
                        share_barrier.wait()
                    except Exception:
                        pass

            if pause_after_share:
                event.listen(engine, "after_cursor_execute", after)

            def admit(k, slot):
                body = {"license_plate": f"51A-{100 + r:03d}.{11 * (k + 1):02d}", "vehicle_type_id": kind_id}
                if slot is not None:
                    body["parking_slot_id"] = slot
                start.wait()
                resp = clients[k].post(f"/api/v2/sites/{site_id}/check-in", json=body,
                                       headers={"Authorization": f"Bearer {tokens[k]}"})
                detail = resp.json().get("slot_name") if resp.status_code == 201 else resp.json().get("detail")
                return resp.status_code, detail

            slots_for = {"explicit": (s0, s1), "mixed": (None, s1)}[mode]
            try:
                with ThreadPoolExecutor(max_workers=2) as pool:
                    futures = [pool.submit(admit, k, slots_for[k]) for k in range(2)]
                    outcomes.append(tuple(f.result(timeout=40) for f in futures))
            finally:
                if pause_after_share:
                    event.remove(engine, "after_cursor_execute", after)
        snapshot = list(errors)
    with Session(engine) as db:
        sessions = db.scalar(select(func.count()).select_from(ParkingSession))
        occupied = db.scalar(select(func.count()).select_from(ParkingSlot).where(ParkingSlot.is_occupied.is_(True)))
    return outcomes, snapshot, sessions, occupied


def _report(label, outcomes, errors, sessions, occupied):
    statuses = Counter(code for pair in outcomes for code, _ in pair)
    failed_rounds = sum(1 for pair in outcomes if any(code != 201 for code, _ in pair))
    deadlocks = [e for e in errors if e[1] == "40P01"]
    print(f"\n[{label}] ROUNDS {len(outcomes)} FAILED_ROUNDS {failed_rounds} STATUS {dict(statuses)} "
          f"DEADLOCKS {len(deadlocks)} SESSIONS {sessions} OCCUPIED {occupied}")
    print(f"[{label}] first outcomes: {outcomes[:3]}")
    if deadlocks:
        print(f"[{label}] first deadlock: {deadlocks[0]}")
    non_deadlock = [e for e in errors if e[1] != "40P01"]
    if non_deadlock:
        print(f"[{label}] other DB errors: {non_deadlock[:3]}")
    return failed_rounds, deadlocks


def test_same_zone_admissions_do_not_deadlock():
    with _isolated_checkout_postgres() as engine:
        outcomes, errors, sessions, occupied = _race(engine, 1, 'same_zone', pause_after_share=True)
        assert [code for pair in outcomes for code,_ in pair] == [201,201], (outcomes,errors)
        assert not errors
        assert sessions == occupied == 2


def test_concurrent_admissions_same_and_different_zones():
    for layout in ('same_zone','different_zones'):
        with _isolated_checkout_postgres() as engine:
            outcomes, errors, sessions, occupied = _race(engine, 5, layout)
            assert all(code == 201 for pair in outcomes for code,_ in pair), (outcomes,errors)
            assert not errors
            assert sessions == occupied == 10
