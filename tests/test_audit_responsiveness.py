from concurrent.futures import ThreadPoolExecutor
from threading import Event
from time import monotonic, sleep

from fastapi import FastAPI
from fastapi.testclient import TestClient

from middleware.audit import AuditLogMiddleware
from services.auth_service import AuthService


def test_slow_audit_storage_does_not_block_the_event_loop(monkeypatch):
    audit_started = Event()

    class SlowAuditSession:
        def add(self, _row):
            pass

        def commit(self):
            audit_started.set()
            sleep(0.5)

        def rollback(self):
            pass

        def close(self):
            pass

    monkeypatch.setattr("middleware.audit.SessionLocal", SlowAuditSession)
    app = FastAPI()

    @app.post("/write")
    def write():
        return {"ok": True}

    @app.get("/pulse")
    async def pulse():
        return {"ok": True}

    app.add_middleware(AuditLogMiddleware)
    token = AuthService().create_access_token(
        user_id=1,
        username="audit-test",
        role="admin",
    )
    headers = {"Authorization": f"Bearer {token}"}

    with TestClient(app) as client, ThreadPoolExecutor(max_workers=1) as pool:
        mutation = pool.submit(client.post, "/write", headers=headers)
        assert audit_started.wait(timeout=2)
        started = monotonic()
        pulse = client.get("/pulse")
        elapsed = monotonic() - started
        assert pulse.status_code == 200
        assert elapsed < 0.2
        assert mutation.result(timeout=2).status_code == 200
