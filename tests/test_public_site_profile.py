"""Public lot page: anonymous read of published data only; manager-of-site edits."""
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import select

from database import get_db
from expansion.portal_models import SubscriptionPlan
from expansion.public_profile import router
from expansion.site_models import ParkingSite, SiteMembership
from models.role import Role
from models.user import User
from services.auth_service import get_current_user

SECRET_KEYS = {"password_hash", "license_plate", "phone_number", "revenue", "demo_token", "api_key", "secret_key",
    "public_profile_updated_by_id", "customer_id", "user_id"}


@pytest.fixture
def env(db_session, vehicle_type, parking_slot, price_config):
    roles = {}
    for name in ("manager", "staff", "customer"):
        role = db_session.scalar(select(Role).where(Role.name == name))
        if role is None:
            role = Role(name=name)
            db_session.add(role)
            db_session.flush()
        roles[name] = role
    users = {}
    for name, role in (("manager_a", "manager"), ("manager_b", "manager"), ("staff_a", "staff"), ("customer", "customer")):
        user = User(username=name, full_name=name, password_hash="unused", role_id=roles[role].id, is_active=True)
        db_session.add(user)
        db_session.flush()
        users[name] = user
    a, b, closed = ParkingSite(name="Bãi A", address="1 Đường A"), ParkingSite(name="Bãi B"), ParkingSite(name="Bãi đóng", is_active=False)
    db_session.add_all([a, b, closed])
    db_session.flush()
    parking_slot.zone.site_id = a.id
    db_session.add_all([SiteMembership(site_id=a.id, user_id=users["manager_a"].id, role="manager"),
                        SiteMembership(site_id=b.id, user_id=users["manager_b"].id, role="manager"),
                        SiteMembership(site_id=a.id, user_id=users["staff_a"].id, role="staff"),
                        SubscriptionPlan(name="Gói tháng A", site_id=a.id, vehicle_type_id=vehicle_type.id, duration_days=30, price=300000),
                        SubscriptionPlan(name="Gói ẩn", site_id=a.id, vehicle_type_id=vehicle_type.id, duration_days=30, price=1, is_active=False)])
    db_session.commit()
    actor = {"user": None}
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_db] = lambda: db_session
    app.dependency_overrides[get_current_user] = lambda: actor["user"]
    return SimpleNamespace(client=TestClient(app), actor=actor, users=users, a=a, b=b, closed=closed, db=db_session,
                           vehicle_type=vehicle_type, price=price_config)


def _walk(value, found):
    if isinstance(value, dict):
        for key, item in value.items():
            found.add(key)
            _walk(item, found)
    elif isinstance(value, list):
        for item in value:
            _walk(item, found)


def test_anonymous_page_shows_only_published_fields_and_reports_missing_ones(env):
    page = env.client.get(f"/api/v2/public/sites/{env.a.id}")
    assert page.status_code == 200, page.text
    data = page.json()
    assert data["name"] == "Bãi A" and data["address"] == "1 Đường A"
    # Nothing was published yet: no invented hours, coordinates or contact.
    assert data["description"] is None and data["opening_hours"] is None and data["location"] is None
    assert data["contact"] == {"phone": None, "email": None} and data["profile_updated_at"] is None
    assert [plan["name"] for plan in data["plans"]] == ["Gói tháng A"]
    assert data["vehicle_types"][0]["id"] == env.vehicle_type.id and data["vehicle_types"][0]["slot_count"] == 1
    assert data["walk_in_rates"][0]["price"] == env.price.price and data["capacity"] == {"zones": 1, "slots": 1}
    keys = set()
    _walk(data, keys)
    assert not keys & SECRET_KEYS, keys & SECRET_KEYS
    assert env.client.get(f"/api/v2/public/sites/{env.closed.id}").status_code == 404
    assert env.client.get("/api/v2/public/sites/999999").status_code == 404
    directory = env.client.get("/api/v2/public/sites").json()["items"]
    assert [row["name"] for row in directory] == ["Bãi A", "Bãi B"] and "plans" not in directory[0]


def test_only_a_manager_of_that_site_can_publish_and_input_is_validated(env):
    url = f"/api/v2/sites/{env.a.id}/public-profile"
    body = {"address": "12 Nguyễn Huệ", "description": "Bãi đồ án", "opening_hours": "06:00–22:00 hằng ngày",
            "contact_phone": "0901 234 567", "contact_email": "lienhe@example.com", "latitude": 10.7769, "longitude": 106.7009}
    for name, code in (("customer", 403), ("staff_a", 403), ("manager_b", 403)):
        env.actor["user"] = env.users[name]
        assert env.client.put(url, json=body).status_code == code, name
    env.actor["user"] = env.users["manager_a"]
    assert env.client.put(url, json={**body, "longitude": None}).status_code == 422
    assert env.client.put(url, json={**body, "contact_email": "not-an-email"}).status_code == 422
    assert env.client.put(url, json={**body, "latitude": 91}).status_code == 422
    assert env.client.put(url, json={**body, "extra": 1}).status_code == 422
    saved = env.client.put(url, json=body)
    assert saved.status_code == 200, saved.text
    assert saved.json()["can_edit"] is True and saved.json()["location"] == {"latitude": 10.7769, "longitude": 106.7009}
    env.db.expire_all()
    site = env.db.get(ParkingSite, env.a.id)
    assert site.public_profile_updated_by_id == env.users["manager_a"].id and site.public_profile_updated_at is not None
    public = env.client.get(f"/api/v2/public/sites/{env.a.id}").json()
    assert public["opening_hours"] == "06:00–22:00 hằng ngày" and public["contact"]["phone"] == "0901 234 567"
    assert public["profile_updated_at"] is not None and "updated_by_id" not in public
    # Staff of the site may read the editor view but the server marks it read-only.
    env.actor["user"] = env.users["staff_a"]
    view = env.client.get(url)
    assert view.status_code == 200 and view.json()["can_edit"] is False
    env.actor["user"] = env.users["manager_b"]
    assert env.client.get(url).status_code == 403
    # Clearing fields publishes "chưa cập nhật" again instead of keeping stale data.
    env.actor["user"] = env.users["manager_a"]
    cleared = env.client.put(url, json={"address": "", "description": "", "opening_hours": ""}).json()
    assert cleared["description"] is None and cleared["location"] is None and cleared["address"] is None
