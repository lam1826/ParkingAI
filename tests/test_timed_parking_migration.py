"""Known P1 CHECK rebuilds preserve history and reject unknown schema shapes."""
import ast
from pathlib import Path

import pytest
from sqlalchemy import create_engine, inspect

from expansion.timed_parking_rollout import migrate_timed_parking


@pytest.fixture
def p1_catalog(tmp_path):
    engine = create_engine("sqlite:///"+(tmp_path/"p1.db").as_posix())
    with engine.begin() as conn:
        for name in ("zones", "parking_slots"):
            conn.exec_driver_sql(f"CREATE TABLE {name}(id INTEGER PRIMARY KEY)")
        conn.exec_driver_sql("""CREATE TABLE subscription_plans (
            id INTEGER PRIMARY KEY, name VARCHAR(100) NOT NULL, site_id INTEGER,
            vehicle_type_id INTEGER NOT NULL, duration_days INTEGER NOT NULL, price INTEGER NOT NULL,
            is_active BOOLEAN NOT NULL, extra_note TEXT,
            CONSTRAINT ck_portal_plan_duration CHECK(duration_days >= 1 AND duration_days <= 366))""")
        conn.exec_driver_sql("""CREATE TABLE portal_orders (
            id VARCHAR(36) PRIMARY KEY, amount INTEGER NOT NULL, status VARCHAR(12) NOT NULL,
            monthly_pass_id INTEGER, receipt_id VARCHAR(36), payment_mode VARCHAR(8) NOT NULL,
            CONSTRAINT ck_portal_order_mode CHECK(payment_mode IN ('demo','manual')),
            CONSTRAINT ck_portal_order_fulfilled CHECK(status NOT IN ('fulfilled','refunded') OR (monthly_pass_id IS NOT NULL AND receipt_id IS NOT NULL)))""")
        conn.exec_driver_sql("""CREATE TABLE payments (id VARCHAR(36) PRIMARY KEY, source_type VARCHAR(24) NOT NULL,
            source_id VARCHAR(36) NOT NULL, amount INTEGER NOT NULL,
            CONSTRAINT ck_payment_source CHECK(source_type IN ('parking_session', 'monthly_pass')))""")
        conn.exec_driver_sql("INSERT INTO subscription_plans VALUES(1,'Historical monthly',1,1,30,180000,1,'do not alter')")
        conn.exec_driver_sql("INSERT INTO portal_orders VALUES('old-order',180000,'fulfilled',123,'old-receipt','manual')")
        conn.exec_driver_sql("INSERT INTO payments VALUES('old-receipt','monthly_pass','123',180000)")
        conn.exec_driver_sql("CREATE INDEX custom_plan_note ON subscription_plans(extra_note)")
        conn.exec_driver_sql("CREATE TRIGGER custom_plan_delete BEFORE DELETE ON subscription_plans BEGIN SELECT RAISE(ABORT,'keep historical'); END")
    try:
        yield engine
    finally:
        engine.dispose()


def test_p1_catalog_rebuild_preserves_values_objects_and_null_legacy_snapshots(p1_catalog):
    engine=p1_catalog
    with engine.connect() as conn:
        before={table: conn.exec_driver_sql(f"SELECT * FROM {table}").all()
            for table in ("subscription_plans","portal_orders","payments")}
        columns={table:[item["name"] for item in inspect(engine).get_columns(table)] for table in before}
    migrate_timed_parking(engine)
    migrate_timed_parking(engine)
    with engine.connect() as conn:
        for table,names in columns.items():
            assert conn.exec_driver_sql(f'SELECT {",".join(names)} FROM {table}').all()==before[table]
        assert conn.exec_driver_sql("SELECT product_kind,plan_name,start_at,end_at,rate_config_id,timed_pass_id FROM portal_orders").one()==("monthly",None,None,None,None,None)
        assert conn.exec_driver_sql("SELECT product_kind,duration_minutes FROM subscription_plans").one()==("monthly",None)
        assert conn.exec_driver_sql("SELECT COUNT(*) FROM sqlite_master WHERE name IN ('custom_plan_note','custom_plan_delete')").scalar_one()==2
        assert next(c for c in inspect(engine).get_columns("subscription_plans") if c["name"]=="duration_days")["nullable"] is True


def test_unknown_catalog_check_is_refused_before_mutation(tmp_path):
    engine=create_engine("sqlite:///"+(tmp_path/"unknown.db").as_posix())
    try:
        with engine.begin() as conn:
            conn.exec_driver_sql("CREATE TABLE subscription_plans(id INTEGER PRIMARY KEY,duration_days INTEGER NOT NULL,CONSTRAINT ck_portal_plan_duration CHECK(duration_days>0))")
        with engine.connect() as conn:
            before=conn.exec_driver_sql("SELECT sql FROM sqlite_master WHERE name='subscription_plans'").scalar_one()
        with pytest.raises(RuntimeError,match="CHECK"):
            migrate_timed_parking(engine)
        with engine.connect() as conn:
            assert conn.exec_driver_sql("SELECT sql FROM sqlite_master WHERE name='subscription_plans'").scalar_one()==before
    finally:
        engine.dispose()


def test_postgres_prepaid_revision_is_frozen_and_preserves_old_billing_policy():
    path=Path(__file__).resolve().parents[1]/"backend/alembic/versions/20260915_03_timed_parking.py"
    tree=ast.parse(path.read_text(encoding="utf-8"))
    constants={n.targets[0].id:ast.literal_eval(n.value) for n in tree.body if isinstance(n,ast.Assign)}
    sql="\n".join(constants["UPGRADE_SQL"])
    assert constants["down_revision"]=="20260915_02"
    assert "'entry-v1','prepaid-window-v1'" in sql
    assert "clock_timestamp() AT TIME ZONE" in sql
    assert "FOR SHARE" in sql and "FOR UPDATE" in sql
    assert "CREATE TABLE parking_capacity_holds" in sql
    assert "CREATE TABLE timed_parking_passes" in sql
    assert "DROP TABLE" not in sql
    assert "UPDATE parking_sessions SET" not in sql
