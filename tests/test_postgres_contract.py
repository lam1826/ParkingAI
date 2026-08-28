from pathlib import Path
import tomllib

from sqlalchemy.dialects import postgresql, sqlite

import database
from core.money import VND_DATABASE_TYPE
from models.monthly_pass import MonthlyPass
from models.parking_session import ParkingSession
from models.price_config import PriceConfig
from postgres_readiness import (
    POSTGRES_SCHEMA_REVISION,
    REQUIRED_CONSTRAINTS,
    REQUIRED_INDEXES,
    REQUIRED_TABLES,
    REQUIRED_TRIGGERS,
    _validate_catalog,
)


def test_vnd_storage_is_bigint_on_postgres_and_integer_on_sqlite():
    assert str(VND_DATABASE_TYPE.compile(dialect=postgresql.dialect())) == "BIGINT"
    assert str(VND_DATABASE_TYPE.compile(dialect=sqlite.dialect())) == "INTEGER"


def test_partial_unique_indexes_have_postgres_predicates():
    indexes = {
        index.name: index
        for table in (PriceConfig.__table__, MonthlyPass.__table__, ParkingSession.__table__)
        for index in table.indexes
    }
    for name in (
        "uq_price_config_one_active_per_vehicle_type",
        "ix_monthly_passes_pass_code",
        "uq_parking_session_one_active_per_vehicle",
        "uq_parking_session_one_active_per_slot",
    ):
        assert indexes[name].dialect_options["postgresql"]["where"] is not None


def test_engine_factory_does_not_leak_sqlite_connect_args_to_postgres(monkeypatch):
    captured = {}
    for name in ("DB_POOL_SIZE", "DB_MAX_OVERFLOW", "DB_POOL_RECYCLE_SECONDS"):
        monkeypatch.delenv(name, raising=False)

    def fake_create_engine(url, **options):
        captured.update(url=url, options=options)
        return object()

    monkeypatch.setattr(database, "create_engine", fake_create_engine)
    database.create_database_engine("postgresql+psycopg://example.invalid/db")

    assert captured["options"]["pool_pre_ping"] is True
    assert "connect_args" not in captured["options"]
    assert captured["options"]["pool_size"] == 5
    assert captured["options"]["max_overflow"] == 5
    assert captured["options"]["pool_recycle"] == 1800


def test_engine_factory_normalizes_plain_postgres_url_to_psycopg3(monkeypatch):
    captured = {}

    def fake_create_engine(url, **options):
        captured["url"] = url
        return object()

    monkeypatch.setattr(database, "create_engine", fake_create_engine)
    database.create_database_engine("postgresql://example.invalid/parkingai")
    assert captured["url"] == "postgresql+psycopg://example.invalid/parkingai"


def test_postgres_baseline_declares_every_readiness_backstop():
    migration = (
        Path(__file__).parents[1]
        / "backend"
        / "alembic"
        / "versions"
        / f"{POSTGRES_SCHEMA_REVISION}_initial_postgresql.py"
    ).read_text(encoding="utf-8")

    for name in (
        *REQUIRED_TABLES,
        *REQUIRED_INDEXES,
        *REQUIRED_CONSTRAINTS,
        *REQUIRED_TRIGGERS,
    ):
        assert name in migration
    assert "CREATE EXTENSION IF NOT EXISTS btree_gist" in migration
    assert "unicode_casefold" in migration
    assert "TG_OP = 'INSERT' AND NEW.monthly_pass_id IS NOT NULL" in migration


def test_delivery_targets_fly_after_verified_main_ci():
    workflow = (
        Path(__file__).parents[1] / ".github" / "workflows" / "delivery.yml"
    ).read_text(encoding="utf-8")
    assert "environment: production" in workflow
    assert "superfly/flyctl-actions/setup-flyctl@master" in workflow
    assert "FLY_API_TOKEN: ${{ secrets.FLY_API_TOKEN }}" in workflow
    assert "flyctl deploy" in workflow
    assert "--remote-only" in workflow
    assert '--env "RELEASE_ID=$RELEASE_SHA"' in workflow
    assert "https://api.parkingai.am" in workflow
    assert "https://parkingai.am" in workflow
    assert "DEPLOY_SSH_PRIVATE_KEY" not in workflow
    assert "docker/build-push-action" not in workflow


def test_fly_config_runs_migrations_and_keeps_one_machine_warm():
    path = Path(__file__).parents[1] / "backend" / "fly.toml"
    raw = path.read_text(encoding="utf-8")
    config = tomllib.loads(raw)

    assert config["app"] == "parkingai-api-lam1826"
    assert config["primary_region"] == "sin"
    assert config["build"]["dockerfile"] == "Dockerfile"
    assert config["deploy"]["release_command"] == (
        "alembic -c alembic.ini upgrade head"
    )
    assert config["http_service"]["force_https"] is True
    assert config["http_service"]["min_machines_running"] == 1
    assert config["http_service"]["checks"][0]["path"] == "/ready"
    assert "DATABASE_URL" not in raw
    assert "SECRET_KEY" not in raw


def test_blue_green_release_contract_is_locked_and_digest_only():
    root = Path(__file__).parents[1]
    common = (root / "deploy" / "scripts" / "common.sh").read_text(
        encoding="utf-8"
    )
    deploy = (root / "deploy" / "scripts" / "deploy.sh").read_text(
        encoding="utf-8"
    )
    assert "@sha256:" in common
    assert "acquire_deploy_lock" in deploy
    assert deploy.index("acquire_deploy_lock") < deploy.index("migrate_image")
    assert "compose up -d --no-deps backend_blue backend_green" in deploy


def test_runtime_catalog_gate_accepts_future_expand_contract_revision():
    class Result:
        def __init__(self, value):
            self.value = value

        def scalar_one(self):
            return self.value

        def scalars(self):
            return iter(self.value)

    class Connection:
        def execute(self, statement):
            sql = str(statement)
            if sql == "SHOW server_encoding":
                return Result("UTF8")
            if "FROM alembic_version" in sql:
                return Result("20260828_02_future_expand")
            if "pg_catalog.pg_tables" in sql:
                return Result(REQUIRED_TABLES)
            if "pg_catalog.pg_indexes" in sql:
                return Result(REQUIRED_INDEXES)
            if "pg_catalog.pg_constraint" in sql:
                return Result(REQUIRED_CONSTRAINTS)
            if "information_schema.triggers" in sql:
                return Result(REQUIRED_TRIGGERS)
            if "pg_catalog.pg_proc" in sql:
                return Result(True)
            raise AssertionError(f"Unexpected catalog SQL: {sql}")

    _validate_catalog(Connection())
