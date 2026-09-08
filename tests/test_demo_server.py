import importlib.util
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("parkingai_demo_server", ROOT / "scripts/demo_server.py")
demo = importlib.util.module_from_spec(spec)
spec.loader.exec_module(demo)


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
