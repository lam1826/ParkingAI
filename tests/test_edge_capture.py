"""Offline transport and video probes; never open a physical camera or server."""
from datetime import datetime, timezone
from email import message_from_bytes
from pathlib import Path
from queue import Queue
import sys

import httpx
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from edge.capture_agent import (
    CaptureError, CaptureEvent, _offer_latest, deliver_event, encode_frame,
    iter_capture, validate_origin,
)


TOKEN = "offline-camera-token-without-real-authority"


def _fields(request):
    request.read()
    message = message_from_bytes(b"Content-Type: " + request.headers["content-type"].encode() + b"\r\n\r\n" + request.content)
    return {part.get_param("name", header="content-disposition"): part.get_payload(decode=True)
            for part in message.walk() if part.get_param("name", header="content-disposition")}


def _event():
    return CaptureEvent.create(17, b"offline-jpeg-fixture", datetime(2026, 9, 15, 1, 0, tzinfo=timezone.utc))


def test_lost_ack_retry_preserves_the_complete_event_and_only_one_observation():
    stored, requests, delays = {}, [], []
    event = _event()

    def transport(request):
        fields = _fields(request)
        requests.append(fields)
        assert request.url.path == "/api/v2/vision/edge-events"
        assert request.headers["x-camera-token"] == TOKEN
        stored.setdefault(fields["event_id"], "observation-1")
        if len(requests) == 1:
            raise httpx.ReadTimeout("lost response; confidential transport details", request=request)
        return httpx.Response(201, json={"received": True, "id": "observation-1", "event_id": event.event_id})

    with httpx.Client(base_url="http://localhost", transport=httpx.MockTransport(transport)) as client:
        result = deliver_event(client, event, TOKEN, sleep=delays.append)
    assert len(stored) == 1 and len(requests) == 2
    assert requests[0] == requests[1]
    assert requests[0]["file"] == event.jpeg
    assert requests[0]["captured_at"] == event.captured_at.encode()
    assert result == {"received": True, "event_id": event.event_id, "observation_id": "observation-1"}
    assert delays == [1]


@pytest.mark.parametrize("status", [401, 403, 409, 410, 413, 422, 302])
def test_permanent_rejection_and_redirect_stop_without_retry_or_secret_disclosure(status):
    calls = []
    def transport(request):
        calls.append(request.url)
        return httpx.Response(status, headers={"Location": "https://unrelated.invalid"}, text=TOKEN)
    with httpx.Client(base_url="http://localhost", transport=httpx.MockTransport(transport)) as client:
        with pytest.raises(CaptureError) as error:
            deliver_event(client, _event(), TOKEN, sleep=lambda _: pytest.fail("Must not retry"))
    assert len(calls) == 1
    assert TOKEN not in str(error.value) and "unrelated" not in str(error.value)


@pytest.mark.parametrize("status", [408, 425, 429, 500, 503])
def test_busy_server_retries_are_bounded_and_honor_capped_retry_after(status):
    calls, delays = [], []
    def transport(request):
        calls.append(_fields(request))
        return httpx.Response(status, headers={"Retry-After": "9999"})
    with httpx.Client(base_url="http://localhost", transport=httpx.MockTransport(transport)) as client:
        with pytest.raises(CaptureError, match="unconfirmed"):
            deliver_event(client, _event(), TOKEN, attempts=3, sleep=delays.append)
    assert len(calls) == 3 and calls[0] == calls[1] == calls[2]
    assert delays == [30, 30]


@pytest.mark.parametrize("payload", [{"received": True, "event_id": "wrong", "id": "x"},
                                     {"received": "true", "event_id": "wrong", "id": "x"},
                                     {}, ["not-an-ack"]])
def test_invalid_success_body_is_never_reported_as_received(payload):
    with httpx.Client(base_url="http://localhost", transport=httpx.MockTransport(lambda _: httpx.Response(201, json=payload))) as client:
        with pytest.raises(CaptureError, match="unconfirmed"):
            deliver_event(client, _event(), TOKEN, attempts=1)


@pytest.mark.parametrize("url", ["http://192.168.1.5", "https://user:secret@example.com",
                                  "https://example.com/path", "https://example.com?q=secret",
                                  "file:///capture", "https://example.com/#x"])
def test_origin_rejects_credential_leaks_and_remote_plaintext(url):
    with pytest.raises(CaptureError):
        validate_origin(url)


def test_origin_accepts_local_demo_and_remote_tls():
    assert validate_origin("http://127.0.0.1:8766/") == "http://127.0.0.1:8766"
    assert validate_origin("https://parking.example") == "https://parking.example"


def test_latest_frame_queue_stays_bounded():
    queue = Queue(maxsize=1)
    _offer_latest(queue, "old")
    _offer_latest(queue, "new")
    assert queue.qsize() == 1 and queue.get_nowait() == "new"


def test_frames_are_sized_encoded_and_decodable_without_changing_aspect_ratio():
    cv = pytest.importorskip("cv2")
    np = pytest.importorskip("numpy")
    jpeg = encode_frame(np.full((1080, 1920, 3), 120, dtype=np.uint8), cv)
    decoded = cv.imdecode(np.frombuffer(jpeg, dtype=np.uint8), cv.IMREAD_COLOR)
    assert decoded.shape[:2] == (900, 1600)
    assert 0 < len(jpeg) < 2 * 1024 * 1024


def test_local_video_replay_returns_a_real_encoded_frame_and_clean_eof(tmp_path):
    cv = pytest.importorskip("cv2")
    np = pytest.importorskip("numpy")
    video = tmp_path / "synthetic-offline.avi"
    writer = cv.VideoWriter(str(video), cv.VideoWriter_fourcc(*"MJPG"), 2, (64, 48))
    if not writer.isOpened():
        pytest.skip("Local OpenCV runtime lacks MJPG writer")
    try:
        writer.write(np.full((48, 64, 3), 80, dtype=np.uint8))
        writer.write(np.full((48, 64, 3), 100, dtype=np.uint8))
    finally:
        writer.release()
    frames = list(iter_capture("video", str(video), interval=3))
    assert len(frames) == 1
    assert frames[0][1].tzinfo is not None
    assert cv.imdecode(np.frombuffer(frames[0][0], dtype=np.uint8), cv.IMREAD_COLOR).shape == (48, 64, 3)


def test_missing_video_fails_safely_without_exposing_source(tmp_path):
    pytest.importorskip("cv2")
    with pytest.raises(CaptureError, match="Capture failed") as error:
        list(iter_capture("video", str(tmp_path / "private-source-name.avi"), interval=3))
    assert "private-source-name" not in str(error.value)
