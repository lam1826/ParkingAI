"""Fleet operations keep stay fees while aggregate finance follows both roles."""

from datetime import timedelta

import pytest
from sqlalchemy import event, select

from expansion.site_models import SiteMembership
from models.role import Role
from test_expansion_fleet_report import env, add_session  # noqa: F401


@pytest.mark.parametrize("account_role,site_role,can_read_fees", (
    ("staff", "staff", False),
    ("staff", "manager", False),
    ("manager", "staff", False),
    ("manager", "manager", True),
    ("admin", "staff", True),
))
def test_fleet_aggregate_requires_management_account_and_site_role(env, account_role, site_role, can_read_fees):
    add_session(env, check_in=env.now - timedelta(minutes=20), fee=15000)
    latest = add_session(env, check_in=env.now - timedelta(minutes=10), fee=25000)
    role = env.db.scalar(select(Role).where(Role.name == account_role))
    if role is None:
        role = Role(name=account_role)
        env.db.add(role)
        env.db.flush()
    env.staff.role = role
    member = env.db.scalar(select(SiteMembership).where(
        SiteMembership.user_id == env.staff.id, SiteMembership.site_id == env.a.id))
    member.role = site_role
    env.db.commit()
    statements = []

    def record(_conn, _cursor, sql, _parameters, _context, _many):
        if "count(parking_sessions.id)" in sql.lower():
            statements.append(sql.lower())

    engine = env.db.get_bind()
    event.listen(engine, "before_cursor_execute", record)
    try:
        response = env.client.get(f"/api/v2/organizations/{env.org.id}/fleet", params={"limit": 1})
    finally:
        event.remove(engine, "before_cursor_execute", record)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["total_sessions"] == body["completed_sessions"] == 2
    assert body["active_sessions"] == 0
    assert len(body["sessions"]) == 1
    assert body["sessions"][0]["id"] == latest.id
    assert body["sessions"][0]["parking_fee"] == 25000
    assert statements, "The test must inspect the actual aggregate SQL."
    if can_read_fees:
        assert body["parking_fees"] == 40000
        assert any("parking_sessions.parking_fee" in sql for sql in statements)
    else:
        assert body["parking_fees"] is None
        assert "dành cho quản lý" in body["fee_note"]
        assert all("parking_fee" not in sql for sql in statements)


def test_empty_fleet_does_not_represent_hidden_staff_total_as_zero(env):
    response = env.client.get(f"/api/v2/organizations/{env.org.id}/fleet")
    assert response.status_code == 200
    assert response.json()["total_sessions"] == 0
    assert response.json()["parking_fees"] is None
    env.actor["user"] = env.account
    customer = env.client.get(f"/api/v2/organizations/{env.org.id}/fleet")
    assert customer.status_code == 200
    assert customer.json()["parking_fees"] == 0


def test_authorized_customer_keeps_fleet_aggregate_but_other_customer_cannot_read_it(env):
    add_session(env, check_in=env.now - timedelta(minutes=20), fee=35000)
    env.actor["user"] = env.account
    path = f"/api/v2/organizations/{env.org.id}/fleet"
    response = env.client.get(path)
    assert response.status_code == 200
    assert response.json()["parking_fees"] == 35000
    env.actor["user"] = env.stranger
    assert env.client.get(path).status_code == 403
