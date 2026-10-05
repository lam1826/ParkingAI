from test_expansion_sites import env  # noqa: F401  (fixture)

from datetime import timedelta
from sqlalchemy import select

from core.clock import BUSINESS_TZ
from expansion.site_models import ParkingReservation, SiteMembership, SiteWaitlist
from expansion.portal_models import PortalAccountLink
from models.customer import Customer
from models.role import Role
from models.user import User
from models.vehicle import Vehicle


def iso(dt):
    return dt.replace(tzinfo=BUSINESS_TZ).isoformat()


def test_future_offer_blocks_walkins_and_staff_cannot_withdraw(env):
    db = env.db
    # A plain staff user (role 'staff', site membership 'staff').
    staff_role = db.scalar(select(Role).where(Role.name == "staff"))
    staff = User(username="counter-staff", role_id=staff_role.id, full_name="NV", password_hash="unused")
    db.add(staff); db.flush()
    db.add(SiteMembership(site_id=env.a.id, user_id=staff.id, role="staff"))
    # A counter customer with NO portal account (cannot use /me/... endpoints).
    walkup = Customer(full_name="Khach quay", phone_number="0907000777")
    db.add(walkup); db.flush()
    v = Vehicle(license_plate="30K12345", vehicle_type_id=env.vehicle.vehicle_type_id, customer_id=walkup.id)
    db.add(v); db.commit()
    assert db.scalar(select(PortalAccountLink).where(PortalAccountLink.customer_id == walkup.id)) is None
    env.actor["user"] = staff

    start = env.now + timedelta(days=2)
    end = start + timedelta(hours=2)
    body = dict(site_id=env.a.id, vehicle_id=v.id, start_at=iso(start), end_at=iso(end),
                request_id="waitlist-gap-request-0001")
    joined = env.client.post(f"/api/v2/sites/{env.a.id}/waitlist", json=body)
    print("join waitlist:", joined.status_code, joined.json().get("status"))
    assert joined.status_code == 201, joined.text
    wid = joined.json()["id"]

    offer = env.client.post(f"/api/v2/sites/{env.a.id}/waitlist/{wid}/offer")
    print("offer:", offer.status_code, offer.json().get("status"), offer.json().get("start_at"), offer.json().get("arrival_deadline"))
    assert offer.status_code == 200, offer.text
    rid = offer.json()["id"]

    walk = {"license_plate": "51F99999", "vehicle_type_id": env.vehicle.vehicle_type_id}
    w1 = env.client.post(f"/api/v2/sites/{env.a.id}/check-in", json=walk)
    print("walk-in now (no slot chosen):", w1.status_code, w1.json())
    w1b = env.client.post(f"/api/v2/sites/{env.a.id}/check-in", json={**walk, "parking_slot_id": env.slot.id})
    print("walk-in now (slot chosen):", w1b.status_code, w1b.json())
    assert w1.status_code >= 400 and w1b.status_code >= 400

    # 'Cập nhật quá hạn' does not release it (deadline is 2 days ahead).
    exp = env.client.post(f"/api/v2/sites/{env.a.id}/reservations/expire")
    print("expire overdue:", exp.status_code, exp.json())

    # Staff 'Rời danh sách chờ' path on the offered row.
    c = env.client.post(f"/api/v2/sites/{env.a.id}/waitlist/{wid}/cancel")
    print("staff cancel waitlist row:", c.status_code, c.json())
    assert c.status_code == 200, c.text
    assert c.json()['status'] == 'cancelled'
    assert db.get(ParkingReservation,rid).status == 'cancelled'
    w2 = env.client.post(f'/api/v2/sites/{env.a.id}/check-in', json=walk)
    assert w2.status_code == 201, w2.text
