"""Small capture clock skew must not bypass any other passage safety gate."""
from datetime import timedelta

import pytest

from test_vision_passage import passage, enable, frame, process  # noqa: F401


@pytest.mark.parametrize("ahead", [1, 3, 5])
def test_fresh_confident_known_vehicle_tolerates_small_future_clock(passage, ahead):
    p = passage; enable(p)
    identity = frame(p, captured_at=p["instant"][0] + timedelta(seconds=ahead))
    response = process(p, identity)
    assert response.status_code == 200, response.text
    assert response.json()["state"] == "entered"


@pytest.mark.parametrize("change", ["large_future", "stale_capture", "stale_receipt", "before_policy", "low_confidence"])
def test_skew_tolerance_keeps_age_receipt_policy_and_confidence_guards(passage, change):
    p = passage; enable(p)
    now = p["instant"][0]
    changes = {"large_future": {"captured_at": now + timedelta(seconds=6)},
        "stale_capture": {"captured_at": now - timedelta(seconds=16)},
        "stale_receipt": {"observed_at": now - timedelta(seconds=16)},
        "before_policy": {"captured_at": now - timedelta(seconds=8)},
        "low_confidence": {"captured_at": now + timedelta(seconds=3), "confidence": .90}}
    assert process(p, frame(p, **changes[change])).json()["state"] == "manual"
