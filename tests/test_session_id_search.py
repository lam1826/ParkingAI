"""Ticket IDs are exact filters combined with the existing timeline scope."""
import pytest

from test_cancelled_analytics import env, traffic  # noqa: F401
from routers.parking import router as parking_router


@pytest.mark.parametrize("scoped", [True, False])
def test_ticket_id_search_is_exact_and_combines_status_and_plate(traffic, scoped):
    env, today, rows = traffic
    if scoped:
        url = f"/api/v2/sites/{env.a.id}/sessions"
    else:
        env.client.app.include_router(parking_router)
        url = "/parking/search"

    def found(params):
        response = env.client.get(url, params=params)
        assert response.status_code == 200, response.text
        result = response.json()
        return result if scoped else result["items"]

    selected = rows[0].id
    result = found({"session_id": selected, "status": "cancelled", "license_plate": env.vehicle.license_plate})
    assert len(result) == 1
    assert result[0]["id" if scoped else "session_id"] == selected
    assert found({"session_id": selected, "status": "active"}) == []
    assert found({"session_id": selected, "license_plate": "DOESNOTMATCH"}) == []
    assert found({"session_id": selected[:-1]}) == []
    assert found({"session_id": "%"}) == []
    assert found({"session_id": selected, "date_from": str(today)})
    assert env.client.get(url, params={"session_id": "x" * 37}).status_code == 422
    assert env.client.get(url, params={"session_id": "   "}).status_code == 422


def test_known_ticket_id_cannot_bypass_site_permission(traffic):
    env, _, rows = traffic
    response = env.client.get(f"/api/v2/sites/{env.b.id}/sessions", params={"session_id": rows[2].id})
    assert response.status_code == 403
