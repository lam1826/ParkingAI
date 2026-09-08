import hashlib
import json
import sqlite3

import pytest

from expansion.demo_seed import create_demo


def test_new_demo_is_ready_has_synthetic_history_and_refuses_overwrite(tmp_path):
    target = tmp_path / "student.db"
    result = create_demo(target, "ParkingDemo@2026")
    marker = target.with_name(target.name + ".demo.json")
    assert result["parkingai_demo"] is True and result["synthetic_history"] is True
    assert json.loads(marker.read_text(encoding="utf-8"))["database"] == str(target.resolve())
    original = hashlib.sha256(target.read_bytes()).hexdigest()
    original_marker = marker.read_bytes()
    with pytest.raises(FileExistsError):
        create_demo(target, "AnotherDemo@2026")
    assert hashlib.sha256(target.read_bytes()).hexdigest() == original
    assert marker.read_bytes() == original_marker
    with sqlite3.connect(target) as db:
        assert db.execute("SELECT count(*) FROM parking_sites").fetchone()[0] == 2
        assert db.execute("SELECT count(*) FROM parking_sessions WHERE status='completed' AND image_in_url='demo://synthetic-history'").fetchone()[0] == result["synthetic_closed_sessions"]
        assert db.execute("SELECT count(*) FROM parking_sessions WHERE status='active'").fetchone()[0] == 1
        assert db.execute("SELECT COALESCE(sum(parking_fee),0) FROM parking_sessions").fetchone()[0] == 0
        assert db.execute("SELECT count(*) FROM payments").fetchone()[0] == 0
        assert db.execute("SELECT count(*) FROM portal_vehicle_ownerships").fetchone()[0] == 2
    from database import create_database_engine
    from expansion.insights_router import forecast_for_site
    from models.user import User
    from sqlalchemy import select
    from sqlalchemy.orm import Session
    engine = create_database_engine("sqlite:///" + target.as_posix())
    try:
        with Session(engine) as db:
            user = db.scalar(select(User).where(User.username == "admin_demo"))
            forecast = forecast_for_site(db, user, result["sites"][0]["id"])
            assert forecast["status"] == "ready"
            assert len(forecast["predictions"]) == 24
            assert forecast["backtest"]["samples"] > 0
    finally:
        engine.dispose()


def test_demo_failure_before_publication_leaves_target_absent(tmp_path, monkeypatch):
    target = tmp_path / "failed.db"
    def fail(*args):
        raise RuntimeError("injected seed error")
    monkeypatch.setattr("expansion.demo_seed._seed_rows", fail)
    with pytest.raises(RuntimeError, match="injected"):
        create_demo(target, "ParkingDemo@2026")
    assert not target.exists() and not target.with_name(target.name + ".demo.json").exists()
    assert not list(tmp_path.glob(".parkingai-demo-*"))


def test_demo_publication_race_never_overwrites_arriving_file(tmp_path, monkeypatch):
    import expansion.demo_seed as module
    target = tmp_path / "raced.db"
    link = module.os.link
    def competing_file(source, destination):
        if destination == target:
            target.write_bytes(b"unrelated database that appeared concurrently")
        return link(source, destination)
    monkeypatch.setattr(module.os, "link", competing_file)
    with pytest.raises(FileExistsError):
        create_demo(target, "ParkingDemo@2026")
    assert target.read_bytes() == b"unrelated database that appeared concurrently"
    assert not target.with_name(target.name + ".demo.json").exists()
