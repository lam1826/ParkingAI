"""#11 fix: idempotent replay of a correction that resolved to an existing canonical vehicle."""
import pytest
from models.vehicle import Vehicle
from test_session_exceptions import env, body  # noqa: F401


@pytest.mark.parametrize("existing", [False, True])
def test_correction_replay_is_idempotent(env, existing):
    if existing:
        env.db.add(Vehicle(license_plate="59A-777.77", vehicle_type_id=env.vehicle.vehicle_type_id))
        env.db.commit()
    first = env.client.post(env.base + "/correct-plate", json=body(license_plate="59A77777"))
    assert first.status_code == 200, first.text
    replay = env.client.post(env.base + "/correct-plate", json=body(license_plate="59A77777"))
    assert replay.status_code == 200, replay.text
    assert replay.json()["replacement_session_id"] == first.json()["replacement_session_id"]
