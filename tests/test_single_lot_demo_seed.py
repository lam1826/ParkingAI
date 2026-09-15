from datetime import date
import hashlib
import json
from pathlib import Path
import sqlite3

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from database import create_database_engine
from expansion.single_lot_seed import create_single_lot_demo


@pytest.fixture(scope="module")
def seeded_demo(tmp_path_factory):
    target = tmp_path_factory.mktemp("single-lot") / "academic.db"
    result = create_single_lot_demo(target)
    return target, result


def test_new_profile_has_one_lot_complete_catalog_and_private_random_credentials(seeded_demo):
    from services.auth_service import AuthService
    from models.user import User
    target, result = seeded_demo
    assert result["profile"] == "single-lot-academic-v1"
    assert result["history_days"] == 14
    marker = Path(str(target) + ".demo.json").read_text(encoding="utf-8")
    credentials = json.loads(Path(result["credentials_file"]).read_text(encoding="utf-8"))["accounts"]
    assert set(credentials) == {"admin_demo", "manager_demo", "staff_demo", "customer_demo"}
    assert len(set(credentials.values())) == 4
    assert all(len(password) >= 24 and password not in marker for password in credentials.values())
    engine = create_database_engine("sqlite:///" + target.as_posix())
    try:
        with Session(engine) as db:
            for user in db.scalars(select(User)):
                assert AuthService.verify_password(credentials[user.username], user.password_hash)
    finally:
        engine.dispose()
    with sqlite3.connect(target) as db:
        assert db.execute("SELECT count(*) FROM parking_sites").fetchone()[0] == 1
        assert db.execute("SELECT count(*), sum(capacity) FROM zones").fetchone() == (3, 40)
        assert db.execute("SELECT count(*), sum(is_active), sum(is_occupied) FROM parking_slots").fetchone() == (40, 36, 2)
        assert db.execute("SELECT count(*) FROM parking_slots s JOIN vehicle_types t ON t.id=s.vehicle_type_id WHERE s.is_active=1 AND t.name='Xe máy DEMO'").fetchone()[0] == 24
        assert db.execute("SELECT count(*) FROM parking_slots s JOIN vehicle_types t ON t.id=s.vehicle_type_id WHERE s.is_active=1 AND t.name='Ô tô DEMO'").fetchone()[0] == 12
        assert db.execute("SELECT count(*) FROM monthly_passes").fetchone()[0] == 3
        assert db.execute("SELECT count(*) FROM parking_sessions WHERE status='active' AND billing_policy_version='entry-v1'").fetchone()[0] == 2
        assert db.execute("SELECT count(*) FROM parking_sessions WHERE status='completed' AND billing_policy_version IS NOT NULL").fetchone()[0] == 0
        generated = date.fromisoformat(result["generated_at"][:10])
        for name, row in result["monthly_examples"].items():
            days = (date.fromisoformat(row["end_date"]) - generated).days
            assert days == {"valid": 24, "near_expiry": 2, "expired": -11}[name]
            assert row["price"] == 0


def test_synthetic_traffic_ledger_and_occupancy_are_consistent(seeded_demo):
    target, result = seeded_demo
    with sqlite3.connect(target) as db:
        assert db.execute("SELECT count(DISTINCT date(check_in_time)) FROM parking_sessions WHERE status='completed'").fetchone()[0] == 14
        assert db.execute("SELECT count(*) FROM parking_sessions WHERE status='completed' AND image_in_url LIKE 'demo://synthetic-history/%'").fetchone()[0] == result["synthetic_closed_sessions"]
        assert db.execute("SELECT count(*) FROM parking_sessions s LEFT JOIN payments p ON p.source_id=s.id AND p.source_type='parking_session' AND p.kind='receipt' WHERE s.status='completed' AND (p.id IS NULL OR p.amount != s.parking_fee)").fetchone()[0] == 0
        assert db.execute("SELECT count(*) FROM payments WHERE source_type='parking_session' AND (site_id IS NULL OR shift_id IS NULL OR method!='cash')").fetchone()[0] == 0
        assert db.execute("SELECT count(*), sum(amount) FROM payments WHERE source_type='parking_session'").fetchone() == (result["synthetic_cash_receipts"], result["synthetic_cash_revenue"])
        assert db.execute("SELECT count(*) FROM payments WHERE source_type='monthly_pass' AND amount=0 AND method='demo' AND collected_by_id IS NULL AND shift_id IS NULL").fetchone()[0] == result["complimentary_monthly_receipts"] == 3
        assert db.execute("SELECT count(*) FROM monthly_passes WHERE card_id IS NULL").fetchone()[0] == 0
        assert result["synthetic_cash_revenue"] > 0 and result["real_money_received"] == 0
        assert db.execute("SELECT count(*) FROM cash_shifts WHERE status='closed' AND difference=0").fetchone()[0] == 14
        assert db.execute("SELECT count(*) FROM cash_shifts c WHERE c.expected_cash != (SELECT sum(amount) FROM payments p WHERE p.shift_id=c.id)").fetchone()[0] == 0
        assert db.execute("SELECT count(*) FROM parking_slots s WHERE s.is_occupied != EXISTS(SELECT 1 FROM parking_sessions p WHERE p.parking_slot_id=s.id AND p.status='active')").fetchone()[0] == 0
        assert db.execute("SELECT count(*) FROM parking_sessions a JOIN parking_sessions b ON a.id < b.id AND (a.parking_slot_id=b.parking_slot_id OR a.vehicle_id=b.vehicle_id) WHERE a.check_in_time < COALESCE(b.check_out_time, '9999') AND b.check_in_time < COALESCE(a.check_out_time, '9999')").fetchone()[0] == 0


def test_fresh_seed_finance_is_complete_without_later_backfill(seeded_demo, tmp_path):
    from db_rollout import migrate_copy, initialize_database
    source, _ = seeded_demo
    target = tmp_path / "reinitialized.db"
    migrate_copy(source, target)
    initialize_database(target)
    with sqlite3.connect(source) as before, sqlite3.connect(target) as after:
        for table in ("payments", "parking_cards", "monthly_passes", "parking_sessions"):
            assert before.execute(f"SELECT * FROM {table} ORDER BY id").fetchall() == after.execute(f"SELECT * FROM {table} ORDER BY id").fetchall()


def test_one_lot_roles_can_open_core_workspace_and_reports_include_empty_week(seeded_demo):
    from expansion.system_router import legacy_workspace_allowed
    from expansion.site_analytics import summarize
    from models.user import User
    target, result = seeded_demo
    engine = create_database_engine("sqlite:///" + target.as_posix())
    try:
        with Session(engine) as db:
            actors = {row.username: row for row in db.scalars(select(User))}
            for role in ("admin", "manager", "staff"):
                assert legacy_workspace_allowed(db, actors[f"{role}_demo"])
            assert not legacy_workspace_allowed(db, actors["customer_demo"])
            last_day = date.fromisoformat(result["history_end"])
            stats = summarize(db, actors["manager_demo"], result["single_site_id"], "week", last_day)
            assert stats["total_arrivals"] > 0
            assert stats["total_arrivals"] == stats["total_departures"]
            assert stats["revenue"]["total_revenue"] > 0
            assert stats["peak_hours"] == ["17:00"]
            assert stats["current_availability"]["total"] == 36
            assert stats["current_availability"]["occupied"] == 2
            empty = summarize(db, actors["manager_demo"], result["single_site_id"], "week",
                              date.fromisoformat(result["empty_period"]["anchor_date"]))
            assert empty["total_arrivals"] == empty["total_departures"] == 0
            assert empty["revenue"]["total_revenue"] == 0
            assert empty["peak_hours"] == []
    finally:
        engine.dispose()


def test_rerun_refuses_and_preserves_database_marker_and_credentials(seeded_demo):
    target, result = seeded_demo
    paths = [target, Path(str(target) + ".demo.json"), Path(result["credentials_file"])]
    original = {path: hashlib.sha256(path.read_bytes()).digest() for path in paths}
    with pytest.raises(FileExistsError):
        create_single_lot_demo(target)
    assert {path: hashlib.sha256(path.read_bytes()).digest() for path in paths} == original


def test_seed_failure_removes_only_its_new_artifacts(tmp_path, monkeypatch):
    target = tmp_path / "failed.db"
    unrelated = tmp_path / "user.db"
    unrelated.write_bytes(b"existing user database")
    def fail(*args):
        raise RuntimeError("injected seed failure")
    monkeypatch.setattr("expansion.single_lot_seed._seed_rows", fail)
    with pytest.raises(RuntimeError, match="injected seed failure"):
        create_single_lot_demo(target)
    assert sorted(path.name for path in tmp_path.iterdir()) == ["user.db"]
    assert unrelated.read_bytes() == b"existing user database"


def test_existing_private_file_alone_is_never_replaced(tmp_path):
    target = tmp_path / "academic.db"
    private = Path(str(target) + ".demo-credentials.json")
    private.write_text("existing credentials", encoding="utf-8")
    with pytest.raises(FileExistsError):
        create_single_lot_demo(target)
    assert private.read_text(encoding="utf-8") == "existing credentials"
    assert not target.exists()
