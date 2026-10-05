"""Final money review: manager refunds remain available after a ticket starts.

Exercise both HTTP refund routes against isolated fixture databases and the
reservation arrival API, without changing the customer refund time policy.
"""
from datetime import datetime, timedelta

import pytest

from expansion.portal_models import PortalOrder
from expansion.site_models import ParkingReservation
from expansion.site_router import router as site_router
from expansion.timed_parking_models import TimedParkingPass
from models.payment import Payment
from models.parking_session import ParkingSession
from test_fix20261005_clledger_direct_refund import (
    _manual_timed_order, _refund_body, _refunds, _routes, _site_row,
)
from test_portal_api import portal  # noqa: F401
from test_timed_parking import timed  # noqa: F401
from core.clock import BUSINESS_TZ


def _url(site, receipt_id, route):
    prefix = f"/api/v2/sites/{site.id}/payments" if route == "site" else "/api/v1/payments"
    return f"{prefix}/{receipt_id}/refund"


def _freeze(monkeypatch, at):
    instant = at.replace(tzinfo=BUSINESS_TZ)

    class FixedClock(datetime):
        @classmethod
        def now(cls, tz=None):
            return instant.astimezone(tz) if tz else instant.astimezone().replace(tzinfo=None)

    monkeypatch.setattr("core.clock.datetime", FixedClock)


@pytest.mark.parametrize("route", ["site", "legacy"])
def test_expired_ticket_can_be_refunded_without_changing_entitlement(timed, route):
    client, current, users, site, kind, db = timed[0]
    _routes(client)
    order = _manual_timed_order(timed, f"final-expired-{route}")
    ticket = db.get(TimedParkingPass, order["timed_pass_id"])
    reservation = db.get(ParkingReservation, ticket.reservation_id)
    ticket.status = reservation.status = "expired"
    db.commit()
    snapshot = (ticket.status, ticket.session_id, reservation.status, reservation.session_id)
    response = client.post(_url(site, order["receipt_id"], route), json=_refund_body(12000, f"final-expired-refund-{route}"))
    assert response.status_code == 200, response.text
    assert response.json()["kind"] == "refund" and response.json()["amount"] == 12000
    db.expire_all()
    assert (ticket.status, ticket.session_id, reservation.status, reservation.session_id) == snapshot
    assert db.get(PortalOrder, order["id"]).status == "fulfilled"
    assert _refunds(db, order["receipt_id"]) == 12000


@pytest.mark.parametrize("route", ["site", "legacy"])
@pytest.mark.parametrize("amount", [6000, 12000])
@pytest.mark.parametrize("product", ["hourly", "daily"])
def test_started_unused_ticket_refund_stops_admission_and_replays(timed, monkeypatch, route, amount, product):
    client, current, users, site, kind, db = timed[0]
    _routes(client)
    client.app.include_router(site_router)
    if product == "daily":
        current["user"] = users[0]
        plan = client.post("/api/v2/portal/admin/plans", json={"name": "One day", "site_id": site.id,
            "vehicle_type_id": kind.id, "product_kind": "daily", "duration_minutes": 1440, "price": 12000})
        assert plan.status_code == 200, plan.text
        timed[1]["plan_id"] = plan.json()["id"]
        current["user"] = users[1]
    order = _manual_timed_order(timed, f"final-started-{product}-{route}-{amount}")
    ticket = db.get(TimedParkingPass, order["timed_pass_id"])
    reservation = db.get(ParkingReservation, ticket.reservation_id)
    _freeze(monkeypatch, ticket.start_at)  # The exact start boundary is allowed.
    row = _site_row(client, site, order["receipt_id"])
    assert row["direct_refund_blocked_reason"] is None
    assert row["direct_refund_revokes_ticket"] is True
    payload = _refund_body(amount, f"final-started-refund-{route}-{amount}")
    response = client.post(_url(site, order["receipt_id"], route), json=payload)
    assert response.status_code == 200, response.text
    db.expire_all()
    assert ticket.status == "revoked" and ticket.session_id is None
    assert reservation.status == "cancelled" and reservation.session_id is None
    assert db.get(PortalOrder, order["id"]).status == ("refunded" if amount == 12000 else "fulfilled")
    assert _refunds(db, order["receipt_id"]) == amount
    row = _site_row(client, site, order["receipt_id"])
    assert row["direct_refund_blocked_reason"] is None
    assert row["direct_refund_revokes_ticket"] is False
    assert row["refundable_amount"] == 12000 - amount
    # The reserved check-in cannot admit the car on the refunded ticket.
    arrival = client.post(f"/api/v2/sites/{site.id}/reservations/{reservation.id}/arrive")
    assert arrival.status_code == 409, arrival.text
    # Replaying through the other public route also returns the same row.
    replay_route = "legacy" if route == "site" else "site"
    replay = client.post(_url(site, order["receipt_id"], replay_route), json=payload)
    assert replay.status_code == 200 and replay.json()["id"] == response.json()["id"], replay.text
    db.expire_all()
    assert _refunds(db, order["receipt_id"]) == amount
    assert ticket.status == "revoked" and reservation.status == "cancelled"


@pytest.mark.parametrize("route", ["site", "legacy"])
def test_before_start_ticket_still_points_to_customer_workflow(timed, route):
    client, current, users, site, kind, db = timed[0]
    _routes(client)
    order = _manual_timed_order(timed, f"final-before-{route}")
    response = client.post(_url(site, order["receipt_id"], route), json=_refund_body(12000, f"final-before-refund-{route}"))
    assert response.status_code == 409 and "yêu cầu hoàn tiền" in response.json()["detail"]
    row = _site_row(client, site, order["receipt_id"])
    assert row["direct_refund_blocked_reason"] == "portal_ticket"
    assert row["direct_refund_revokes_ticket"] is False
    assert "chưa tới giờ bắt đầu" in row["direct_refund_blocked_label"]
    current["user"] = users[1]
    request = client.post(f"/api/v2/me/receipts/{order['receipt_id']}/refund-requests", json={"reason": "Đổi lịch gửi xe"})
    assert request.status_code == 201, request.text
    db.expire_all()
    assert db.get(TimedParkingPass, order["timed_pass_id"]).status == "ready"
    assert _refunds(db, order["receipt_id"]) == 0


@pytest.mark.parametrize("route", ["site", "legacy"])
@pytest.mark.parametrize("request_status", ["pending", "reviewing", "approved"])
def test_open_request_blocks_direct_refund_even_after_start(timed, monkeypatch, route, request_status):
    client, current, users, site, kind, db = timed[0]
    _routes(client)
    order = _manual_timed_order(timed, f"final-request-{route}-{request_status}")
    current["user"] = users[1]
    request = client.post(f"/api/v2/me/receipts/{order['receipt_id']}/refund-requests", json={"reason": "Không dùng vé"})
    assert request.status_code == 201, request.text
    current["user"] = users[0]
    request_id = request.json()["id"]
    request_url = f"/api/v2/sites/{site.id}/refund-requests/{request_id}"
    if request_status == "reviewing":
        assert client.post(request_url + "/review", json={}).status_code == 200
    elif request_status == "approved":
        assert client.post(request_url + "/approve", json={}).status_code == 200
    ticket = db.get(TimedParkingPass, order["timed_pass_id"])
    _freeze(monkeypatch, ticket.start_at + timedelta(minutes=1))
    response = client.post(_url(site, order["receipt_id"], route), json=_refund_body(6000, f"final-open-refund-{route}-{request_status}"))
    assert response.status_code == 409 and "yêu cầu hoàn" in response.json()["detail"]
    row = _site_row(client, site, order["receipt_id"])
    assert row["direct_refund_blocked_reason"] == "request_open"
    assert row["open_refund_request_id"] == request_id
    assert _refunds(db, order["receipt_id"]) == 0


@pytest.mark.parametrize("route", ["site", "legacy"])
@pytest.mark.parametrize("status", ["consumed", "revoked"])
def test_terminal_ticket_refund_only_adds_ledger_rows(timed, monkeypatch, route, status):
    client, current, users, site, kind, db = timed[0]
    _routes(client)
    client.app.include_router(site_router)
    order = _manual_timed_order(timed, f"final-terminal-{route}-{status}")
    ticket = db.get(TimedParkingPass, order["timed_pass_id"])
    reservation = db.get(ParkingReservation, ticket.reservation_id)
    _freeze(monkeypatch, ticket.start_at + timedelta(minutes=1))
    if status == "consumed":
        arrived = client.post(f"/api/v2/sites/{site.id}/reservations/{reservation.id}/arrive")
        assert arrived.status_code == 200, arrived.text
        db.expire_all()
        assert ticket.status == "consumed"
    else:
        ticket.status, reservation.status = "revoked", "cancelled"
        db.commit()
    snapshot = (ticket.status, ticket.session_id, reservation.status, reservation.session_id)
    receipt = db.get(Payment, order["receipt_id"])
    original = (receipt.amount, receipt.kind, receipt.method, receipt.source_type, receipt.source_id, receipt.site_id, receipt.created_at)
    payload = _refund_body(12000, f"final-terminal-refund-{route}-{status}")
    response = client.post(_url(site, receipt.id, route), json=payload)
    assert response.status_code == 200, response.text
    db.expire_all()
    assert (ticket.status, ticket.session_id, reservation.status, reservation.session_id) == snapshot
    assert db.get(PortalOrder, order["id"]).status == "fulfilled"
    assert (receipt.amount, receipt.kind, receipt.method, receipt.source_type, receipt.source_id, receipt.site_id, receipt.created_at) == original
    if status == "consumed":
        session = db.get(ParkingSession, ticket.session_id)
        assert session.status == "active" and session.timed_pass_id == ticket.id
    replay = client.post(_url(site, receipt.id, route), json=payload)
    assert replay.status_code == 200 and replay.json()["id"] == response.json()["id"]
    assert _refunds(db, receipt.id) == 12000
    excess = client.post(_url(site, receipt.id, route), json=_refund_body(1, f"final-excess-{route}-{status}"))
    assert excess.status_code == 409 and _refunds(db, receipt.id) == 12000
    conflict = client.post(_url(site, receipt.id, route), json={**payload, "amount": 6000})
    assert conflict.status_code == 409 and _refunds(db, receipt.id) == 12000


@pytest.mark.parametrize("route", ["site", "legacy"])
def test_failed_refund_does_not_revoke_a_started_ticket(timed, monkeypatch, route):
    client, current, users, site, kind, db = timed[0]
    _routes(client)
    order = _manual_timed_order(timed, f"final-overflow-{route}")
    ticket = db.get(TimedParkingPass, order["timed_pass_id"])
    _freeze(monkeypatch, ticket.start_at + timedelta(minutes=1))
    response = client.post(_url(site, order["receipt_id"], route), json=_refund_body(12001, f"final-overflow-refund-{route}"))
    assert response.status_code == 409, response.text
    db.expire_all()
    assert ticket.status == "ready"
    assert db.get(ParkingReservation, ticket.reservation_id).status == "confirmed"
    assert db.get(PortalOrder, order["id"]).status == "fulfilled"
    assert _refunds(db, order["receipt_id"]) == 0
