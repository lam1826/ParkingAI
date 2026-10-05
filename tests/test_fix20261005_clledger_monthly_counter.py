"""Review 05/10/2026 #8, #19, #44: counter monthly sales and site revenue bounds.

#8  A renewal period that already ended before today buys no coverage (coverage
    is fixed at admission), so the server refuses it before collecting money.
#19 A monthly pass binds the vehicle's owner: another customer is refused; a
    walk-in vehicle without an owner stays allowed.
#44 Site revenue with a single date bound is open-ended on the other side,
    exactly like the payment list it sums, instead of HTTP 422.
"""
import datetime
from uuid import uuid4

from sqlalchemy import func, select

from core.clock import business_now
from expansion.site_models import ParkingSite, SiteMembership
from models.customer import Customer
from models.monthly_pass import MonthlyPass
from models.payment import Payment
from models.vehicle import Vehicle
from services.auth_service import AuthService
from services.payment_service import PaymentService


def _headers(user):
    token = AuthService().create_access_token(user_id=user.id, username=user.username,
        role=user.role.name, password_hash=user.password_hash)
    return {"Authorization": "Bearer " + token}


def _site(db, user):
    site = ParkingSite(name="Only lot", is_active=True)
    db.add(site)
    db.flush()
    db.add(SiteMembership(site_id=site.id, user_id=user.id, role="manager"))
    db.commit()
    return site


def _create(client, user, customer, vehicle, start, end, code):
    return client.post("/api/v1/monthly-passes", headers=_headers(user), json={
        "customer_id": customer.id, "vehicle_id": vehicle.id, "pass_code": code, "price": 300000,
        "start_date": start.isoformat(), "end_date": end.isoformat(), "payment_method": "cash"})


def _receipts(db):
    return db.scalar(select(func.count()).select_from(Payment).where(Payment.source_type == "monthly_pass"))


def test_renewal_that_ended_before_today_is_refused_without_a_receipt(client, db_session, manager_user, customer, vehicle):
    today = business_now().date()
    old_end = today - datetime.timedelta(days=31)
    created = _create(client, manager_user, customer, vehicle, old_end - datetime.timedelta(days=29), old_end, "CARD-LAPSED")
    assert created.status_code == 201, created.text
    original = created.json()
    # The old dialog default: end+1 .. end+30, which lies entirely in the past.
    start = old_end + datetime.timedelta(days=1)
    stale = client.post(f"/api/v1/monthly-passes/{original['id']}/renew", headers=_headers(manager_user), json={
        "start_date": start.isoformat(), "end_date": (start + datetime.timedelta(days=29)).isoformat(),
        "price": 300000, "payment_method": "cash", "request_id": uuid4().hex})
    assert stale.status_code == 409, stale.text
    assert "trước hôm nay" in stale.json()["detail"]
    assert _receipts(db_session) == 1
    assert db_session.scalar(select(func.count()).select_from(MonthlyPass)) == 1
    # A renewal that starts today (the corrected default) still works.
    fresh = client.post(f"/api/v1/monthly-passes/{original['id']}/renew", headers=_headers(manager_user), json={
        "start_date": today.isoformat(), "end_date": (today + datetime.timedelta(days=29)).isoformat(),
        "price": 300000, "payment_method": "cash", "request_id": uuid4().hex})
    assert fresh.status_code == 201, fresh.text
    assert _receipts(db_session) == 2


def test_pass_customer_must_own_the_vehicle(client, db_session, manager_user, customer, vehicle):
    owner = Customer(full_name="Chủ xe", phone_number="0911111111")
    db_session.add(owner)
    db_session.flush()
    owned = Vehicle(license_plate="51F-999.99", vehicle_type_id=vehicle.vehicle_type_id, customer_id=owner.id)
    db_session.add(owned)
    db_session.commit()
    start = business_now().date() + datetime.timedelta(days=1)
    end = start + datetime.timedelta(days=29)
    mismatch = _create(client, manager_user, customer, owned, start, end, "CARD-MISMATCH")
    assert mismatch.status_code == 409, mismatch.text
    assert db_session.scalar(select(func.count()).select_from(MonthlyPass)) == 0 and _receipts(db_session) == 0
    assert _create(client, manager_user, owner, owned, start, end, "CARD-OWNER").status_code == 201
    # The conftest vehicle has no owner: a walk-in vehicle can still get a pass.
    walk_in = _create(client, manager_user, customer, vehicle, start, end, "CARD-WALKIN")
    assert walk_in.status_code == 201, walk_in.text


def test_revenue_with_one_date_bound_matches_the_payment_list(client, db_session, manager_user, customer, vehicle):
    site = _site(db_session, manager_user)
    today = business_now().date()
    yesterday = today - datetime.timedelta(days=1)
    root = f"/api/v2/sites/{site.id}"
    # The old route answered 422 to a single bound even with no data at all.
    for params in ({"date_to": yesterday.isoformat()}, {"date_from": (today + datetime.timedelta(days=1)).isoformat()}):
        empty = client.get(f"{root}/revenue", params=params, headers=_headers(manager_user))
        assert empty.status_code == 200 and empty.json()["total_revenue"] == 0, (params, empty.text)
    for offset, code in ((1, "REV-OLD"), (0, "REV-TODAY")):
        period = MonthlyPass(customer_id=customer.id, vehicle_id=vehicle.id, price=100000 + offset,
            start_date=today + datetime.timedelta(days=40 * (offset + 1)),
            end_date=today + datetime.timedelta(days=40 * (offset + 1) + 29), pass_code=code)
        db_session.add(period)
        db_session.flush()
        PaymentService.record_receipt(db_session, "monthly_pass", period.id, period.price, None, "cash",
            created_at=business_now() - datetime.timedelta(days=offset), counter_site_id=site.id)
    db_session.commit()
    for params, expected in (({"date_to": yesterday.isoformat()}, 100001),
                             ({"date_from": today.isoformat()}, 100000),
                             ({"date_from": (today + datetime.timedelta(days=1)).isoformat()}, 0)):
        revenue = client.get(f"{root}/revenue", params=params, headers=_headers(manager_user))
        assert revenue.status_code == 200, (params, revenue.text)
        listed = client.get(f"{root}/payments", params=params, headers=_headers(manager_user)).json()["items"]
        assert revenue.json()["total_revenue"] == expected == sum(row["amount"] for row in listed)
        assert revenue.json()["payment_count"] == len(listed)
    # No bound at all keeps the "today" summary.
    assert client.get(f"{root}/revenue", headers=_headers(manager_user)).json()["total_revenue"] == 100000
    reversed_range = client.get(f"{root}/revenue", params={"date_from": today.isoformat(), "date_to": yesterday.isoformat()},
        headers=_headers(manager_user))
    assert reversed_range.status_code == 422
