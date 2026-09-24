"""Preserve existing rows while adding approved-preview authority and camera tables."""
import ast
from pathlib import Path

import pytest
from sqlalchemy import create_engine, inspect
from sqlalchemy.dialects import postgresql
from sqlalchemy.schema import CreateIndex, CreateTable

from database import Base
from expansion.simplified_customer_rollout import migrate_simplified_customer


CUSTOMER = {"session_ticket_credentials", "session_payment_access", "declared_parking_reservations"}
CAMERA = {"vision_automation_policies", "vision_passage_events"}


def frozen(revision):
    path = next((Path(__file__).parents[1] / "backend/alembic/versions").glob(revision + "_*.py"))
    tree = ast.parse(path.read_text(encoding="utf-8"))
    return {node.targets[0].id: ast.literal_eval(node.value) for node in tree.body if isinstance(node, ast.Assign)}


def test_existing_sqlite_catalog_and_observation_survive_repeated_rollout(tmp_path):
    engine = create_engine("sqlite:///" + (tmp_path / "prior-schema.db").as_posix())
    try:
        with engine.begin() as connection:
            for table in ("parking_sessions", "parking_sites", "parking_slots", "users", "vehicles", "zones", "vision_cameras"):
                connection.exec_driver_sql(f"CREATE TABLE {table} (id INTEGER PRIMARY KEY)")
            connection.exec_driver_sql("CREATE TABLE vehicle_types(id INTEGER PRIMARY KEY,name VARCHAR(50),custom_note TEXT)")
            connection.exec_driver_sql("INSERT INTO vehicle_types VALUES(1,'Legacy type','preserve operator note')")
            connection.exec_driver_sql("CREATE INDEX custom_type_note ON vehicle_types(custom_note)")
            connection.exec_driver_sql("CREATE TABLE vision_observations(id VARCHAR(36) PRIMARY KEY, private_note TEXT)")
            connection.exec_driver_sql("INSERT INTO vision_observations VALUES('old-photo','unchanged historical row')")
        migrate_simplified_customer(engine)
        migrate_simplified_customer(engine)
        with engine.connect() as connection:
            assert connection.exec_driver_sql("SELECT id,name,custom_note,requires_plate,code_prefix FROM vehicle_types").one() == (
                1, "Legacy type", "preserve operator note", 1, None)
            assert connection.exec_driver_sql("SELECT id,private_note,capture_source FROM vision_observations").one() == (
                "old-photo", "unchanged historical row", "manual_upload")
            schema = inspect(connection)
            assert CUSTOMER | CAMERA <= set(schema.get_table_names())
            assert {row["name"] for row in schema.get_indexes("vehicle_types")} >= {"custom_type_note", "uq_vehicle_types_code_prefix"}
    finally:
        engine.dispose()


@pytest.mark.parametrize("revision,tables", [("20260923_08", CUSTOMER), ("20260923_09", CAMERA)])
def test_frozen_postgres_ddl_contains_current_new_table_constraints(revision, tables):
    values = frozen(revision)
    dialect = postgresql.dialect()
    for name in tables:
        table = Base.metadata.tables[name]
        assert str(CreateTable(table).compile(dialect=dialect)).strip() in values["UPGRADE_SQL"]
        for index in table.indexes:
            assert str(CreateIndex(index).compile(dialect=dialect)) in values["UPGRADE_SQL"]
    assert not any(sql.lstrip().upper().startswith(("UPDATE ", "DELETE ", "DROP TABLE ")) for sql in values["UPGRADE_SQL"])


def test_frozen_guards_and_schema_chain_are_explicit_and_readiness_tracks_new_contracts():
    import postgres_readiness as readiness
    from expansion.simplified_customer_guards import SIMPLIFIED_POSTGRES_GUARD_SQL
    import re
    customer, camera = frozen("20260923_08"), frozen("20260923_09")
    assert customer["down_revision"] == "20260916_07"
    assert camera["down_revision"] == customer["revision"]
    assert SIMPLIFIED_POSTGRES_GUARD_SQL in customer["UPGRADE_SQL"]
    assert readiness.POSTGRES_SCHEMA_REVISION == camera["revision"]
    assert CUSTOMER | CAMERA <= readiness.REQUIRED_TABLES
    assert set(re.findall(r"CREATE TRIGGER (\w+)", SIMPLIFIED_POSTGRES_GUARD_SQL)) <= readiness.REQUIRED_TRIGGERS
    assert {"vehicle_types.requires_plate:boolean::NO", "vehicle_types.code_prefix:character varying:8:YES",
            "vision_observations.capture_source:character varying:16:NO"} <= readiness.REQUIRED_COLUMN_CONTRACTS
    assert "uq_declared_booking_request" in readiness.REQUIRED_CONSTRAINTS
    assert "uq_vision_passage_observation" in readiness.REQUIRED_CONSTRAINTS
    assert any("DEFAULT 'manual_upload'" in sql for sql in camera["UPGRADE_SQL"])
