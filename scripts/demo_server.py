"""Serve the academic demo UI and API together; never select the normal DB."""
from __future__ import annotations

import argparse
from contextlib import asynccontextmanager
import json
import logging
import os
from pathlib import Path
import secrets
import sys
import threading

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"


def configure_demo(database: Path, *, vision=True):
    database = database.resolve()
    marker = Path(str(database) + ".demo.json")
    if not database.is_file() or not marker.is_file():
        raise ValueError("Chỉ chạy DB demo đã tạo bằng expansion.demo_seed (cần tệp .demo.json bên cạnh).")
    metadata = json.loads(marker.read_text(encoding="utf-8"))
    if metadata.get("parkingai_demo") is not True or metadata.get("synthetic_history") is not True:
        raise ValueError("Tệp này không được đánh dấu là dữ liệu đồ án.")
    # Force these before importing any backend module or loading backend/.env.
    os.environ["DATABASE_URL"] = "sqlite:///" + database.as_posix()
    os.environ["DEMO_PAYMENTS_ENABLED"] = "true"
    os.environ["AI_ENABLED"] = "false"
    os.environ["SECRET_KEY"] = secrets.token_hex(32)
    os.environ["MANAGER_REGISTRATION_CODE"] = secrets.token_urlsafe(32)
    os.environ["ADMIN_REGISTRATION_CODE"] = secrets.token_urlsafe(32)
    os.environ["RELEASE_ID"] = "academic-demo"
    model = BACKEND / "artifacts" / "vision" / "license-plate-yolov8n.onnx"
    os.environ["PARKING_VISION_ENGINE"] = "yolo_rapidocr" if vision and model.is_file() else "disabled"
    os.environ["PARKING_VISION_MODEL"] = str(model) if vision and model.is_file() else ""
    sys.path.insert(0, str(BACKEND))
    return database


def build_demo_app():
    from fastapi import FastAPI
    from fastapi.responses import FileResponse, Response
    from fastapi.staticfiles import StaticFiles
    from main import app as api_app
    from database import engine, SessionLocal
    from db_rollout import check_database_readiness
    from expansion.portal_worker import run_portal_maintenance
    from expansion.vision_service import purge_expired

    dist = ROOT / "frontend" / "dist"
    if not (dist / "index.html").is_file():
        raise ValueError("Chưa build frontend. Chạy npm run build trong frontend trước.")
    check_database_readiness(engine)
    stop = threading.Event()

    def maintain():
        while not stop.is_set():
            try:
                with SessionLocal() as db:
                    run_portal_maintenance(db)
                    purge_expired(db)
                    db.commit()
            except Exception:
                logging.getLogger("parkingai.demo").exception("Demo maintenance failed; retry on next cycle")
            stop.wait(30)

    @asynccontextmanager
    async def lifespan(app):
        worker = threading.Thread(target=maintain, daemon=True, name="parkingai-demo-maintenance")
        worker.start()
        try:
            yield
        finally:
            stop.set()
            worker.join(timeout=5)
            engine.dispose()

    app = FastAPI(title="ParkingAI Academic Demo", docs_url=None, redoc_url=None, openapi_url=None, lifespan=lifespan)

    @app.get("/config.js", include_in_schema=False)
    def config():
        return Response("globalThis.__PARKINGAI_CONFIG__ = {API_URL: globalThis.location.origin, DEMO: true};", media_type="application/javascript", headers={"Cache-Control": "no-store"})

    def frontend():
        return FileResponse(dist / "index.html", headers={"Cache-Control": "no-store"})

    for route in ("/", "/login", "/register", "/portal", "/portal-admin", "/reservations", "/sites", "/vision", "/insights",
                  "/account", "/profile", "/settings", "/dashboard", "/sessions", "/parking-sessions", "/customers", "/vehicles",
                  "/monthly-passes", "/users", "/zones", "/parking-slots", "/vehicle-types", "/price-configs", "/reports",
                  "/finance", "/audit-logs", "/ai", "/roles", "/home"):
        app.add_api_route(route, frontend, methods=["GET"], include_in_schema=False)
    app.mount("/assets", StaticFiles(directory=dist / "assets"), name="assets")
    def asset_handler(filename):
        # A closure has no FastAPI query parameters that can override the path.
        def public_asset():
            return FileResponse(dist / filename)
        return public_asset

    for name in ("brand-mark.svg", "icons.svg"):
        app.add_api_route("/" + name, asset_handler(name), methods=["GET"], include_in_schema=False)
    app.mount("/", api_app)
    return app


def main():
    parser = argparse.ArgumentParser(description="Run the isolated academic demo (QR simulation, same-origin phone UI).")
    parser.add_argument("--database", type=Path, required=True)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--no-vision", action="store_true")
    args = parser.parse_args()
    configure_demo(args.database, vision=not args.no_vision)
    import uvicorn
    uvicorn.run(build_demo_app(), host=args.host, port=args.port)


if __name__ == "__main__":
    main()
