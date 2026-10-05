"""#71 and #77: the global zone catalog must expose what the site-scoped pages need.

#71: with several parking sites the legacy POST /api/v1/zones always answers 409 (it cannot choose
a site), but the /zones page still offered "Thêm khu vực". The page needs the same rule before it
shows the form: GET /api/v1/zones/creation-scope.

#77: in single-site mode the "Bãi đỗ" page must show only the configured site's zones and slots,
which needs the zone's site in the v1 zone response (it had no site_id).
"""
from sqlalchemy import select

from expansion.site_models import ParkingSite
from main import app
from models import Role, Zone
from services.auth_service import get_current_user


def _as_admin(db_session, user):
    role = Role(name="admin")
    db_session.add(role)
    db_session.flush()
    user.role = role
    db_session.commit()
    app.dependency_overrides[get_current_user] = lambda: user


def test_creation_scope_matches_the_multi_site_409(client, db_session, test_user):
    _as_admin(db_session, test_user)
    sites = [ParkingSite(name=f"Bãi {n}") for n in range(3)]  # production topology: 3 sites
    db_session.add_all(sites)
    db_session.commit()

    scope = client.get("/api/v1/zones/creation-scope")
    assert scope.status_code == 200, scope.text
    assert scope.json()["legacy_create_allowed"] is False

    created = client.post("/api/v1/zones", json={"name": "Khu mới", "capacity": 5})
    assert created.status_code == 409, created.text
    assert scope.json()["detail"] == created.json()["detail"]
    assert db_session.scalar(select(Zone)) is None


def test_creation_scope_allows_the_single_site_and_zero_site_setups(client, db_session, test_user):
    _as_admin(db_session, test_user)
    empty = client.get("/api/v1/zones/creation-scope")
    assert empty.status_code == 200, empty.text
    assert empty.json() == {"legacy_create_allowed": True, "detail": None}

    site = ParkingSite(name="Bãi duy nhất")
    db_session.add(site)
    db_session.commit()
    single = client.get("/api/v1/zones/creation-scope").json()
    assert single == {"legacy_create_allowed": True, "detail": None}
    created = client.post("/api/v1/zones", json={"name": "Khu một bãi", "capacity": 5})
    assert created.status_code == 201, created.text
    assert created.json()["site_id"] == site.id


def test_zone_list_and_detail_report_each_zone_site(client, db_session, test_user):
    _as_admin(db_session, test_user)
    first, second = ParkingSite(name="Bãi 1"), ParkingSite(name="Bãi 2")
    db_session.add_all([first, second])
    db_session.flush()
    db_session.add_all([Zone(name="Khu bãi 1", capacity=3, site_id=first.id),
                        Zone(name="Khu bãi 2", capacity=3, site_id=second.id)])
    db_session.commit()

    listing = client.get("/api/v1/zones")
    assert listing.status_code == 200, listing.text
    by_name = {row["name"]: row["site_id"] for row in listing.json()}
    assert by_name == {"Khu bãi 1": first.id, "Khu bãi 2": second.id}
    zone_id = next(row["id"] for row in listing.json() if row["name"] == "Khu bãi 2")
    assert client.get(f"/api/v1/zones/{zone_id}").json()["site_id"] == second.id

    # site_id is read-only on the legacy write payload (extra fields are rejected).
    moved = client.put(f"/api/v1/zones/{zone_id}", json={"site_id": first.id})
    assert moved.status_code == 422, moved.text
