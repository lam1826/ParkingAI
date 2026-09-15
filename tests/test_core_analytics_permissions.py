"""Financial scope is enforced before querying, prompting or replaying AI."""
from types import SimpleNamespace
from uuid import uuid4

import pytest
from sqlalchemy import event, select

from test_expansion_sites import env  # noqa: F401
from expansion.analytics_models import SiteAiAnalysis
from expansion.site_models import SiteMembership
from models.role import Role


def endpoint(env):
    return f"/api/v2/sites/{env.a.id}"


def demote(env, membership_only=False):
    if membership_only:
        member = env.db.scalar(select(SiteMembership).where(
            SiteMembership.user_id == env.staff.id, SiteMembership.site_id == env.a.id))
        member.role = "staff"
    else:
        role = env.db.scalar(select(Role).where(Role.name == "staff"))
        if role is None:
            role = Role(name="staff")
            env.db.add(role)
        env.staff.role = role
    env.db.commit()


@pytest.mark.parametrize("membership_only", [False, True])
def test_operations_summary_never_reads_payment_ledger(env, membership_only):
    demote(env, membership_only)
    statements = []
    def capture(conn, cursor, statement, parameters, context, executemany):
        statements.append(statement.lower())
    engine = env.db.get_bind()
    event.listen(engine, "before_cursor_execute", capture)
    try:
        response = env.client.get(endpoint(env) + "/reports/summary")
    finally:
        event.remove(engine, "before_cursor_execute", capture)
    assert response.status_code == 200, response.text
    assert response.json()["revenue"] is None
    assert response.json()["data_scope"] == "operations"
    assert not any("from payments" in sql for sql in statements)


def test_staff_ai_has_no_financial_input_and_replays_own_operations_result(env, mock_ai_provider_client):
    demote(env)
    mock_ai_provider_client.return_value.models.generate_content.return_value.text = "Chưa có dữ liệu lưu lượng."
    body = {"kind": "question", "question": "Doanh thu của bãi là bao nhiêu?", "request_id": str(uuid4())}
    response = env.client.post(endpoint(env) + "/ai/analyses", json=body)
    assert response.status_code == 201, response.text
    row = env.db.scalar(select(SiteAiAnalysis))
    assert row.context["data_scope"] == "operations"
    assert row.context["revenue"] is None
    prompt = mock_ai_provider_client.return_value.models.generate_content.call_args.kwargs["contents"]
    assert '"revenue": null' in prompt
    assert '"parking_revenue"' not in prompt
    assert "không có quyền xem tài chính" in prompt
    assert env.client.post(endpoint(env) + "/ai/analyses", json=body).json()["id"] == row.id
    assert len(env.client.get(endpoint(env) + "/ai/analyses").json()) == 1


@pytest.mark.parametrize("membership_only", [False, True])
def test_demotion_blocks_history_detail_and_idempotent_replay(env, mock_ai_provider_client, membership_only):
    mock_ai_provider_client.return_value.models.generate_content.return_value.text = "Báo cáo tài chính quản lý."
    body = {"kind": "report", "request_id": str(uuid4())}
    url = endpoint(env) + "/ai/analyses"
    response = env.client.post(url, json=body)
    assert response.status_code == 201, response.text
    demote(env, membership_only)
    assert env.client.get(url).json() == []
    assert env.client.get(url + "/" + response.json()["id"]).status_code == 404
    assert env.client.post(url, json=body).status_code == 403
    assert mock_ai_provider_client.return_value.models.generate_content.call_count == 1


def test_legacy_analysis_without_scope_cannot_leak_through_staff_history(env):
    row = SiteAiAnalysis(id=str(uuid4()), site_id=env.a.id, generated_by_id=env.staff.id,
        request_id=str(uuid4()), input_hash="a" * 64, kind="report", model="old-test-model",
        context={"period": "day", "start_date": "2026-09-15", "end_date": "2026-09-15",
                 "revenue": {"total_revenue": 123456}}, content="Old financial analysis")
    env.db.add(row)
    env.db.commit()
    demote(env)
    assert env.client.get(endpoint(env) + "/ai/analyses").json() == []
    assert env.client.get(endpoint(env) + "/ai/analyses/" + row.id).status_code == 404


@pytest.mark.parametrize("membership_only", [False, True])
def test_demotion_during_provider_call_does_not_return_or_store_financial_result(env, mock_ai_provider_client, membership_only):
    def generate(**kwargs):
        demote(env, membership_only)
        return SimpleNamespace(text="Restricted financial output")
    mock_ai_provider_client.return_value.models.generate_content.side_effect = generate
    response = env.client.post(endpoint(env) + "/ai/analyses", json={"kind": "report", "request_id": str(uuid4())})
    assert response.status_code == 403, response.text
    assert "Restricted financial output" not in response.text
    assert env.db.scalars(select(SiteAiAnalysis)).all() == []


def test_export_uses_same_period_and_financial_scope_as_summary(env):
    import csv
    from io import StringIO
    url = endpoint(env) + "/reports/export"
    params = {"period": "week", "anchor_date": str(env.now.date())}
    management = env.client.get(url, params=params)
    assert management.status_code == 200, management.text
    assert management.content.startswith(b"\xef\xbb\xbf")
    assert management.headers["cache-control"] == "no-store"
    assert ".csv" in management.headers["content-disposition"]
    rows = list(csv.reader(StringIO(management.content.decode("utf-8-sig"))))
    assert len([r for r in rows if r[0] == "Theo ngày"]) == 7
    assert len([r for r in rows if r[0] == "Theo giờ"]) == 24
    assert any(r[0] == "Tài chính" for r in rows)
    demote(env)
    operations = env.client.get(url, params=params)
    assert operations.status_code == 200
    rows = list(csv.reader(StringIO(operations.content.decode("utf-8-sig"))))
    assert not any(r[0] == "Tài chính" for r in rows)
    assert env.client.get(f"/api/v2/sites/{env.b.id}/reports/export", params=params).status_code == 403
    env.actor["user"] = env.account
    assert env.client.get(url).status_code == 403


def test_export_keeps_site_names_as_text_and_rejects_invalid_period(env):
    import csv
    from io import StringIO
    env.a.name = "  =1+1"
    env.db.commit()
    response = env.client.get(endpoint(env) + "/reports/export")
    rows = list(csv.reader(StringIO(response.content.decode("utf-8-sig"))))
    assert rows[1][5] == "'  =1+1"
    assert env.client.get(endpoint(env) + "/reports/export", params={"period": "year"}).status_code == 422
