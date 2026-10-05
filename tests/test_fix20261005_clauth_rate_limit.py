"""CL-AUTH #38: the limiter's own 429 rejections never extend the lockout.

Real failures (login) and attempts (registration) still lock the IP; the lock
ends one window after them even while someone on the same NAT keeps retrying.
The 429 rows themselves stay in the audit log.
"""

from datetime import timedelta

from models.audit_log import AuditLog
from core.config import settings


def _age_rows(db_session, seconds):
    for row in db_session.query(AuditLog).all():
        row.created_at = row.created_at - timedelta(seconds=seconds)
    db_session.commit()


def test_login_lock_ends_one_window_after_real_failures_despite_retries(client, db_session, test_user, monkeypatch):
    monkeypatch.setattr(settings, "TRUSTED_EDGE_PROXY", True)
    monkeypatch.setattr(settings, "AUTH_LOGIN_MAX_FAILURES", 10)
    monkeypatch.setattr(settings, "AUTH_LOGIN_WINDOW_SECONDS", 300)
    headers = {"Fly-Client-IP": "198.51.100.7"}
    login = lambda password: client.post("/api/auth/login", headers=headers,  # noqa: E731
                                         json={"username": test_user.username, "password": password})

    assert [login("wrong").status_code for _ in range(10)] == [401] * 10
    # Still limited: retries inside the window are refused, even with the right password.
    statuses = []
    for _ in range(11):
        _age_rows(db_session, 25)
        statuses.append(login("password123").status_code)
    assert statuses == [429] * 11  # t = 25 .. 275 s

    # One window after the real failures, the retrying user gets in.
    _age_rows(db_session, 30)  # t = 305 s; retries every 25 s never stopped
    assert login("password123").status_code == 200
    # The rejected attempts are still audited as failures (evidence is kept).
    rejected = db_session.query(AuditLog).filter(AuditLog.action == "LOGIN", AuditLog.status_code == 429).count()
    assert rejected == 11


def test_login_lock_still_counts_new_real_failures(client, db_session, test_user, monkeypatch):
    monkeypatch.setattr(settings, "TRUSTED_EDGE_PROXY", True)
    monkeypatch.setattr(settings, "AUTH_LOGIN_MAX_FAILURES", 3)
    monkeypatch.setattr(settings, "AUTH_LOGIN_WINDOW_SECONDS", 300)
    headers = {"Fly-Client-IP": "198.51.100.9"}
    for _ in range(3):
        client.post("/api/auth/login", headers=headers, json={"username": test_user.username, "password": "wrong"})
    assert client.post("/api/auth/login", headers=headers,
                       json={"username": test_user.username, "password": "password123"}).status_code == 429
    _age_rows(db_session, 301)  # the first lock has expired
    again = [client.post("/api/auth/login", headers=headers,
                         json={"username": test_user.username, "password": "wrong"}).status_code for _ in range(3)]
    assert again == [401] * 3  # real failures, counted again
    _age_rows(db_session, 150)
    assert client.post("/api/auth/login", headers=headers,
                       json={"username": test_user.username, "password": "password123"}).status_code == 429


def test_registration_lock_is_not_renewed_by_its_own_rejections(client, db_session, monkeypatch):
    monkeypatch.setattr(settings, "TRUSTED_EDGE_PROXY", True)
    monkeypatch.setattr(settings, "AUTH_REGISTER_MAX_ATTEMPTS", 5)
    monkeypatch.setattr(settings, "AUTH_REGISTER_WINDOW_SECONDS", 3600)
    headers = {"Fly-Client-IP": "198.51.100.8"}
    register = lambda i: client.post("/api/auth/register", headers=headers, json={  # noqa: E731
        "username": f"cust_{i}", "password": "password123", "full_name": "Khach", "role": "customer"}).status_code

    assert [register(i) for i in range(5)] == [201] * 5
    assert [register(100 + i) for i in range(1)] == [429]
    statuses = []
    for i in range(5):  # one attempt every 10 minutes
        _age_rows(db_session, 600)
        statuses.append(register(200 + i))
    assert statuses == [429] * 5  # t = 600 .. 3000 s, the five real registrations still count
    _age_rows(db_session, 700)  # t = 3700 s: the window after the real attempts has passed
    assert register(300) == 201
