"""The approved single-lot role matrix is enforced at the HTTP boundary."""

from datetime import date

import pytest

from expansion.site_models import ParkingSite, SiteMembership
from models.customer import Customer
from models.monthly_pass import MonthlyPass
from models.payment import Payment
from models.role import Role
from models.user import User
from services.auth_service import AuthService


@pytest.fixture
def core_access(db_session, vehicle_type, zone, parking_slot, vehicle, customer, price_config):
    site = ParkingSite(name="Single lot permissions")
    db_session.add(site)
    db_session.flush()
    zone.site_id = site.id
    actors = {}
    for role_name in ("staff", "manager", "admin"):
        role = Role(name=role_name)
        db_session.add(role)
        db_session.flush()
        user = User(username=f"core_{role_name}", full_name=f"Core {role_name}",
                    role_id=role.id, password_hash="unused", is_active=True)
        db_session.add(user)
        db_session.flush()
        if role_name != "admin":
            db_session.add(SiteMembership(site_id=site.id, user_id=user.id, role=role_name))
        # A forged elevated role claim must not bypass the database role.
        token = AuthService().create_access_token(user.id, user.username, "admin")
        actors[role_name] = {"Authorization": f"Bearer {token}"}
    period = MonthlyPass(customer_id=customer.id, vehicle_id=vehicle.id,
                         pass_code="CORE-EXISTING", price=100000,
                         start_date=date(2035, 1, 1), end_date=date(2035, 1, 30),
                         is_active=True)
    db_session.add(period)
    db_session.commit()
    return {"headers": actors, "site": site, "vehicle-types": vehicle_type,
            "zones": zone, "parking-slots": parking_slot, "vehicles": vehicle,
            "customers": customer, "price-configs": price_config, "monthly-passes": period}


CATALOG_PATHS = ("vehicle-types", "price-configs", "zones", "parking-slots", "monthly-passes")


def _payload(resource, context):
    return {
        "vehicle-types": {"name": "New core type", "description": "Permission test"},
        "price-configs": {"vehicle_type_id": context["vehicle-types"].id, "price": 30000,
                          "ticket_type": "HOURLY", "effective_date": "2035-01-01", "is_active": False},
        "zones": {"name": "New core zone", "capacity": 3, "is_active": True},
        "parking-slots": {"slot_name": "CORE-NEW", "zone_id": context["zones"].id,
                          "vehicle_type_id": context["vehicle-types"].id, "is_active": True},
        "monthly-passes": {"customer_id": context["customers"].id, "vehicle_id": context["vehicles"].id,
                           "pass_code": "CORE-NEW", "start_date": "2035-02-01",
                           "end_date": "2035-02-28", "price": 150000},
    }[resource]


@pytest.mark.parametrize("resource", CATALOG_PATHS + ("customers", "vehicles"))
def test_staff_can_read_core_records(client, core_access, resource):
    headers = core_access["headers"]["staff"]
    path = f"/api/v1/{resource}"
    listed = client.get(path, headers=headers)
    detail = client.get(f"{path}/{core_access[resource].id}", headers=headers)
    assert listed.status_code == detail.status_code == 200
    assert detail.json() in listed.json()


@pytest.mark.parametrize("resource", CATALOG_PATHS)
@pytest.mark.parametrize("method", ("post", "put", "delete"))
def test_staff_cannot_mutate_core_configuration(client, db_session, core_access, resource, method):
    headers = core_access["headers"]["staff"]
    path = f"/api/v1/{resource}"
    before = client.get(path, headers=headers).json()
    url = path if method == "post" else f"{path}/{core_access[resource].id}"
    kwargs = {} if method == "delete" else {"json": _payload(resource, core_access)}

    response = client.request(method, url, headers=headers, **kwargs)

    assert response.status_code == 403, response.text
    assert client.get(path, headers=headers).json() == before
    assert db_session.query(Payment).count() == 0


def test_staff_cannot_renew_monthly_pass_or_delete_customer_vehicle(client, db_session, core_access):
    headers = core_access["headers"]["staff"]
    period = core_access["monthly-passes"]
    renewal = {"start_date": "2035-02-01", "end_date": "2035-02-28", "price": 150000,
               "request_id": "core-forbidden-renewal"}
    response = client.post(f"/api/v1/monthly-passes/{period.id}/renew", headers=headers, json=renewal)
    assert response.status_code == 403
    for resource in ("customers", "vehicles"):
        url = f"/api/v1/{resource}/{core_access[resource].id}"
        assert client.delete(url, headers=headers).status_code == 403
        assert client.get(url, headers=headers).status_code == 200
    assert db_session.query(MonthlyPass).count() == 1
    assert db_session.query(Payment).count() == 0


@pytest.mark.parametrize("role_name", ("manager", "admin"))
def test_manager_and_admin_can_manage_catalog_and_paid_monthly_periods(client, db_session, core_access, role_name):
    headers = core_access["headers"][role_name]
    updates = {"vehicle-types": {"description": "Updated"}, "price-configs": {"price": 35000},
               "zones": {"capacity": 4}, "parking-slots": {"is_active": False}}
    for resource in CATALOG_PATHS[:-1]:
        path = f"/api/v1/{resource}"
        created = client.post(path, headers=headers, json=_payload(resource, core_access))
        assert created.status_code == 201, created.text
        url = f"{path}/{created.json()['id']}"
        updated = client.put(url, headers=headers, json=updates[resource])
        assert updated.status_code == 200, updated.text
        assert all(updated.json()[key] == value for key, value in updates[resource].items())
        assert client.delete(url, headers=headers).status_code == 204
        assert client.get(url, headers=headers).status_code == 404

    created = client.post("/api/v1/monthly-passes", headers=headers,
                          json=_payload("monthly-passes", core_access))
    assert created.status_code == 201, created.text
    url = f"/api/v1/monthly-passes/{created.json()['id']}"
    renewal = {"start_date": "2035-03-01", "end_date": "2035-03-30", "price": 175000,
               "request_id": f"core-allowed-renewal-{role_name}"}
    renewed = client.post(url + "/renew", headers=headers, json=renewal)
    assert renewed.status_code == 201, renewed.text
    assert client.post(url + "/renew", headers=headers, json=renewal).json()["id"] == renewed.json()["id"]
    assert client.put(url, headers=headers, json={"is_active": False}).status_code == 200
    # Manager permission must not bypass paid-history protections.
    assert client.delete(url, headers=headers).status_code == 409
    assert db_session.query(Payment).count() == 2
    unpaid_url = f"/api/v1/monthly-passes/{core_access['monthly-passes'].id}"
    assert client.delete(unpaid_url, headers=headers).status_code == 204


def test_staff_can_register_and_update_operational_customers_and_vehicles(client, core_access):
    headers = core_access["headers"]["staff"]
    customer = client.post("/api/v1/customers", headers=headers,
                           json={"full_name": "Operational customer", "phone_number": "0911111111"})
    assert customer.status_code == 201, customer.text
    customer_url = f"/api/v1/customers/{customer.json()['id']}"
    assert client.put(customer_url, headers=headers, json={"full_name": "Updated customer"}).status_code == 200
    vehicle = client.post("/api/v1/vehicles", headers=headers,
                          json={"license_plate": "30A-123.45", "vehicle_type_id": core_access["vehicle-types"].id,
                                "customer_id": customer.json()["id"]})
    assert vehicle.status_code == 201, vehicle.text
    vehicle_url = f"/api/v1/vehicles/{vehicle.json()['id']}"
    assert client.put(vehicle_url, headers=headers, json={"license_plate": "30A-123.46"}).status_code == 200
    manager = core_access["headers"]["manager"]
    assert client.delete(vehicle_url, headers=manager).status_code == 204
    assert client.delete(customer_url, headers=manager).status_code == 204


def test_manager_write_still_requires_single_site_boundary(client, db_session, core_access):
    db_session.add(ParkingSite(name="Closed historical lot", is_active=False))
    db_session.commit()
    response = client.post("/api/v1/vehicle-types", headers=core_access["headers"]["manager"],
                           json={"name": "Forbidden global type"})
    assert response.status_code == 403


@pytest.mark.parametrize("path", ("/dashboard", "/dashboard/revenue-chart", "/parking/statistics", "/reports/revenue",
                                  "/reports/export/xlsx", "/ai/reports"))
def test_staff_cannot_read_legacy_lot_finances(client, core_access, path):
    assert client.get(path, headers=core_access["headers"]["staff"]).status_code == 403


@pytest.mark.parametrize("path", ("/dashboard/ai-insight", "/dashboard/recent-sessions", "/reports/traffic"))
def test_staff_retains_legacy_operational_reads(client, core_access, path):
    response = client.get(path, headers=core_access["headers"]["staff"])
    assert response.status_code == 200, response.text


def test_staff_cannot_send_legacy_financial_ai_prompt(client, core_access, mock_ai_provider_client):
    response = client.post("/ai/question", headers=core_access["headers"]["staff"],
                           json={"question": "Tổng doanh thu của bãi là bao nhiêu?"})
    assert response.status_code == 403
    mock_ai_provider_client.assert_not_called()
