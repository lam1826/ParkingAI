"""Upgrade a nonempty predecessor provider mapping without rewriting its target."""
import ast
from pathlib import Path

import pytest
from sqlalchemy import create_engine, inspect

from expansion.session_credit_rollout import migrate_session_credit


def _frozen(revision):
    path = next((Path(__file__).parents[1] / "backend/alembic/versions").glob(revision + "_*.py"))
    return {node.targets[0].id: ast.literal_eval(node.value) for node in ast.parse(path.read_text(encoding="utf-8")).body
        if isinstance(node, ast.Assign)}


def test_prior_order_mapping_rows_survive_target_expansion_and_replay(tmp_path):
    engine = create_engine("sqlite:///" + (tmp_path / "mapping.db").as_posix())
    # The frozen PostgreSQL release supplies the exact pre-credit table layout;
    # only physical SQLite type spelling differs for this portable fixture.
    ddl = next(sql for sql in _frozen("20260915_04")["UPGRADE_SQL"] if "CREATE TABLE online_payment_links" in sql)
    ddl = ddl.replace("BIGSERIAL", "INTEGER").replace("BIGINT", "INTEGER").replace("TIMESTAMP WITHOUT TIME ZONE", "DATETIME")
    try:
        with engine.begin() as conn:
            conn.exec_driver_sql("CREATE TABLE portal_orders(id VARCHAR(36) PRIMARY KEY)")
            conn.exec_driver_sql("CREATE TABLE parking_sites(id INTEGER PRIMARY KEY)")
            conn.exec_driver_sql("CREATE TABLE payments(id VARCHAR(36) PRIMARY KEY)")
            conn.exec_driver_sql("INSERT INTO portal_orders VALUES ('prior-order')")
            conn.exec_driver_sql("INSERT INTO parking_sites VALUES (1)")
            conn.exec_driver_sql(ddl)
            conn.exec_driver_sql("ALTER TABLE online_payment_links ADD COLUMN retained_note TEXT")
            conn.exec_driver_sql("CREATE INDEX custom_online_note ON online_payment_links(retained_note)")
            conn.exec_driver_sql("""INSERT INTO online_payment_links
                (id,order_id,site_id,channel,receiver_digest,amount,currency,description,return_url,cancel_url,
                 expires_at,created_at,state,retained_note)
                VALUES (740001,'prior-order',1,'test-channel','digest',180000,'VND','PARKING',
                 'https://example.invalid/return','https://example.invalid/cancel','2026-09-15 11:00:00',
                 '2026-09-15 10:00:00','unknown','retain provider reconciliation')""")
            columns = [c["name"] for c in inspect(conn).get_columns("online_payment_links")]
            before = conn.exec_driver_sql("SELECT * FROM online_payment_links").all()
        migrate_session_credit(engine)
        migrate_session_credit(engine)
        with engine.connect() as conn:
            assert conn.exec_driver_sql("SELECT " + ",".join(columns) + " FROM online_payment_links").all() == before
            assert conn.exec_driver_sql("SELECT session_quote_id FROM online_payment_links").scalar_one() is None
            assert next(c for c in inspect(conn).get_columns("online_payment_links") if c["name"] == "order_id")["nullable"]
            assert "custom_online_note" in {i["name"] for i in inspect(conn).get_indexes("online_payment_links")}
            assert any(i["unique"] and i["column_names"] == ["session_quote_id"] for i in inspect(conn).get_indexes("online_payment_links"))
    finally:
        engine.dispose()


def test_unknown_target_constraint_is_refused_before_schema_changes(tmp_path):
    engine = create_engine("sqlite:///" + (tmp_path / "unknown.db").as_posix())
    try:
        with engine.begin() as conn:
            conn.exec_driver_sql("CREATE TABLE online_payment_links(id INTEGER PRIMARY KEY,order_id VARCHAR(36) NOT NULL,CONSTRAINT ck_online_link_target CHECK(order_id IS NOT NULL))")
            before = conn.exec_driver_sql("SELECT name,sql FROM sqlite_master ORDER BY name").all()
        with pytest.raises(RuntimeError, match="Unknown"):
            migrate_session_credit(engine)
        with engine.connect() as conn:
            assert conn.exec_driver_sql("SELECT name,sql FROM sqlite_master ORDER BY name").all() == before
    finally:
        engine.dispose()


def test_credit_revision_preserves_history_and_replaces_due_guards():
    from database import CHECKOUT_CONFIRMATION_POSTGRES_GUARD_SQL
    from models.payment import PAYMENT_POSTGRES_GUARD_SQL
    from expansion.session_payment_guards import SESSION_PAYMENT_POSTGRES_GUARD_SQL
    frozen = _frozen("20260915_06")
    assert frozen["down_revision"] == "20260915_05"
    statements = frozen["UPGRADE_SQL"]
    assert CHECKOUT_CONFIRMATION_POSTGRES_GUARD_SQL in statements
    assert PAYMENT_POSTGRES_GUARD_SQL.replace("%%", "%") in statements
    assert SESSION_PAYMENT_POSTGRES_GUARD_SQL.replace("%%", "%") in statements
    assert not any(sql.startswith("UPDATE ") or sql.startswith("DELETE ") for sql in statements)
    assert any("committed_session.status IN ('active','checking_out')" in sql for sql in statements)
