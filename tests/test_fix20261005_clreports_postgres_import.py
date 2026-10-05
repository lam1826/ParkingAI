"""#69: postgres_import.py must import a current SQLite database (monthly passes included).

The importer's source gate accepts only a SQLite file at the CURRENT schema, but it copied a fixed
legacy subset of 12 tables: any monthly pass failed the PostgreSQL card binding (cards were never
copied), receipts/shifts/sites/expansion data were dropped, and the deep readiness ran only after
COMMIT, leaving a half-filled target that every retry refused.

The SQLite-only tests run everywhere. The PostgreSQL round trip uses the same disposable database
helper as the other PostgreSQL regressions (designated loopback CI service only).
"""
from __future__ import annotations

import json
import uuid
from datetime import timedelta

import bcrypt
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import JSON, create_engine, select, text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.sql.elements import Null

import postgres_import
from core.clock import business_now
from database import Base, get_db
from db_rollout import initialize_database
from expansion.site_models import ParkingSite, SiteMembership
from main import app
from models import Customer, ParkingSlot, PriceConfig, Role, User, Vehicle, VehicleType, Zone
from services.auth_service import AuthService
from test_postgres_integration import POSTGRES_TEST_URL, _isolated_checkout_postgres


def test_copy_order_covers_every_current_table_with_parents_first():
    order = postgres_import.COPY_ORDER
    assert set(order) == set(Base.metadata.tables)
    assert len(order) == len(set(order))
    position = {name: index for index, name in enumerate(order)}
    for name in order:
        for key in Base.metadata.tables[name].foreign_keys:
            parent = key.column.table.name
            if parent != name:
                assert position[parent] < position[name], (parent, name)
    assert position["parking_cards"] < position["monthly_passes"]


def test_json_columns_keep_sql_null_json_null_and_objects_distinct():
    column = Base.metadata.tables["parking_session_events"].c.before_state
    assert isinstance(column.type, JSON)
    assert isinstance(postgres_import._convert_value(column, None), Null)
    assert postgres_import._convert_value(column, "null") is JSON.NULL
    assert postgres_import._convert_value(column, '{"status": "active", "n": 1}') == {"status": "active", "n": 1}


def test_every_current_table_can_be_read_including_tables_without_id(tmp_path):
    source = tmp_path / "current.db"
    initialize_database(source)
    keyed_otherwise = [name for name in postgres_import.COPY_ORDER
                       if [c.name for c in Base.metadata.tables[name].primary_key.columns] != ["id"]]
    assert {"session_ticket_credentials", "occupancy_calibration_slots"} <= set(keyed_otherwise)
    connection = postgres_import._readonly_sqlite_connection(source)
    try:
        for name in postgres_import.COPY_ORDER:
            postgres_import._read_rows(connection, name)
    finally:
        connection.close()


# ---------------------------------------------------------------------------
# PostgreSQL round trip (CI loopback service only)
# ---------------------------------------------------------------------------

def _headers(user):
    token = AuthService().create_access_token(user_id=user.id, username=user.username,
        role=user.role.name, password_hash=user.password_hash)
    return {"Authorization": f"Bearer {token}"}


def _build_current_source(path):
    """A current-schema SQLite file populated through the real API flows."""
    initialize_database(path)
    engine = create_engine(f"sqlite:///{path.as_posix()}", connect_args={"check_same_thread": False})
    factory = sessionmaker(bind=engine, autoflush=False)

    def override():
        db = factory()
        try:
            yield db
        finally:
            db.close()

    with factory() as db:
        password = bcrypt.hashpw(b"password123", bcrypt.gensalt()).decode()
        manager_role, staff_role = Role(name="manager"), Role(name="staff")
        db.add_all([manager_role, staff_role])
        db.flush()
        manager = User(username="import_mgr", role_id=manager_role.id, password_hash=password, full_name="Mgr", is_active=True)
        staff = User(username="import_staff", role_id=staff_role.id, password_hash=password, full_name="Staff", is_active=True)
        customer = Customer(full_name="Khách nhập", phone_number="0900000001")
        kind = VehicleType(name="Ô tô nhập", description="x")
        db.add_all([manager, staff, customer, kind])
        db.flush()
        site_id = db.scalar(select(ParkingSite.id).order_by(ParkingSite.id))
        db.add_all([SiteMembership(site_id=site_id, user_id=manager.id, role="manager"),
                    SiteMembership(site_id=site_id, user_id=staff.id, role="staff")])
        car = Vehicle(license_plate="30A99999", vehicle_type_id=kind.id, customer_id=customer.id)
        walk_in = Vehicle(license_plate="30A88888", vehicle_type_id=kind.id)
        zone = Zone(name="Khu nhập", capacity=10, is_active=True, site_id=site_id)
        db.add_all([car, walk_in, zone])
        db.flush()
        slots = [ParkingSlot(zone_id=zone.id, vehicle_type_id=kind.id, slot_name=f"N-{i}", is_occupied=False, is_active=True)
                 for i in range(2)]
        db.add_all(slots + [PriceConfig(vehicle_type_id=kind.id, is_active=True, ticket_type="HOURLY", price=25000,
                                        effective_date=(business_now() - timedelta(days=1)).date())])
        db.commit()
        ids = dict(customer=customer.id, car=car.id, walk_in=walk_in.id, slots=[slot.id for slot in slots])
        manager_headers, staff_headers = _headers(manager), _headers(staff)

    saved = dict(app.dependency_overrides)
    app.dependency_overrides[get_db] = override
    try:
        with TestClient(app) as client:
            today = business_now().date()
            sold = client.post("/api/v1/monthly-passes", headers=manager_headers, json={
                "customer_id": ids["customer"], "vehicle_id": ids["car"], "pass_code": "CARD-IMPORT",
                "price": 500000, "start_date": today.isoformat(),
                "end_date": (today + timedelta(days=30)).isoformat(), "is_active": True, "payment_method": "cash"})
            assert sold.status_code == 201, sold.text
            stay = client.post("/api/v1/parking-sessions/check-in", headers=staff_headers,
                               json={"vehicle_id": ids["walk_in"], "parking_slot_id": ids["slots"][0]})
            assert stay.status_code == 201, stay.text
            quote = client.get(f"/api/v1/parking-sessions/{stay.json()['id']}/checkout-quote", headers=staff_headers).json()
            paid = client.put(f"/api/v1/parking-sessions/{stay.json()['id']}/check-out", headers=staff_headers,
                              json={"quote_token": quote["quote_token"], "payment_confirmed": True,
                                    "payment_method": "cash" if quote["parking_fee"] > 0 else None})
            assert paid.status_code == 200, paid.text
            mistaken = client.post("/api/v1/parking-sessions/check-in", headers=staff_headers,
                                   json={"vehicle_id": ids["walk_in"], "parking_slot_id": ids["slots"][1]})
            assert mistaken.status_code == 201, mistaken.text
            cancelled = client.post(f"/api/v1/parking-sessions/{mistaken.json()['id']}/cancel", headers=manager_headers,
                                    json={"reason": "Nhập nhầm lượt tại cổng", "request_id": "import-cancel-1"})
            assert cancelled.status_code == 200, cancelled.text
    finally:
        app.dependency_overrides.clear()
        app.dependency_overrides.update(saved)
    with engine.connect() as connection:
        counts = {name: connection.execute(text(f'SELECT count(*) FROM "{name}"')).scalar_one()
                  for name in postgres_import.COPY_ORDER}
        events = [(row[0], json.loads(row[1]), json.loads(row[2])) for row in connection.execute(text(
            "SELECT id, before_state, after_state FROM parking_session_events ORDER BY id"))]
    engine.dispose()
    return counts, events


def _destination_counts(engine):
    with engine.connect() as connection:
        return {name: connection.execute(text(f'SELECT count(*) FROM "{name}"')).scalar_one()
                for name in postgres_import.COPY_ORDER}


@pytest.mark.skipif(not POSTGRES_TEST_URL, reason="Requires the isolated PostgreSQL CI service")
def test_current_sqlite_with_monthly_pass_imports_completely_and_atomically(tmp_path, monkeypatch):
    source = tmp_path / f"source-{uuid.uuid4().hex[:8]}.db"
    source_counts, source_events = _build_current_source(source)
    for table in ("parking_cards", "monthly_passes", "payments", "parking_session_events", "site_memberships"):
        assert source_counts[table] > 0, table

    with _isolated_checkout_postgres() as engine:
        url = engine.url.render_as_string(hide_password=False)
        before = _destination_counts(engine)

        def broken_invariants(connection):
            raise RuntimeError("simulated invariant failure")

        with monkeypatch.context() as patch:
            patch.setattr(postgres_import, "_validate_business_invariants", broken_invariants)
            with pytest.raises(RuntimeError, match="simulated invariant failure"):
                postgres_import.import_sqlite_to_postgres(source, url)
        assert _destination_counts(engine) == before  # rolled back, placeholder site kept

        imported = postgres_import.import_sqlite_to_postgres(source, url)
        assert imported == source_counts
        assert _destination_counts(engine) == source_counts
        with engine.connect() as connection:
            events = [(row[0], row[1], row[2]) for row in connection.execute(text(
                "SELECT id, before_state, after_state FROM parking_session_events ORDER BY id"))]
            assert events == source_events
            assert connection.execute(text(
                "SELECT count(*) FROM monthly_passes WHERE card_id IS NOT NULL")).scalar_one() == source_counts["monthly_passes"]
        with engine.connect() as probe:  # sequences continue after the imported ids
            new_role = probe.execute(text("INSERT INTO roles (name) VALUES ('sequence-probe') RETURNING id")).scalar_one()
            assert new_role > source_counts["roles"]
            probe.rollback()
        with pytest.raises(RuntimeError, match="không rỗng"):
            postgres_import.import_sqlite_to_postgres(source, url)
