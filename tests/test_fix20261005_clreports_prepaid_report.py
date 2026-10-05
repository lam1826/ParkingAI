"""#35: hour/day package receipts (prepaid_revenue) must have their own report/CSV line.

The site summary already counts non-demo ``portal_order`` receipts in ``prepaid_revenue`` and
in ``total_revenue``; the CSV must list that component so the finance rows reconcile:
parking + monthly + prepaid - refunds == net.
"""
import csv
import io

from fastapi import FastAPI
from fastapi.testclient import TestClient

from test_portal_api import portal  # noqa: F401 -- shared isolated portal fixture
from test_timed_parking import timed  # noqa: F401 -- hour/day plan on top of the portal fixture
from database import get_db
from services.auth_service import get_current_user
from expansion import site_analytics


def _finance_rows(text):
    return {row[1]: row[5] for row in csv.reader(io.StringIO(text)) if row and row[0] == "Tài chính"}


def test_collected_hour_day_package_has_its_own_csv_line_and_rows_reconcile(timed):
    context, body, _slot, _rate = timed
    client, current, users, site, _kind, db = context
    made = client.post("/api/v2/me/orders", json={**body, "payment_mode": "manual"})
    assert made.status_code == 200, made.text
    current["user"] = users[0]
    collected = client.post(f"/api/v2/portal/admin/orders/{made.json()['id']}/collect",
        json={"confirmed": True, "payment_method": "transfer"})
    assert collected.status_code == 200, collected.text

    app = FastAPI()
    app.include_router(site_analytics.router, prefix="/api/v2")
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_current_user] = lambda: users[0]
    with TestClient(app) as reports:
        summary = reports.get(f"/api/v2/sites/{site.id}/reports/summary")
        assert summary.status_code == 200, summary.text
        exported = reports.get(f"/api/v2/sites/{site.id}/reports/export")
        assert exported.status_code == 200, exported.text

    revenue = summary.json()["revenue"]
    assert revenue["prepaid_revenue"] == 12000
    assert revenue["total_revenue"] == 12000
    rows = _finance_rows(exported.content.decode("utf-8-sig"))
    assert rows["Thu vé giờ/ngày"] == "12000"
    assert (int(rows["Thu lượt gửi"]) + int(rows["Thu vé tháng"]) + int(rows["Thu vé giờ/ngày"])
            - int(rows["Hoàn tiền"])) == int(rows["Thu ròng"])
    labels = list(rows)
    assert labels.index("Thu vé tháng") < labels.index("Thu vé giờ/ngày") < labels.index("Hoàn tiền")
