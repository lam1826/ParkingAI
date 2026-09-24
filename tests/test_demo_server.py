import importlib.util
import json
import os
from pathlib import Path
import sqlite3

import pytest
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("parkingai_demo_server", ROOT / "scripts/demo_server.py")
demo = importlib.util.module_from_spec(spec)
spec.loader.exec_module(demo)


def test_powershell_scripts_with_vietnamese_text_carry_a_utf8_bom():
    # Windows PowerShell 5.1 reads a BOM-less .ps1 as ANSI, so Vietnamese string
    # literals break the parser and `./scripts/start_demo.ps1` fails before starting.
    for script in sorted((ROOT / "scripts").glob("*.ps1")):
        raw = script.read_bytes()
        if any(byte > 0x7F for byte in raw):
            assert raw.startswith(b"\xef\xbb\xbf"), f"{script.name} needs a UTF-8 BOM for Windows PowerShell 5.1"
            raw[3:].decode("utf-8")


def test_demo_server_refuses_an_unmarked_database(tmp_path):
    source = tmp_path / "real.db"
    source.write_bytes(b"do not change")
    with pytest.raises(ValueError, match="demo_seed"):
        demo.configure_demo(source)
    assert source.read_bytes() == b"do not change"


def test_demo_ui_uses_same_origin_and_static_route_cannot_select_another_file(tmp_path, monkeypatch):
    dist = tmp_path / "frontend" / "dist"
    (dist / "assets").mkdir(parents=True)
    (dist / "index.html").write_text("<html>Demo application</html>")
    (dist / "brand-mark.svg").write_text("<svg>logo</svg>")
    (dist / "private.txt").write_text("not public")
    monkeypatch.setattr(demo, "ROOT", tmp_path)
    monkeypatch.setattr("db_rollout.check_database_readiness", lambda *_args, **_kwargs: None)
    client = TestClient(demo.build_demo_app())
    assert "location.origin" in client.get("/config.js").text
    assert client.get("/portal").text == "<html>Demo application</html>"
    assert client.get("/site-settings").text == "<html>Demo application</html>"
    assert client.get("/brand-mark.svg?filename=private.txt").text == "<svg>logo</svg>"


def test_demo_dashboard_routes_browser_navigation_to_spa_and_json_to_api(tmp_path, monkeypatch):
    dist = tmp_path / "frontend" / "dist"
    (dist / "assets").mkdir(parents=True)
    (dist / "index.html").write_text("<html>Demo dashboard</html>")
    monkeypatch.setattr(demo, "ROOT", tmp_path)
    monkeypatch.setattr("db_rollout.check_database_readiness", lambda *_args, **_kwargs: None)

    client = TestClient(demo.build_demo_app())
    browser = client.get("/dashboard", headers={"Accept": "text/html"})
    api = client.get("/dashboard", headers={"Accept": "application/json"})

    assert browser.status_code == 200
    assert browser.text == "<html>Demo dashboard</html>"
    assert api.status_code == 401
    assert api.headers["content-type"].startswith("application/json")


@pytest.mark.parametrize("enable_ai", [False, True])
def test_single_lot_server_uses_verified_site_id_and_marks_synthetic_reports(tmp_path, monkeypatch, enable_ai):
    database = tmp_path / "academic.db"
    with sqlite3.connect(database) as connection:
        connection.execute("CREATE TABLE parking_sites (id INTEGER PRIMARY KEY)")
        connection.execute("INSERT INTO parking_sites VALUES (7)")
    Path(str(database) + ".demo.json").write_text(json.dumps({"parkingai_demo": True,
        "synthetic_history": True, "profile": "single-lot-academic-v1", "single_site_id": 7}), encoding="utf-8")
    # configure_demo intentionally mutates process startup configuration; this
    # test restores the environment so later API tests keep their own fixtures.
    with monkeypatch.context() as local:
        local.setattr(demo, "DEMO_SITE_ID", None)
        local.setattr(os, "environ", os.environ.copy())
        local.setattr(demo.sys, "path", list(demo.sys.path))
        demo.configure_demo(database, vision=False, single_lot=True, enable_ai=enable_ai)
        assert os.environ["PARKINGAI_SHOWCASE_MODE"] == "true"
        assert os.environ["AI_ENABLED"] == ("true" if enable_ai else "false")
        assert os.environ["DATABASE_URL"] == "sqlite:///" + database.as_posix()
        dist = tmp_path / "frontend" / "dist"
        (dist / "assets").mkdir(parents=True)
        (dist / "index.html").write_text("<html>Single lot</html>")
        local.setattr(demo, "ROOT", tmp_path)
        local.setattr("db_rollout.check_database_readiness", lambda *_args, **_kwargs: None)
        response = TestClient(demo.build_demo_app()).get("/config.js")
        assert "SINGLE_SITE_ID: 7" in response.text
        assert "DEMO: true" in response.text
        assert response.headers["cache-control"] == "no-store"


def test_demo_ai_opt_in_requires_the_verified_single_lot_profile(tmp_path):
    with pytest.raises(ValueError, match="single-lot"):
        demo.configure_demo(tmp_path / "other.db", enable_ai=True)


@pytest.mark.parametrize("site_ids,marker_id", [([1, 2], 1), ([7], 2), ([1], True)])
def test_single_lot_server_rejects_mismatched_marker_without_mutation(tmp_path, site_ids, marker_id):
    database = tmp_path / "invalid.db"
    with sqlite3.connect(database) as connection:
        connection.execute("CREATE TABLE parking_sites (id INTEGER PRIMARY KEY)")
        connection.executemany("INSERT INTO parking_sites VALUES (?)", [(item,) for item in site_ids])
    Path(str(database) + ".demo.json").write_text(json.dumps({"parkingai_demo": True,
        "synthetic_history": True, "profile": "single-lot-academic-v1", "single_site_id": marker_id}), encoding="utf-8")
    original = database.read_bytes()
    with pytest.raises(ValueError):
        demo.configure_demo(database, single_lot=True)
    assert database.read_bytes() == original
