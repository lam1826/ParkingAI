"""#68: request schemas must reject values the production columns cannot store (422, nothing stored).

zones.capacity is a 32-bit INTEGER on PostgreSQL and customers.email is VARCHAR(100). SQLite stores
both happily, so without request bounds production returns HTTP 500 (and SQLite commits a row the
response schema then cannot serialize).
"""
import pytest
from sqlalchemy import text

from test_zone_slot_integrity import make_headers
from models.customer import Customer
from models.zone import Zone

INT4_MAX = 2_147_483_647
LONG_EMAIL = ("a" * 60) + "@" + ("b" * 50) + ".example.com"  # 123 characters, syntactically valid


@pytest.mark.parametrize("capacity", [INT4_MAX + 1, 3_000_000_000])
def test_zone_capacity_above_int4_is_rejected_on_create_and_update(client, db_session, manager_user, capacity):
    headers = make_headers(manager_user)
    created = client.post("/api/v1/zones", headers=headers, json={"name": "Khu lớn", "capacity": capacity, "is_active": True})
    assert created.status_code == 422, created.text
    assert db_session.query(Zone).filter(Zone.name == "Khu lớn").count() == 0

    small = client.post("/api/v1/zones", headers=headers, json={"name": "Khu nhỏ", "capacity": 5, "is_active": True})
    assert small.status_code == 201, small.text
    updated = client.put(f"/api/v1/zones/{small.json()['id']}", headers=headers, json={"capacity": capacity})
    assert updated.status_code == 422, updated.text
    db_session.expire_all()
    assert db_session.execute(text("SELECT capacity FROM zones WHERE id = :id"), {"id": small.json()["id"]}).scalar() == 5


def test_zone_capacity_at_int4_boundary_is_still_accepted(client, manager_user):
    created = client.post("/api/v1/zones", headers=make_headers(manager_user),
        json={"name": "Khu biên", "capacity": INT4_MAX, "is_active": True})
    assert created.status_code == 201, created.text


def test_site_scoped_zone_routes_share_the_capacity_bound():
    # POST /api/v2/sites/{id}/zones uses SiteZoneCreate(ZoneCreate); PUT .../zones/{id} uses ZoneUpdate.
    from pydantic import ValidationError
    from expansion.site_schemas import SiteZoneCreate
    from schemas.zone import ZoneUpdate

    for model, body in ((SiteZoneCreate, {"name": "Khu bãi", "capacity": INT4_MAX + 1}),
                        (ZoneUpdate, {"capacity": INT4_MAX + 1})):
        with pytest.raises(ValidationError):
            model(**body)
    assert SiteZoneCreate(name="Khu bãi", capacity=INT4_MAX).capacity == INT4_MAX


def test_customer_email_longer_than_column_is_rejected_on_create_and_update(client, db_session, manager_user):
    headers = make_headers(manager_user)
    created = client.post("/api/v1/customers", headers=headers,
        json={"full_name": "Khách dài", "phone_number": "0911222333", "email": LONG_EMAIL})
    assert created.status_code == 422, created.text
    assert db_session.query(Customer).filter(Customer.phone_number == "0911222333").count() == 0

    normal = client.post("/api/v1/customers", headers=headers,
        json={"full_name": "Khách thường", "phone_number": "0911000111", "email": "x@example.com"})
    assert normal.status_code == 201, normal.text
    updated = client.put(f"/api/v1/customers/{normal.json()['id']}", headers=headers, json={"email": LONG_EMAIL})
    assert updated.status_code == 422, updated.text
    listing = client.get("/api/v1/customers", headers=headers)
    assert listing.status_code == 200, listing.text
    assert [row["email"] for row in listing.json() if row["id"] == normal.json()["id"]] == ["x@example.com"]
