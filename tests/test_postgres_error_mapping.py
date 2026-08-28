from sqlalchemy.exc import DBAPIError, IntegrityError

from core.errors import is_known_database_business_conflict
from crud.parking_session import map_check_in_integrity_error


def _db_error(message: str) -> DBAPIError:
    return DBAPIError("statement hidden", {}, RuntimeError(message), False)


def test_postgres_active_vehicle_constraint_maps_to_checkin_conflict():
    error = IntegrityError(
        "statement hidden",
        {},
        RuntimeError(
            'duplicate key value violates unique constraint '
            '"uq_parking_session_one_active_per_vehicle"'
        ),
    )
    assert "Xe vừa được check-in" in map_check_in_integrity_error(error)


def test_postgres_active_slot_constraint_maps_to_checkin_conflict():
    error = IntegrityError(
        "statement hidden",
        {},
        RuntimeError(
            'duplicate key value violates unique constraint '
            '"uq_parking_session_one_active_per_slot"'
        ),
    )
    assert "Vị trí đỗ vừa được xe khác" in map_check_in_integrity_error(error)


def test_postgres_business_trigger_is_a_safe_conflict():
    assert is_known_database_business_conflict(
        _db_error("RaiseException: zone capacity exceeded")
    )


def test_unknown_database_failure_is_not_mislabeled_as_business_conflict():
    assert not is_known_database_business_conflict(
        _db_error("connection reset by peer")
    )
