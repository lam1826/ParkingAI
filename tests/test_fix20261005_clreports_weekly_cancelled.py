"""#62: the server-aggregated weekly AI report must not count cancelled admissions per hour.

Daily totals (get_daily_summaries) already exclude cancelled stays; the hourly traffic given to
the AI as the peak-hour source must use the same rule so the two series agree.
"""
import json
from datetime import datetime

import pytest

from models.ai_report import AiReport
from models.parking_session import ParkingSession
from services.auth_service import AuthService


@pytest.fixture
def business_reference_now():
    return datetime(2026, 8, 20, 17, 45)


def _weekly_payload(prompt):
    marker = prompt.index("DỮ LIỆU TUẦN")
    return json.loads(prompt[prompt.index("{", marker):prompt.rindex("}") + 1])


def test_weekly_hourly_traffic_excludes_cancelled_admissions(client, db_session, manager_user, mock_ai_provider_client,
                                                              vehicle, parking_slot, test_user, price_config):
    day = datetime(2026, 8, 20)
    db_session.add_all([
        ParkingSession(vehicle_id=vehicle.id, parking_slot_id=parking_slot.id, staff_in_id=test_user.id,
                       check_in_time=day.replace(hour=8, minute=10), status="cancelled"),
        ParkingSession(vehicle_id=vehicle.id, parking_slot_id=parking_slot.id, staff_in_id=test_user.id,
                       check_in_time=day.replace(hour=8, minute=20), status="cancelled"),
        ParkingSession(vehicle_id=vehicle.id, parking_slot_id=parking_slot.id, staff_in_id=test_user.id,
                       check_in_time=day.replace(hour=9, minute=10), status="active"),
    ])
    parking_slot.is_occupied = True
    db_session.commit()
    token = AuthService().create_access_token(user_id=manager_user.id, username=manager_user.username,
        role="manager", password_hash=manager_user.password_hash)
    mock_ai_provider_client.return_value.models.generate_content.return_value.text = "Báo cáo tuần."

    response = client.post("/ai/weekly-report", json={"start_date": "2026-08-19", "end_date": "2026-08-25"},
                           headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 200, response.text

    data = _weekly_payload(db_session.query(AiReport).one().prompt_used)
    assert data["hourly_traffic"] == [{"time_label": "09:00", "total_vehicles": 1}]
    assert sum(row["total_vehicles"] for row in data["hourly_traffic"]) == \
        sum(row.get("total_entries", 0) for row in data["daily_summaries"])
