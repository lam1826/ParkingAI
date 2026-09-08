"""Real concurrent SQLite transactions; no shared connection masquerading as concurrency."""
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from time import monotonic

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select, func
from sqlalchemy.orm import sessionmaker

from test_portal_api import portal, onboard
from database import get_db
from expansion.portal_router import router
from expansion.portal_schemas import Simulation
from expansion.portal_service import simulate
from expansion.portal_models import PortalPaymentEvent
from middleware.audit import AuditLogMiddleware
from models.audit_log import AuditLog
from models.monthly_pass import MonthlyPass
from models.payment import Payment
from models.user import User
from services.auth_service import AuthService, get_current_user


def test_two_simultaneous_confirmations_issue_exactly_one_period_and_receipt(portal, tmp_path):
    client, current, users, site, kind, source_db = portal
    order = client.post("/api/v2/me/orders", json=onboard(portal)).json()
    owner_id = users[1].id
    source_db.commit()
    engine = create_engine("sqlite:///" + (tmp_path / "portal-concurrent.sqlite").as_posix(),
        connect_args={"timeout": 15, "check_same_thread": False})
    # Clone only this test's in-memory database, including its integrity guards.
    source = source_db.get_bind().raw_connection()
    target = engine.raw_connection()
    try:
        source.driver_connection.backup(target.driver_connection)
    finally:
        source.close()
        target.close()
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    barrier = Barrier(2)
    def confirm():
        with factory() as db:
            actor = db.get(User, owner_id)
            barrier.wait(timeout=10)
            result = simulate(db, actor, order["id"], Simulation(token=order["demo_token"], outcome="success"))
            return result.monthly_pass_id, result.receipt_id
    try:
        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = [pool.submit(confirm) for _ in range(2)]
            results = [future.result(timeout=25) for future in futures]
        assert results[0] == results[1]
        with factory() as db:
            assert db.scalar(select(func.count()).select_from(MonthlyPass)) == 1
            assert db.scalar(select(func.count()).select_from(Payment)) == 1
            assert db.scalar(select(func.count()).select_from(PortalPaymentEvent)) == 1
    finally:
        engine.dispose()


def test_order_replay_releases_sqlite_writer_before_audit(portal, tmp_path):
    body = onboard(portal)
    _, _, users, _, _, source_db = portal
    source_db.commit()
    engine = create_engine(
        "sqlite:///" + (tmp_path / "portal-replay.sqlite").as_posix(),
        connect_args={"timeout": 0.2, "check_same_thread": False},
    )
    source = source_db.get_bind().raw_connection()
    target = engine.raw_connection()
    try:
        source.driver_connection.backup(target.driver_connection)
    finally:
        source.close()
        target.close()
    factory = sessionmaker(bind=engine, expire_on_commit=False)

    def request_db():
        with factory() as db:
            yield db

    user = users[1]
    token = AuthService().create_access_token(
        user_id=user.id,
        username=user.username,
        role=user.role.name,
    )
    app = FastAPI()
    app.include_router(router, prefix="/api/v2")
    app.add_middleware(AuditLogMiddleware)
    app.dependency_overrides[get_db] = request_db
    app.dependency_overrides[get_current_user] = lambda: user
    headers = {"Authorization": f"Bearer {token}"}

    try:
        with TestClient(app) as client:
            created = client.post("/api/v2/me/orders", json=body, headers=headers)
            started = monotonic()
            replay = client.post("/api/v2/me/orders", json=body, headers=headers)
            elapsed = monotonic() - started
        assert created.status_code == 200
        assert replay.status_code == 200
        assert replay.json()["id"] == created.json()["id"]
        assert elapsed < 0.5
        with factory() as db:
            assert db.scalar(select(func.count()).select_from(AuditLog)) == 2
    finally:
        engine.dispose()
