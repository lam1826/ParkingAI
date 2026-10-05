"""Offline edge CLI regressions: shed load safely, bound uncertain delivery."""
from datetime import datetime, timezone
from functools import partial
import json
import sys

import httpx
import pytest

import edge.capture_agent as agent


TOKEN = "offline-camera-token-without-real-authority"


def run_capture(monkeypatch, transport, *, max_events=1, sleep=None):
    original_client = httpx.Client
    client = original_client(base_url="http://localhost", transport=httpx.MockTransport(transport))
    monkeypatch.setattr(agent.httpx, "Client", lambda **kwargs: client)
    delays, pulled = [], []
    sleeper = sleep or delays.append
    monkeypatch.setattr(agent.time, "sleep", sleeper)
    monkeypatch.setattr(agent, "deliver_event", partial(agent.deliver_event, sleep=sleeper))
    monkeypatch.setenv("PARKINGAI_CAMERA_TOKEN", TOKEN)
    monkeypatch.setattr(sys, "argv", ["capture_agent.py", "--device", "0", "--camera-id", "17",
                                    "--max-events", str(max_events)])

    def frames(*args, **kwargs):
        for frame in range(3):
            pulled.append(frame)
            yield b"offline-jpeg", datetime.now(timezone.utc)

    monkeypatch.setattr(agent, "iter_capture", frames)
    return agent.main(), delays, pulled


def event_id(request):
    # The public multipart payload retains an id for retries of each frame.
    request.read()
    from email import message_from_bytes
    message = message_from_bytes(b"Content-Type: " + request.headers["content-type"].encode()
                                 + b"\r\n\r\n" + request.content)
    for part in message.walk():
        if part.get_param("name", header="content-disposition") == "event_id":
            return part.get_payload(decode=True).decode()
    pytest.fail("No event id sent")


def test_repeated_upload_slot_contention_backs_off_then_accepts_a_fresh_frame(monkeypatch, capsys):
    identifiers = []

    def transport(request):
        identifier = event_id(request)
        identifiers.append(identifier)
        if len(identifiers) <= 8:
            return httpx.Response(429, headers={"Retry-After": "9999"})
        return httpx.Response(201, json={"received": True, "id": "observation-1", "event_id": identifier})

    code, delays, pulled = run_capture(monkeypatch, transport)
    assert code == 0
    assert pulled == [0, 1, 2]
    assert identifiers[:4] == [identifiers[0]] * 4
    assert identifiers[4:8] == [identifiers[4]] * 4
    assert len(set(identifiers)) == 3
    assert delays == [30] * 8
    output = [json.loads(line) for line in capsys.readouterr().out.splitlines()]
    assert [row["status"] for row in output[:-1]] == ["backoff", "backoff"]
    assert output[-1]["received"] is True and output[-1]["accepted"] == 1
    assert all(TOKEN not in json.dumps(row) for row in output)


@pytest.mark.parametrize("uncertain", ["transport", "server", "acknowledgement"])
def test_a_busy_last_response_cannot_discard_an_earlier_uncertain_delivery(monkeypatch, capsys, uncertain):
    calls = []

    def transport(request):
        calls.append(event_id(request))
        if len(calls) == 1:
            if uncertain == "transport":
                raise httpx.ReadTimeout("private-url-or-token", request=request)
            if uncertain == "server":
                return httpx.Response(503)
            return httpx.Response(201, json={"received": True, "event_id": "wrong", "id": "x"})
        return httpx.Response(429, headers={"Retry-After": "3"})

    code, delays, pulled = run_capture(monkeypatch, transport)
    assert code == 1 and len(calls) == 4
    assert len(set(calls)) == 1 and pulled == [0]
    assert delays == [1, 3, 4]
    output = json.loads(capsys.readouterr().out)
    assert output["status"] == "stopped" and output["unconfirmed_event_id"] == calls[0]
    assert "private-url-or-token" not in output["reason"]


def test_keyboard_interrupt_during_busy_backoff_has_no_unconfirmed_frame(monkeypatch, capsys):
    delays = []

    def sleep(delay):
        delays.append(delay)
        if len(delays) == 4:
            raise KeyboardInterrupt

    code, _, pulled = run_capture(monkeypatch, lambda _: httpx.Response(429), max_events=0, sleep=sleep)
    assert code == 0 and pulled == [0]
    output = [json.loads(line) for line in capsys.readouterr().out.splitlines()]
    assert output[-1]["status"] == "stopped"
    assert output[-1]["unconfirmed_event_id"] is None
