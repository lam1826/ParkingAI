import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from models.parking_slot import ParkingSlot
from models.parking_session import ParkingSession
from models.user import User
from models.vehicle_type import VehicleType
from models.zone import Zone
from services.auth_service import AuthService
from database import run_sqlite_migrations


def make_headers(user: User) -> dict[str, str]:
    token = AuthService().create_access_token(
        user_id=user.id,
        username=user.username,
        role=user.role.name,
    )
    return {"Authorization": f"Bearer {token}"}


def test_client_cannot_create_slot_as_occupied(
    client: TestClient,
    db_session: Session,
    test_user: User,
    zone: Zone,
    vehicle_type: VehicleType,
):
    response = client.post(
        "/api/v1/parking-slots",
        headers=make_headers(test_user),
        json={
            "slot_name": "A-CLIENT-STATE",
            "zone_id": zone.id,
            "vehicle_type_id": vehicle_type.id,
            "is_occupied": True,
            "is_active": True,
        },
    )

    assert response.status_code == 422
    assert db_session.query(ParkingSlot).filter_by(slot_name="A-CLIENT-STATE").first() is None


def test_client_cannot_update_slot_occupancy(
    client: TestClient,
    db_session: Session,
    test_user: User,
    parking_slot: ParkingSlot,
):
    original_state = parking_slot.is_occupied

    response = client.put(
        f"/api/v1/parking-slots/{parking_slot.id}",
        headers=make_headers(test_user),
        json={"is_occupied": not original_state},
    )

    assert response.status_code == 422
    db_session.refresh(parking_slot)
    assert parking_slot.is_occupied is original_state


def test_check_in_does_not_allocate_slot_from_inactive_zone(
    client: TestClient,
    db_session: Session,
    test_user: User,
    zone: Zone,
    vehicle_type: VehicleType,
):
    zone.is_active = False
    slot = ParkingSlot(
        slot_name="A-INACTIVE-ZONE",
        zone_id=zone.id,
        vehicle_type_id=vehicle_type.id,
        is_occupied=False,
        is_active=True,
    )
    db_session.add(slot)
    db_session.commit()

    response = client.post(
        "/parking/check-in",
        headers=make_headers(test_user),
        json={
            "license_plate": "30A-111.22",
            "vehicle_type_id": vehicle_type.id,
        },
    )

    assert response.status_code == 404
    assert "chỗ trống" in response.json()["detail"].lower()
    db_session.refresh(slot)
    assert slot.is_occupied is False
    assert db_session.query(ParkingSession).count() == 0


def test_check_in_rejects_explicit_slot_from_inactive_zone(
    client: TestClient,
    db_session: Session,
    test_user: User,
    zone: Zone,
    vehicle_type: VehicleType,
):
    zone.is_active = False
    slot = ParkingSlot(
        slot_name="A-INACTIVE-EXPLICIT",
        zone_id=zone.id,
        vehicle_type_id=vehicle_type.id,
        is_occupied=False,
        is_active=True,
    )
    db_session.add(slot)
    db_session.commit()

    response = client.post(
        "/parking/check-in",
        headers=make_headers(test_user),
        json={
            "license_plate": "30A-222.33",
            "vehicle_type_id": vehicle_type.id,
            "parking_slot_id": slot.id,
        },
    )

    assert response.status_code == 404
    db_session.refresh(slot)
    assert slot.is_occupied is False
    assert db_session.query(ParkingSession).count() == 0


def test_available_slot_summary_excludes_inactive_zones(
    client: TestClient,
    db_session: Session,
    test_user: User,
    zone: Zone,
    vehicle_type: VehicleType,
):
    zone.is_active = False
    db_session.add(
        ParkingSlot(
            slot_name="A-HIDDEN-ZONE",
            zone_id=zone.id,
            vehicle_type_id=vehicle_type.id,
            is_occupied=False,
            is_active=True,
        )
    )
    db_session.commit()

    response = client.get("/parking/available-slots", headers=make_headers(test_user))

    assert response.status_code == 200
    assert response.json() == {
        "total_slots": 0,
        "total_occupied": 0,
        "total_available": 0,
        "zones": [],
    }


def test_parking_statistics_exclude_inactive_zones(
    client: TestClient,
    db_session: Session,
    test_user: User,
    zone: Zone,
    vehicle_type: VehicleType,
):
    zone.is_active = False
    db_session.add_all(
        [
            ParkingSlot(
                slot_name="A-INACTIVE-FREE",
                zone_id=zone.id,
                vehicle_type_id=vehicle_type.id,
                is_occupied=False,
                is_active=True,
            ),
            ParkingSlot(
                slot_name="A-INACTIVE-OCCUPIED",
                zone_id=zone.id,
                vehicle_type_id=vehicle_type.id,
                is_occupied=True,
                is_active=True,
            ),
        ]
    )
    db_session.commit()

    response = client.get("/parking/statistics", headers=make_headers(test_user))

    assert response.status_code == 200
    assert response.json()["available_slots"] == 0
    assert response.json()["occupied_slots"] == 0


def test_dashboard_occupancy_excludes_inactive_zones(
    client: TestClient,
    db_session: Session,
    test_user: User,
    zone: Zone,
    vehicle_type: VehicleType,
):
    zone.is_active = False
    db_session.add(
        ParkingSlot(
            slot_name="A-INACTIVE-DASHBOARD",
            zone_id=zone.id,
            vehicle_type_id=vehicle_type.id,
            is_occupied=True,
            is_active=True,
        )
    )
    db_session.commit()

    response = client.get("/dashboard", headers=make_headers(test_user))

    assert response.status_code == 200
    assert response.json()["occupancy_rate_percentage"] == 0.0


def test_create_slot_rejects_zone_capacity_overflow(
    client: TestClient,
    db_session: Session,
    test_user: User,
    zone: Zone,
    vehicle_type: VehicleType,
):
    zone.capacity = 1
    db_session.add(
        ParkingSlot(
            slot_name="A-CAPACITY-01",
            zone_id=zone.id,
            vehicle_type_id=vehicle_type.id,
            is_occupied=False,
            is_active=True,
        )
    )
    db_session.commit()

    response = client.post(
        "/api/v1/parking-slots",
        headers=make_headers(test_user),
        json={
            "slot_name": "A-CAPACITY-02",
            "zone_id": zone.id,
            "vehicle_type_id": vehicle_type.id,
            "is_active": True,
        },
    )

    assert response.status_code == 409
    assert "sức chứa" in response.json()["detail"].lower()
    assert db_session.query(ParkingSlot).filter_by(zone_id=zone.id).count() == 1


def test_move_slot_rejects_full_destination_zone(
    client: TestClient,
    db_session: Session,
    test_user: User,
    parking_slot: ParkingSlot,
    vehicle_type: VehicleType,
):
    destination = Zone(name="Khu đầy", capacity=1, is_active=True)
    db_session.add(destination)
    db_session.flush()
    db_session.add(
        ParkingSlot(
            slot_name="FULL-01",
            zone_id=destination.id,
            vehicle_type_id=vehicle_type.id,
            is_occupied=False,
            is_active=True,
        )
    )
    db_session.commit()
    original_zone_id = parking_slot.zone_id

    response = client.put(
        f"/api/v1/parking-slots/{parking_slot.id}",
        headers=make_headers(test_user),
        json={"zone_id": destination.id},
    )

    assert response.status_code == 409
    assert "sức chứa" in response.json()["detail"].lower()
    db_session.refresh(parking_slot)
    assert parking_slot.zone_id == original_zone_id


def test_zone_capacity_cannot_be_reduced_below_existing_slot_count(
    client: TestClient,
    db_session: Session,
    test_user: User,
    zone: Zone,
    parking_slot: ParkingSlot,
):
    response = client.put(
        f"/api/v1/zones/{zone.id}",
        headers=make_headers(test_user),
        json={"capacity": 0},
    )

    assert response.status_code == 409
    assert "sức chứa" in response.json()["detail"].lower()
    db_session.refresh(zone)
    assert zone.capacity == 50
    assert parking_slot.zone_id == zone.id


def test_zone_name_is_trimmed_and_unique_case_insensitively(
    client: TestClient,
    db_session: Session,
    test_user: User,
    zone: Zone,
):
    response = client.post(
        "/api/v1/zones",
        headers=make_headers(test_user),
        json={"name": "  kHU a  ", "capacity": 10, "is_active": True},
    )

    assert response.status_code == 409
    assert "tên khu vực" in response.json()["detail"].lower()
    assert db_session.query(Zone).count() == 1


def test_zone_update_rejects_another_zone_name(
    client: TestClient,
    db_session: Session,
    test_user: User,
    zone: Zone,
):
    other_zone = Zone(name="Khu B", capacity=10, is_active=True)
    db_session.add(other_zone)
    db_session.commit()

    response = client.put(
        f"/api/v1/zones/{other_zone.id}",
        headers=make_headers(test_user),
        json={"name": " khu a "},
    )

    assert response.status_code == 409
    db_session.refresh(other_zone)
    assert other_zone.name == "Khu B"


def test_zone_name_uniqueness_uses_unicode_casefold(
    client: TestClient,
    db_session: Session,
    test_user: User,
    zone: Zone,
):
    zone.name = "KHU ĐỖ"
    db_session.commit()

    response = client.post(
        "/api/v1/zones",
        headers=make_headers(test_user),
        json={"name": " khu đỗ ", "capacity": 10, "is_active": True},
    )

    assert response.status_code == 409
    assert db_session.query(Zone).count() == 1


def test_slot_code_is_normalized_and_unique_case_insensitively(
    client: TestClient,
    db_session: Session,
    test_user: User,
    zone: Zone,
    vehicle_type: VehicleType,
    parking_slot: ParkingSlot,
):
    response = client.post(
        "/api/v1/parking-slots",
        headers=make_headers(test_user),
        json={
            "slot_name": " a-01 ",
            "zone_id": zone.id,
            "vehicle_type_id": vehicle_type.id,
            "is_active": True,
        },
    )

    assert response.status_code == 409
    assert "mã vị trí" in response.json()["detail"].lower()
    assert db_session.query(ParkingSlot).count() == 1


def test_slot_update_rejects_another_slot_code(
    client: TestClient,
    db_session: Session,
    test_user: User,
    zone: Zone,
    vehicle_type: VehicleType,
    parking_slot: ParkingSlot,
):
    other_slot = ParkingSlot(
        slot_name="A-02",
        zone_id=zone.id,
        vehicle_type_id=vehicle_type.id,
        is_occupied=False,
        is_active=True,
    )
    db_session.add(other_slot)
    db_session.commit()

    response = client.put(
        f"/api/v1/parking-slots/{other_slot.id}",
        headers=make_headers(test_user),
        json={"slot_name": " a-01 "},
    )

    assert response.status_code == 409
    db_session.refresh(other_slot)
    assert other_slot.slot_name == "A-02"


def test_create_slot_rejects_missing_vehicle_type_before_write(
    client: TestClient,
    db_session: Session,
    test_user: User,
    zone: Zone,
):
    response = client.post(
        "/api/v1/parking-slots",
        headers=make_headers(test_user),
        json={
            "slot_name": "A-NO-TYPE",
            "zone_id": zone.id,
            "vehicle_type_id": 999999,
            "is_active": True,
        },
    )

    assert response.status_code == 404
    assert "loại xe" in response.json()["detail"].lower()
    assert db_session.query(ParkingSlot).filter_by(slot_name="A-NO-TYPE").first() is None


def test_update_slot_rejects_missing_vehicle_type_before_write(
    client: TestClient,
    db_session: Session,
    test_user: User,
    parking_slot: ParkingSlot,
):
    original_type_id = parking_slot.vehicle_type_id

    response = client.put(
        f"/api/v1/parking-slots/{parking_slot.id}",
        headers=make_headers(test_user),
        json={"vehicle_type_id": 999999},
    )

    assert response.status_code == 404
    assert "loại xe" in response.json()["detail"].lower()
    db_session.refresh(parking_slot)
    assert parking_slot.vehicle_type_id == original_type_id


def test_slot_create_normalizes_code_and_keeps_server_occupancy_default(
    client: TestClient,
    db_session: Session,
    test_user: User,
    zone: Zone,
    vehicle_type: VehicleType,
):
    response = client.post(
        "/api/v1/parking-slots",
        headers=make_headers(test_user),
        json={
            "slot_name": " b-02 ",
            "zone_id": zone.id,
            "vehicle_type_id": vehicle_type.id,
            "is_active": True,
        },
    )

    assert response.status_code == 201
    assert response.json()["slot_name"] == "B-02"
    assert response.json()["is_occupied"] is False
    stored = db_session.get(ParkingSlot, response.json()["id"])
    assert stored is not None
    assert stored.slot_name == "B-02"
    assert stored.is_occupied is False


def test_active_session_blocks_slot_deactivation(
    client: TestClient,
    db_session: Session,
    test_user: User,
    parking_slot: ParkingSlot,
    parking_session: ParkingSession,
):
    response = client.put(
        f"/api/v1/parking-slots/{parking_slot.id}",
        headers=make_headers(test_user),
        json={"is_active": False},
    )

    assert response.status_code == 409
    assert "xe đang đỗ" in response.json()["detail"].lower()
    db_session.refresh(parking_slot)
    assert parking_slot.is_active is True
    assert parking_session.status == "active"


def test_active_session_blocks_zone_deactivation(
    client: TestClient,
    db_session: Session,
    test_user: User,
    zone: Zone,
    parking_slot: ParkingSlot,
    parking_session: ParkingSession,
):
    response = client.put(
        f"/api/v1/zones/{zone.id}",
        headers=make_headers(test_user),
        json={"is_active": False},
    )

    assert response.status_code == 409
    assert "xe đang đỗ" in response.json()["detail"].lower()
    db_session.refresh(zone)
    assert zone.is_active is True
    assert parking_slot.is_occupied is True
    assert parking_session.status == "active"


def test_slot_with_session_history_cannot_be_deleted(
    client: TestClient,
    db_session: Session,
    test_user: User,
    parking_slot: ParkingSlot,
    parking_session: ParkingSession,
):
    response = client.delete(
        f"/api/v1/parking-slots/{parking_slot.id}",
        headers=make_headers(test_user),
    )

    assert response.status_code == 409
    assert "lịch sử" in response.json()["detail"].lower()
    assert db_session.get(ParkingSlot, parking_slot.id) is not None
    db_session.refresh(parking_session)
    assert parking_session.parking_slot_id == parking_slot.id


def test_zone_with_slots_cannot_be_deleted(
    client: TestClient,
    db_session: Session,
    test_user: User,
    zone: Zone,
    parking_slot: ParkingSlot,
):
    response = client.delete(
        f"/api/v1/zones/{zone.id}",
        headers=make_headers(test_user),
    )

    assert response.status_code == 409
    assert "vị trí" in response.json()["detail"].lower()
    assert db_session.get(Zone, zone.id) is not None
    assert db_session.get(ParkingSlot, parking_slot.id) is not None


@pytest.mark.parametrize(
    ("resource", "field"),
    [
        ("zones", "name"),
        ("zones", "capacity"),
        ("zones", "is_active"),
        ("parking-slots", "slot_name"),
        ("parking-slots", "zone_id"),
        ("parking-slots", "vehicle_type_id"),
        ("parking-slots", "is_active"),
    ],
)
def test_partial_updates_reject_explicit_null(
    client: TestClient,
    test_user: User,
    zone: Zone,
    parking_slot: ParkingSlot,
    resource: str,
    field: str,
):
    resource_id = zone.id if resource == "zones" else parking_slot.id
    before = client.get(
        f"/api/v1/{resource}/{resource_id}", headers=make_headers(test_user)
    ).json()

    response = client.put(
        f"/api/v1/{resource}/{resource_id}",
        headers=make_headers(test_user),
        json={field: None},
    )

    assert response.status_code == 422
    assert field in str(response.json())
    after = client.get(
        f"/api/v1/{resource}/{resource_id}", headers=make_headers(test_user)
    ).json()
    assert after == before


def test_database_rejects_duplicate_zone_name_case_insensitively(
    db_session: Session,
    zone: Zone,
):
    db_session.add(Zone(name="  kHU a  ", capacity=10, is_active=True))

    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()

    assert db_session.query(Zone).count() == 1


def test_database_rejects_duplicate_slot_code_case_insensitively(
    db_session: Session,
    zone: Zone,
    vehicle_type: VehicleType,
    parking_slot: ParkingSlot,
):
    db_session.add(
        ParkingSlot(
            slot_name=" a-01 ",
            zone_id=zone.id,
            vehicle_type_id=vehicle_type.id,
            is_occupied=False,
            is_active=True,
        )
    )

    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()

    assert db_session.query(ParkingSlot).count() == 1


def test_openapi_keeps_occupancy_read_only_and_forbids_unknown_fields(
    client: TestClient,
):
    schemas = client.get("/openapi.json").json()["components"]["schemas"]

    for schema_name in ("ParkingSlotCreate", "ParkingSlotUpdate"):
        assert schemas[schema_name]["additionalProperties"] is False
        assert "is_occupied" not in schemas[schema_name]["properties"]
    assert "is_occupied" in schemas["ParkingSlotResponse"]["properties"]
    for schema_name in ("ZoneCreate", "ZoneUpdate"):
        assert schemas[schema_name]["additionalProperties"] is False


def test_sqlite_test_database_enforces_foreign_keys(db_session: Session):
    enabled = db_session.connection().exec_driver_sql("PRAGMA foreign_keys").scalar_one()
    assert enabled == 1


def test_database_rejects_deleting_slot_with_session_history(
    db_session: Session,
    parking_slot: ParkingSlot,
    parking_session: ParkingSession,
):
    slot_id = parking_slot.id
    session_id = parking_session.id
    db_session.delete(parking_slot)

    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()

    assert db_session.get(ParkingSlot, slot_id) is not None
    assert db_session.get(ParkingSession, session_id).parking_slot_id == slot_id


def test_database_rejects_direct_slot_insert_beyond_zone_capacity(
    db_session: Session,
    zone: Zone,
    vehicle_type: VehicleType,
    parking_slot: ParkingSlot,
):
    zone.capacity = 1
    db_session.commit()
    db_session.add(
        ParkingSlot(
            slot_name="CAPACITY-DIRECT-02",
            zone_id=zone.id,
            vehicle_type_id=vehicle_type.id,
            is_occupied=False,
            is_active=True,
        )
    )

    with pytest.raises(IntegrityError, match="zone capacity exceeded"):
        db_session.commit()
    db_session.rollback()

    assert db_session.query(ParkingSlot).filter_by(zone_id=zone.id).count() == 1


def test_database_rejects_direct_zone_capacity_reduction(
    db_session: Session,
    zone: Zone,
    parking_slot: ParkingSlot,
):
    zone.capacity = 0

    with pytest.raises(IntegrityError, match="zone capacity below slot count"):
        db_session.commit()
    db_session.rollback()

    db_session.refresh(zone)
    assert zone.capacity == 50
    assert parking_slot.zone_id == zone.id


def test_database_rejects_direct_move_into_full_zone(
    db_session: Session,
    parking_slot: ParkingSlot,
    vehicle_type: VehicleType,
):
    destination = Zone(name="Khu full trực tiếp", capacity=1, is_active=True)
    db_session.add(destination)
    db_session.flush()
    db_session.add(
        ParkingSlot(
            slot_name="DIRECT-FULL-01",
            zone_id=destination.id,
            vehicle_type_id=vehicle_type.id,
            is_occupied=False,
            is_active=True,
        )
    )
    db_session.commit()
    original_zone_id = parking_slot.zone_id
    parking_slot.zone_id = destination.id

    with pytest.raises(IntegrityError, match="zone capacity exceeded"):
        db_session.commit()
    db_session.rollback()

    db_session.refresh(parking_slot)
    assert parking_slot.zone_id == original_zone_id


def test_migration_adds_normalized_unique_indexes_to_existing_database(tmp_path):
    migration_engine = create_engine(f"sqlite:///{(tmp_path / 'legacy.db').as_posix()}")
    with migration_engine.begin() as connection:
        connection.exec_driver_sql(
            "CREATE TABLE zones ("
            "id INTEGER PRIMARY KEY, name VARCHAR(50) NOT NULL, "
            "capacity INTEGER NOT NULL, is_active BOOLEAN NOT NULL)"
        )
        connection.exec_driver_sql(
            "CREATE TABLE parking_slots ("
            "id INTEGER PRIMARY KEY, zone_id INTEGER NOT NULL, "
            "vehicle_type_id INTEGER NOT NULL, slot_name VARCHAR(50) NOT NULL, "
            "is_occupied BOOLEAN NOT NULL, is_active BOOLEAN NOT NULL)"
        )
        connection.exec_driver_sql(
            "INSERT INTO zones(id, name, capacity, is_active) "
            "VALUES (1, 'Khu A', 10, 1)"
        )
        connection.exec_driver_sql(
            "INSERT INTO parking_slots("
            "id, zone_id, vehicle_type_id, slot_name, is_occupied, is_active) "
            "VALUES (1, 1, 1, 'A-01', 0, 1)"
        )

    run_sqlite_migrations(migration_engine)
    run_sqlite_migrations(migration_engine)

    with migration_engine.connect() as connection:
        zone_indexes = {
            row[1] for row in connection.exec_driver_sql("PRAGMA index_list(zones)")
        }
        slot_indexes = {
            row[1]
            for row in connection.exec_driver_sql("PRAGMA index_list(parking_slots)")
        }
        triggers = {
            row[0]
            for row in connection.exec_driver_sql(
                "SELECT name FROM sqlite_master WHERE type = 'trigger'"
            )
        }
    assert "uq_zones_name_normalized" in zone_indexes
    assert "uq_parking_slots_name_normalized" in slot_indexes
    assert triggers == {
        "trg_parking_slots_capacity_insert",
        "trg_parking_slots_capacity_move",
        "trg_zones_capacity_update",
    }

    with pytest.raises(IntegrityError):
        with migration_engine.begin() as connection:
            connection.exec_driver_sql(
                "INSERT INTO zones(id, name, capacity, is_active) "
                "VALUES (2, '  khu a  ', 10, 1)"
            )
    with pytest.raises(IntegrityError):
        with migration_engine.begin() as connection:
            connection.exec_driver_sql(
                "INSERT INTO parking_slots("
                "id, zone_id, vehicle_type_id, slot_name, is_occupied, is_active) "
                "VALUES (2, 1, 1, ' a-01 ', 0, 1)"
            )


def test_migration_fails_loudly_for_legacy_normalized_duplicates(tmp_path):
    migration_engine = create_engine(f"sqlite:///{(tmp_path / 'duplicate.db').as_posix()}")
    with migration_engine.begin() as connection:
        connection.exec_driver_sql(
            "CREATE TABLE zones ("
            "id INTEGER PRIMARY KEY, name VARCHAR(50) NOT NULL, "
            "capacity INTEGER NOT NULL, is_active BOOLEAN NOT NULL)"
        )
        connection.exec_driver_sql(
            "INSERT INTO zones(id, name, capacity, is_active) VALUES "
            "(1, 'Khu A', 10, 1), (2, '  khu a  ', 10, 1)"
        )

    with pytest.raises(RuntimeError, match="trùng sau chuẩn hóa"):
        run_sqlite_migrations(migration_engine)


def test_migration_fails_loudly_for_legacy_capacity_violation(tmp_path):
    migration_engine = create_engine(f"sqlite:///{(tmp_path / 'capacity.db').as_posix()}")
    with migration_engine.begin() as connection:
        connection.exec_driver_sql(
            "CREATE TABLE zones ("
            "id INTEGER PRIMARY KEY, name VARCHAR(50) NOT NULL, "
            "capacity INTEGER NOT NULL, is_active BOOLEAN NOT NULL)"
        )
        connection.exec_driver_sql(
            "CREATE TABLE parking_slots ("
            "id INTEGER PRIMARY KEY, zone_id INTEGER NOT NULL, "
            "vehicle_type_id INTEGER NOT NULL, slot_name VARCHAR(50) NOT NULL, "
            "is_occupied BOOLEAN NOT NULL, is_active BOOLEAN NOT NULL)"
        )
        connection.exec_driver_sql(
            "INSERT INTO zones(id, name, capacity, is_active) "
            "VALUES (1, 'Khu quá tải', 1, 1)"
        )
        connection.exec_driver_sql(
            "INSERT INTO parking_slots("
            "id, zone_id, vehicle_type_id, slot_name, is_occupied, is_active) "
            "VALUES (1, 1, 1, 'A-01', 0, 1), (2, 1, 1, 'A-02', 0, 1)"
        )

    with pytest.raises(RuntimeError, match="vượt sức chứa"):
        run_sqlite_migrations(migration_engine)
