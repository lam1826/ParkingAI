"""Legacy zone writes must not create data outside the site's operational scope."""
import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from database import create_database_engine, get_db
from db_rollout import check_database_readiness, initialize_database, migrate_copy
from expansion.site_models import ParkingSite
from main import app
from models import Role, User, Zone
from services.auth_service import get_current_user


@pytest.fixture
def admin_actor(db_session, test_user):
    role = Role(name="admin")
    db_session.add(role)
    db_session.flush()
    test_user.role = role
    db_session.commit()
    app.dependency_overrides[get_current_user] = lambda: test_user
    return test_user


@pytest.mark.parametrize("site_count", [0, 1, 2])
def test_legacy_create_zone_resolves_single_site_or_requires_scoped_api(client, db_session, admin_actor, site_count):
    sites = [ParkingSite(name=f"Site {number}") for number in range(site_count)]
    db_session.add_all(sites)
    db_session.commit()

    response = client.post("/api/v1/zones", json={"name": "Legacy zone", "capacity": 2})

    if site_count > 1:
        assert response.status_code == 409, response.text
        assert db_session.scalar(select(Zone).where(Zone.name == "Legacy zone")) is None
    else:
        assert response.status_code == 201, response.text
        zone = db_session.get(Zone, response.json()["id"])
        assert zone.site_id == (sites[0].id if sites else None)
        if sites:
            assert [row["id"] for row in client.get(f"/api/v2/sites/{sites[0].id}/zones").json()] == [zone.id]


def test_closed_site_still_makes_legacy_creation_ambiguous(client, db_session, admin_actor):
    db_session.add_all([ParkingSite(name="Open"), ParkingSite(name="Closed history", is_active=False)])
    db_session.commit()
    assert client.post("/api/v1/zones", json={"name": "Unassigned", "capacity": 1}).status_code == 409


@pytest.mark.parametrize("deep", [False, True])
def test_sqlite_readiness_rejects_existing_multisite_orphan_without_repair(tmp_path, deep):
    source = tmp_path / "orphan.db"
    initialize_database(source)
    engine = create_database_engine("sqlite:///" + source.as_posix())
    try:
        with Session(engine) as db:
            db.add_all([ParkingSite(name="Second site"), Zone(name="Orphan", capacity=1)])
            db.commit()
        before = source.read_bytes()
        with pytest.raises(RuntimeError, match="site_id"):
            check_database_readiness(engine, deep=deep)
        assert source.read_bytes() == before
    finally:
        engine.dispose()


def test_allowed_zone_write_remains_visible_and_can_rollout_after_adding_second_site(tmp_path):
    from fastapi.testclient import TestClient

    source, target = tmp_path / "source.db", tmp_path / "copy.db"
    initialize_database(source)
    engine = create_database_engine("sqlite:///" + source.as_posix())
    try:
        with Session(engine) as db:
            role = Role(name="admin")
            db.add(role)
            db.flush()
            actor = User(username="review_admin", role_id=role.id, full_name="Review", password_hash="unused", is_active=True)
            db.add(actor)
            db.commit()
            app.dependency_overrides[get_db] = lambda: db
            app.dependency_overrides[get_current_user] = lambda: actor
            with TestClient(app) as client:
                response = client.post("/api/v1/zones", json={"name": "Created before expansion", "capacity": 2})
                assert response.status_code == 201
                site = db.scalar(select(ParkingSite))
                zone = db.get(Zone, response.json()["id"])
                assert zone.site_id == site.id
                db.add(ParkingSite(name="Second site"))
                db.commit()
                assert [row["id"] for row in client.get(f"/api/v2/sites/{site.id}/zones").json()] == [zone.id]
            check_database_readiness(engine)
    finally:
        app.dependency_overrides.clear()
        engine.dispose()
    before = source.read_bytes()
    migrate_copy(source, target)
    assert source.read_bytes() == before
    migrated = create_database_engine("sqlite:///" + target.as_posix())
    try:
        check_database_readiness(migrated)
    finally:
        migrated.dispose()


def test_postgres_business_gate_uses_the_same_portable_orphan_check(tmp_path):
    # Runs the shared SQL invariant, not a PostgreSQL integration substitute.
    from postgres_readiness import _validate_business_invariants

    source = tmp_path / "orphan.db"
    initialize_database(source)
    engine = create_database_engine("sqlite:///" + source.as_posix())
    try:
        with Session(engine) as db:
            db.add_all([ParkingSite(name="Second site"), Zone(name="Orphan", capacity=1)])
            db.commit()
        with engine.connect() as connection, pytest.raises(RuntimeError, match="site_id"):
            _validate_business_invariants(connection)
    finally:
        engine.dispose()
