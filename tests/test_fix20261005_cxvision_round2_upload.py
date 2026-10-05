"""Authentication and bounded network reads must never own the inference slot."""
import asyncio
import hashlib
import threading
from uuid import uuid4

import httpx
import pytest
from fastapi import FastAPI

from database import get_db
from expansion import vision_router
from services.auth_service import AuthService
from test_expansion_vision_api import picture
from test_vision_passage import passage  # noqa: F401


def setup_app(p):
    app = FastAPI()
    app.include_router(vision_router.router)
    app.dependency_overrides[get_db] = lambda: p["db"]
    actor = p["actor"]
    bearer = AuthService().create_access_token(actor.id, actor.username, actor.role.name,
                                              password_hash=actor.password_hash)
    token = "R" * 43
    p["camera"].edge_token_hash = hashlib.sha256(token.encode()).hexdigest()
    camera_id = p["camera"].id
    p["db"].commit()
    return app, camera_id, {"Authorization": f"Bearer {bearer}"}, {"X-Camera-Token": token}


def upload_request(camera_id, path, headers):
    request = httpx.Request("POST", f"http://test{path}", headers=headers,
        data={"camera_id": str(camera_id), "event_id": str(uuid4())},
        files={"file": ("frame.jpg", picture(), "image/jpeg")})
    return request, request.read()


def scope_for(request):
    return {"type": "http", "method": "POST", "path": request.url.path,
        "raw_path": request.url.raw_path, "headers": [(key.lower(), value) for key, value in request.headers.raw],
        "scheme": "http", "query_string": b"", "server": ("test", 80),
        "client": ("test", 1), "http_version": "1.1", "root_path": ""}


@pytest.mark.parametrize("path", ["/api/v2/vision/live-frames", "/api/v2/vision/observations"])
def test_invalid_bearer_flood_does_not_block_valid_upload(passage, path, monkeypatch):
    app, camera_id, staff, _edge = setup_app(passage)
    gate = threading.BoundedSemaphore(1)
    acquisitions = []

    class Gate:
        def acquire(self, blocking=True):
            acquired = gate.acquire(blocking=blocking)
            acquisitions.append(acquired)
            return acquired

        def release(self):
            gate.release()

    monkeypatch.setattr(vision_router, "_upload_gate", Gate())

    async def run():
        unauthorized = asyncio.Event()
        release_responses = asyncio.Event()
        codes, body_reads = [], []

        async def receive():
            body_reads.append(True)
            raise AssertionError("unauthenticated body read")

        async def send(message):
            if message["type"] == "http.response.start":
                codes.append(message["status"])
                if message["status"] == 401:
                    unauthorized.set()
                    await release_responses.wait()

        async def attack():
            request = httpx.Request("POST", f"http://test{path}",
                                    headers={"Authorization": "Bearer bogus.bearer.token"})
            await app(scope_for(request), receive, send)

        tasks = [asyncio.create_task(attack()) for _ in range(12)]
        try:
            await asyncio.wait_for(unauthorized.wait(), 3)
            # Even a slot released before an error response can starve cameras
            # under a sustained flood: authentication must never touch it.
            assert acquisitions == []
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
                req, body = upload_request(camera_id, path, staff)
                response = await client.post(path, headers=req.headers, content=body)
            assert response.status_code == 201, response.text
        finally:
            release_responses.set()
            await asyncio.gather(*tasks)
        assert codes == [401] * 12
        assert not body_reads

    asyncio.run(run())


@pytest.mark.parametrize("path", ["/api/v2/vision/live-frames", "/api/v2/vision/observations", "/api/v2/vision/edge-events"])
def test_slow_authenticated_body_does_not_block_another_upload(passage, path):
    app, camera_id, staff, edge = setup_app(passage)
    headers = edge if path.endswith("edge-events") else staff

    async def run():
        request, body = upload_request(camera_id, path, headers)
        started, release = asyncio.Event(), asyncio.Event()
        messages = []

        async def receive():
            if not started.is_set():
                started.set()
                return {"type": "http.request", "body": body[:40], "more_body": True}
            await release.wait()
            return {"type": "http.request", "body": body[40:], "more_body": False}

        async def send(message):
            messages.append(message)

        first = asyncio.create_task(app(scope_for(request), receive, send))
        try:
            await asyncio.wait_for(started.wait(), 3)
            req, complete_body = upload_request(camera_id, path, headers)
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
                second = await client.post(path, headers=req.headers, content=complete_body)
            assert second.status_code == 201, second.text
        finally:
            release.set()
            await asyncio.wait_for(first, 5)
        assert next(m["status"] for m in messages if m["type"] == "http.response.start") == 201

    asyncio.run(run())


def test_camera_token_lookup_runs_off_event_loop(passage, monkeypatch):
    app, _camera_id, _staff, _edge = setup_app(passage)
    scalar = passage["db"].scalar
    lookup_threads = []

    def record_lookup(*args, **kwargs):
        lookup_threads.append(threading.get_ident())
        return scalar(*args, **kwargs)

    monkeypatch.setattr(passage["db"], "scalar", record_lookup)

    async def run():
        loop_thread = threading.get_ident()
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post("/api/v2/vision/edge-events", headers={"X-Camera-Token": "Z" * 43})
        assert response.status_code == 401
        assert lookup_threads and all(thread != loop_thread for thread in lookup_threads)

    asyncio.run(run())
