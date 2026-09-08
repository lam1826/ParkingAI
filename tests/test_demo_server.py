import importlib.util
from pathlib import Path

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
