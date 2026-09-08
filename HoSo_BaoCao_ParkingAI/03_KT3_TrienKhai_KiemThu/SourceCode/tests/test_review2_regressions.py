"""Round-two review regressions: ownership change vs. bookings, observation id oracle, midnight DEMO payment."""
from datetime import timedelta
from uuid import uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy import select

from test_expansion_sites import env, reserve  # noqa: F401  (shared booking fixture)
from test_expansion_vision_api import picture, vision  # noqa: F401
from test_portal_api import onboard, portal  # noqa: F401

from core.clock import BUSINESS_TZ, business_now
from expansion import reservations as service
from expansion.portal_models import PortalAccountLink, PortalOrder, PortalVehicleOwnership
from expansion.site_schemas import ReservationCreate
from expansion.vision_models import VisionObservation
from models.parking_slot import ParkingSlot


def _transfer_vehicle(env):
    link = env.db.scalar(select(PortalAccountLink).where(PortalAccountLink.user_id == env.stranger.id))
    env.vehicle.customer_id = link.customer_id
    env.db.add(PortalVehicleOwnership(customer_id=link.customer_id, vehicle_id=env.vehicle.id, approved_by_id=env.staff.id))
    env.db.commit()
    return link.customer_id


def test_previous_owner_booking_no_longer_blocks_verified_new_owner(env):
    old = reserve(env, start=env.now + timedelta(hours=1), end=env.now + timedelta(hours=3))
    spare = ParkingSlot(zone_id=env.slot.zone_id, vehicle_type_id=env.vehicle.vehicle_type_id, slot_name="A-02")
    env.db.add(spare)
    env.db.commit()
    new_owner_id = _transfer_vehicle(env)
    body = ReservationCreate(site_id=env.a.id, vehicle_id=env.vehicle.id,
                             start_at=(env.now + timedelta(hours=1)).replace(tzinfo=BUSINESS_TZ),
                             end_at=(env.now + timedelta(hours=3)).replace(tzinfo=BUSINESS_TZ),
                             request_id="new-owner-request-0001")
    row = service.reserve(env.db, env.stranger, body, customer=True)
    env.db.commit()
    assert row.status == "confirmed" and row.customer_id == new_owner_id
    # The old booking still holds its own slot, so the new owner landed on the spare one.
    assert row.slot_id == spare.id and old.slot_id == env.slot.id
    # The verified owner cannot double-book their own window.
    with pytest.raises(HTTPException) as exc:
        service.reserve(env.db, env.stranger, body.model_copy(update={"request_id": "new-owner-request-0002"}), customer=True)
    assert exc.value.status_code == 409
    env.db.rollback()
    # The previous owner's row cannot be used to admit the car any more.
    env.clock["now"] += timedelta(hours=1)
    with pytest.raises(HTTPException) as exc:
        service.arrive(env.db, env.staff, old)
    assert exc.value.status_code == 409
    env.db.rollback()


def test_foreign_site_observation_id_is_indistinguishable_from_missing(vision):
    client, db, camera, foreign, user = vision
    now = business_now()
    row = VisionObservation(camera_id=foreign.id, site_id=foreign.site_id, event_id=str(uuid4()),
                            image_hash="0" * 64, image_bytes=picture(), image_width=180, image_height=80,
                            observed_at=now, captured_at=now, expires_at=now + timedelta(hours=1),
                            ocr_status="unavailable", engine="disabled")
    db.add(row)
    db.commit()
    foreign_codes = {
        "image": client.get(f"/api/v2/vision/observations/{row.id}/image").status_code,
        "review": client.post(f"/api/v2/vision/observations/{row.id}/review", json={"decision": "reject"}).status_code,
        "delete": client.delete(f"/api/v2/vision/observations/{row.id}").status_code,
    }
    missing = client.get(f"/api/v2/vision/observations/{uuid4()}/image").status_code
    assert set(foreign_codes.values()) == {missing} == {404}
    assert db.get(VisionObservation, row.id).review_status == "pending"


def test_demo_result_inside_validity_window_survives_midnight(portal):
    client, current, users, site, kind, db = portal
    body = onboard(portal)
    order = client.post("/api/v2/me/orders", json=body).json()
    row = db.get(PortalOrder, order["id"])
    # The order was created before midnight (start_date = yesterday) and is still within its TTL now.
    row.start_date -= timedelta(days=1)
    row.end_date -= timedelta(days=1)
    db.commit()
    result = client.post(f"/api/v2/me/orders/{order['id']}/simulate", json={"token": order["demo_token"], "outcome": "success"})
    assert result.status_code == 200, result.text
    assert result.json()["status"] == "fulfilled" and result.json()["monthly_pass_id"]


def test_demo_result_after_expiry_still_goes_to_review_and_manager_can_reject(portal):
    client, current, users, site, kind, db = portal
    body = onboard(portal)
    order = client.post("/api/v2/me/orders", json=body).json()
    row = db.get(PortalOrder, order["id"])
    row.start_date -= timedelta(days=1)
    row.end_date -= timedelta(days=1)
    row.expires_at -= timedelta(days=1, minutes=30)
    db.commit()
    result = client.post(f"/api/v2/me/orders/{order['id']}/simulate", json={"token": order["demo_token"], "outcome": "success"})
    assert result.status_code == 200 and result.json()["status"] == "review" and result.json()["review_reason"] == "late_payment"
    current["user"] = users[0]
    approve = client.post(f"/api/v2/portal/admin/orders/{order['id']}/review", json={"approve": True, "note": "kiểm tra"})
    assert approve.status_code == 409
    reject = client.post(f"/api/v2/portal/admin/orders/{order['id']}/review", json={"approve": False, "note": "quá hạn"})
    assert reject.status_code == 200 and reject.json()["status"] == "cancelled"


def test_review_for_on_time_result_can_be_approved_even_days_later(portal):
    """A result received inside the window but flagged for another reason stays approvable after midnight."""
    client, current, users, site, kind, db = portal
    body = onboard(portal)
    order = client.post("/api/v2/me/orders", json=body).json()
    row = db.get(PortalOrder, order["id"])
    original_site = row.site_id
    row_site = db.get(type(site), original_site)
    row_site.is_active = False
    db.commit()
    result = client.post(f"/api/v2/me/orders/{order['id']}/simulate", json={"token": order["demo_token"], "outcome": "success"})
    assert result.json()["status"] == "review" and result.json()["review_reason"] == "site_inactive"
    row_site.is_active = True
    row.start_date -= timedelta(days=1)
    row.end_date -= timedelta(days=1)
    db.commit()
    current["user"] = users[0]
    approve = client.post(f"/api/v2/portal/admin/orders/{order['id']}/review", json={"approve": True, "note": "bãi mở lại"})
    assert approve.status_code == 200, approve.text
    assert approve.json()["status"] == "fulfilled"
