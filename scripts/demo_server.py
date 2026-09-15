"""Serve the academic demo UI and API together; never select the normal DB."""
from __future__ import annotations

import argparse
from contextlib import asynccontextmanager
import json
import logging
import os
from pathlib import Path
import secrets
import sqlite3
import sys
import threading

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
DEMO_SITE_ID = None


def configure_demo(database: Path, *, vision=True, single_lot=False, enable_ai=False):
    global DEMO_SITE_ID
    database = database.resolve()
    if enable_ai and not single_lot:
        raise ValueError("Bật AI yêu cầu profile một bãi được kiểm chứng (--single-lot).")
    marker = Path(str(database) + ".demo.json")
    if not database.is_file() or not marker.is_file():
        raise ValueError("Chỉ chạy DB demo đã tạo bằng expansion.demo_seed (cần tệp .demo.json bên cạnh).")
    metadata = json.loads(marker.read_text(encoding="utf-8"))
    if metadata.get("parkingai_demo") is not True or metadata.get("synthetic_history") is not True:
        raise ValueError("Tệp này không được đánh dấu là dữ liệu đồ án.")
    site_id = metadata.get("single_site_id")
    if single_lot and metadata.get("profile") != "single-lot-academic-v1":
        raise ValueError("Cần DB một bãi tạo bằng expansion.single_lot_seed; DB cũ không được thay đổi.")
    if site_id is not None:
        if type(site_id) is not int or site_id < 1:
            raise ValueError("Mã bãi trong marker demo không hợp lệ.")
        with sqlite3.connect(database.as_uri() + "?mode=ro", uri=True) as connection:
            sites = connection.execute("SELECT id FROM parking_sites LIMIT 2").fetchall()
        if sites != [(site_id,)]:
            raise ValueError("DB không còn đúng một bãi như marker. Không khởi động hoặc sửa dữ liệu.")
    elif single_lot:
        raise ValueError("Marker demo thiếu mã bãi duy nhất.")
    DEMO_SITE_ID = site_id
    # Force these before importing any backend module or loading backend/.env.
    os.environ["DATABASE_URL"] = "sqlite:///" + database.as_posix()
    os.environ["DEMO_PAYMENTS_ENABLED"] = "true"
    # A synthetic academic database must never create a real bank payment link.
    os.environ["PAYOS_ENABLED"] = "false"
    os.environ["AI_ENABLED"] = "true" if enable_ai else "false"
    os.environ["PARKINGAI_SHOWCASE_MODE"] = "true"
    os.environ["SECRET_KEY"] = secrets.token_hex(32)
    os.environ["MANAGER_REGISTRATION_CODE"] = secrets.token_urlsafe(32)
    os.environ["ADMIN_REGISTRATION_CODE"] = secrets.token_urlsafe(32)
    os.environ["RELEASE_ID"] = "academic-demo"
    model = BACKEND / "artifacts" / "vision" / "license-plate-yolov8n.onnx"
    os.environ["PARKING_VISION_ENGINE"] = "yolo_rapidocr" if vision and model.is_file() else "disabled"
    os.environ["PARKING_VISION_MODEL"] = str(model) if vision and model.is_file() else ""
    sys.path.insert(0, str(BACKEND))
    return database


def build_demo_app(frontend_dist=None):
    from fastapi import FastAPI, Request
    from fastapi.responses import FileResponse, Response
    from fastapi.staticfiles import StaticFiles
    from main import app as api_app
    from database import engine, SessionLocal
    from db_rollout import check_database_readiness
    from expansion.portal_worker import run_portal_maintenance
    from expansion.vision_service import purge_expired

    dist = Path(frontend_dist).resolve() if frontend_dist is not None else ROOT / "frontend" / "dist"
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

    @app.middleware("http")
    async def dashboard_content_negotiation(request: Request, call_next):
        if request.url.path == "/dashboard" and "text/html" in request.headers.get("accept", "").lower():
            return frontend()
        return await call_next(request)

    @app.get("/config.js", include_in_schema=False)
    def config():
        site = f", SINGLE_SITE_ID: {DEMO_SITE_ID}" if DEMO_SITE_ID is not None else ""
        return Response("globalThis.__PARKINGAI_CONFIG__ = {API_URL: globalThis.location.origin, DEMO: true" + site + "};", media_type="application/javascript", headers={"Cache-Control": "no-store"})

    def frontend():
        return FileResponse(dist / "index.html", headers={"Cache-Control": "no-store"})

    for route in ("/", "/login", "/register", "/portal", "/portal-admin", "/reservations", "/sites", "/vision", "/occupancy", "/insights",
                  "/account", "/profile", "/settings", "/sessions", "/parking-sessions", "/customers", "/vehicles",
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
    parser.add_argument("--frontend-dist", type=Path, help="Use a separately built frontend for an isolated acceptance run")
    parser.add_argument("--no-vision", action="store_true")
    parser.add_argument("--single-lot", action="store_true", help="Require a verified one-lot academic seed")
    parser.add_argument("--enable-ai", action="store_true", help="Opt in to Gemini for aggregate synthetic data; requires --single-lot and a configured API key")
    args = parser.parse_args()
    configure_demo(args.database, vision=not args.no_vision, single_lot=args.single_lot, enable_ai=args.enable_ai)
    if args.enable_ai:
        from core.config import settings
        if not settings.GEMINI_API_KEY.strip():
            parser.error("--enable-ai requires GEMINI_API_KEY in the environment or backend/.env")
    import uvicorn
    uvicorn.run(build_demo_app(args.frontend_dist), host=args.host, port=args.port)


if __name__ == "__main__":
    main()
