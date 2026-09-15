"""Bounded camera/video capture into the existing human-reviewed OCR inbox.

No recognition, admission, checkout, or payment occurs here. Network retries
reuse exactly the same event identifier, capture time, and JPEG. Source URLs
and camera tokens are never included in status output.
"""
from __future__ import annotations

import argparse
from dataclasses import dataclass, field
from datetime import datetime, timezone
import json
import math
import multiprocessing as mp
import os
from pathlib import Path
from queue import Empty, Full
import time
from urllib.parse import urlsplit
from uuid import uuid4

import httpx


MAX_IMAGE_BYTES = 2 * 1024 * 1024


class CaptureError(RuntimeError):
    """A sanitized actionable failure, without source URLs or HTTP headers."""


@dataclass(frozen=True)
class CaptureEvent:
    camera_id: int
    event_id: str
    captured_at: str
    jpeg: bytes = field(repr=False)

    @classmethod
    def create(cls, camera_id, jpeg, captured_at):
        if type(camera_id) is not int or camera_id < 1:
            raise CaptureError("Camera ID must be a positive integer.")
        if not isinstance(jpeg, bytes) or not 0 < len(jpeg) <= MAX_IMAGE_BYTES:
            raise CaptureError("Encoded image must be at most 2 MB.")
        if captured_at.tzinfo is None:
            raise CaptureError("Capture time must include its timezone.")
        return cls(camera_id, str(uuid4()), captured_at.isoformat(), jpeg)


def validate_origin(value):
    parsed = urlsplit(value)
    if (not parsed.hostname or parsed.username or parsed.password or parsed.query
            or parsed.fragment or parsed.path not in ("", "/")
            or parsed.scheme not in ("http", "https")):
        raise CaptureError("API origin must be an HTTP(S) origin without credentials or a path.")
    if parsed.scheme == "http" and parsed.hostname not in ("localhost", "127.0.0.1", "::1"):
        raise CaptureError("Use HTTPS for a remote API, or HTTP on loopback at the local edge computer.")
    return value.rstrip("/")


def deliver_event(client, event, token, *, attempts=4, sleep=time.sleep):
    """Retry transient/ambiguous responses without constructing another event."""
    if not isinstance(token, str) or not 32 <= len(token) <= 128:
        raise CaptureError("Configure a valid camera token in the selected environment variable.")
    if type(attempts) is not int or not 1 <= attempts <= 8:
        raise CaptureError("Retry attempts must be between 1 and 8.")
    for attempt in range(attempts):
        delay = min(2 ** attempt, 10)
        try:
            response = client.post(
                "/api/v2/vision/edge-events",
                headers={"X-Camera-Token": token},
                data={"camera_id": str(event.camera_id), "event_id": event.event_id,
                      "captured_at": event.captured_at},
                files={"file": ("capture.jpg", event.jpeg, "image/jpeg")},
                follow_redirects=False,
            )
            if response.status_code == 201:
                try:
                    data = response.json()
                except ValueError:
                    data = None
                if (isinstance(data, dict) and data.get("received") is True
                        and data.get("event_id") == event.event_id
                        and isinstance(data.get("id"), str) and data["id"]):
                    return {"event_id": event.event_id, "observation_id": data["id"], "received": True}
                # A malformed acknowledgement is ambiguous: retry this event.
            elif response.status_code in (401, 403):
                raise CaptureError("Camera token was rejected or revoked. Stop and configure a new token.")
            elif response.status_code not in (408, 425, 429) and response.status_code < 500:
                raise CaptureError(f"Image was not accepted (HTTP {response.status_code}); review the camera inbox/configuration.")
            else:
                retry_after = response.headers.get("Retry-After", "")
                if retry_after.isascii() and retry_after.isdigit():
                    delay = min(max(int(retry_after), delay), 30)
        except httpx.TransportError:
            pass  # Never log an exception carrying a camera token or URL.
        if attempt + 1 < attempts:
            sleep(delay)
    raise CaptureError("Delivery remains unconfirmed after bounded retries; check the inbox before restarting capture.")


def encode_frame(frame, cv):
    """Bound the upload without changing aspect ratio or trusting camera size."""
    if frame is None or len(frame.shape) != 3 or frame.shape[2] != 3:
        raise CaptureError("Camera returned an invalid color frame.")
    height, width = frame.shape[:2]
    if min(width, height) < 16 or width * height > 12_000_000:
        raise CaptureError("Frame dimensions are outside the supported range.")
    scale = min(1.0, 1600 / max(width, height))
    if scale < 1:
        frame = cv.resize(frame, (round(width * scale), round(height * scale)), interpolation=cv.INTER_AREA)
    for quality in (85, 70, 55):
        ok, encoded = cv.imencode(".jpg", frame, [cv.IMWRITE_JPEG_QUALITY, quality])
        if ok and 0 < encoded.size <= MAX_IMAGE_BYTES:
            return encoded.tobytes()
    raise CaptureError("Frame cannot be encoded within the upload limit.")


def _offer_latest(queue, item):
    """Only one waiting frame; slow inference never creates an unbounded queue."""
    try:
        queue.put_nowait(item)
        return
    except Full:
        try:
            queue.get_nowait()
        except Empty:
            pass
    try:
        queue.put_nowait(item)
    except Full:
        pass


def _finish(queue, stop, status):
    # Preserve the final sampled frame; wait cooperatively for its consumer
    # instead of replacing it with EOF or losing EOF during a slow upload.
    while not stop.is_set():
        try:
            queue.put((status, None, None), timeout=.2)
            return
        except Full:
            continue


def _capture_worker(kind, source, interval, queue, stop):
    # FFmpeg/OpenCV can print a credential-bearing RTSP URL from native code.
    # Silence this child's native stderr; parent emits sanitized status only.
    with open(os.devnull, "w") as quiet:
        os.dup2(quiet.fileno(), 2)
    capture = None
    try:
        import cv2 as cv
        if kind == "stream":
            capture = cv.VideoCapture(source, cv.CAP_FFMPEG, [
                cv.CAP_PROP_OPEN_TIMEOUT_MSEC, 5000, cv.CAP_PROP_READ_TIMEOUT_MSEC, 5000,
            ])
        else:
            capture = cv.VideoCapture(source)
        if not capture.isOpened():
            raise CaptureError("Capture source could not be opened.")
        fps = capture.get(cv.CAP_PROP_FPS)
        if not math.isfinite(fps) or fps <= 0:
            fps = 30.0
        started = time.monotonic()
        next_sample = started
        frame_number = 0
        while not stop.is_set():
            ok, frame = capture.read()
            if not ok:
                _finish(queue, stop, "end" if kind == "video" else "error")
                return
            # Files replay at their declared frame rate, not as a burst of old
            # imagery. captured_at is the replay acquisition time, not source time.
            if kind == "video" and stop.wait(max(0, started + frame_number / fps - time.monotonic())):
                return
            frame_number += 1
            current = time.monotonic()
            if current >= next_sample:
                jpeg = encode_frame(frame, cv)
                stamp = datetime.now(timezone.utc)
                _offer_latest(queue, ("frame", jpeg, stamp))
                next_sample = current + interval
    except Exception:
        _finish(queue, stop, "error")
    finally:
        if capture is not None:
            capture.release()


def iter_capture(kind, source, *, interval=5.0, read_timeout=15.0):
    """Isolate native device reads; a stalled camera cannot hang the API process."""
    if kind not in ("video", "device", "stream") or not 3 <= interval <= 30:
        raise CaptureError("Capture kind or interval is invalid (interval: 3–30 seconds).")
    context = mp.get_context("spawn")
    queue, stop = context.Queue(maxsize=1), context.Event()
    worker = context.Process(target=_capture_worker, args=(kind, source, interval, queue, stop), daemon=True)
    worker.start()
    try:
        while True:
            try:
                status, jpeg, stamp = queue.get(timeout=max(read_timeout, interval + 5))
            except Empty:
                raise CaptureError("Camera stopped producing frames; capture was stopped.") from None
            if status == "end":
                return
            if status != "frame":
                raise CaptureError("Capture failed or the camera disconnected.")
            yield jpeg, stamp
    finally:
        stop.set()
        worker.join(timeout=2)
        if worker.is_alive():
            worker.terminate()
            worker.join(timeout=3)
        queue.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    source_group = parser.add_mutually_exclusive_group(required=True)
    source_group.add_argument("--video", type=Path, help="Local replay video; use a clearly labelled DEMO camera.")
    source_group.add_argument("--device", type=int, help="Explicit local webcam index, e.g. 0.")
    source_group.add_argument("--stream-env", help="Name of environment variable containing an RTSP(S) source URL.")
    parser.add_argument("--api-origin", default="http://127.0.0.1:8766")
    parser.add_argument("--camera-id", type=int, required=True)
    parser.add_argument("--token-env", default="PARKINGAI_CAMERA_TOKEN")
    parser.add_argument("--interval", type=float, default=5)
    parser.add_argument("--max-events", type=int, default=20, help="0 means continuous until Ctrl+C.")
    args = parser.parse_args()
    count = 0
    pending_id = None
    try:
        origin = validate_origin(args.api_origin)
        token = os.environ.get(args.token_env, "")
        if not 32 <= len(token) <= 128 or args.camera_id < 1 or args.max_events < 0:
            raise CaptureError("Configure a camera ID/token and nonnegative event limit before capture.")
        if args.video is not None:
            if not args.video.is_file():
                raise CaptureError("Replay video does not exist.")
            kind, source = "video", str(args.video.resolve())
        elif args.device is not None:
            if args.device < 0:
                raise CaptureError("Webcam index must be nonnegative.")
            kind, source = "device", args.device
        else:
            kind, source = "stream", os.environ.get(args.stream_env, "")
            if urlsplit(source).scheme not in ("rtsp", "rtsps") or not urlsplit(source).hostname:
                raise CaptureError("Configure a valid RTSP(S) source in the selected environment variable.")
        with httpx.Client(base_url=origin, trust_env=False, timeout=httpx.Timeout(20, connect=5, pool=2)) as client:
            frames = iter_capture(kind, source, interval=args.interval)
            try:
                for jpeg, stamp in frames:
                    event = CaptureEvent.create(args.camera_id, jpeg, stamp)
                    pending_id = event.event_id
                    result = deliver_event(client, event, token)
                    count += 1
                    pending_id = None
                    print(json.dumps({**result, "source_kind": kind, "accepted": count}), flush=True)
                    if args.max_events and count >= args.max_events:
                        break
            finally:
                frames.close()
        return 0
    except KeyboardInterrupt:
        print(json.dumps({"status": "stopped", "accepted": count, "unconfirmed_event_id": pending_id}))
        return 0
    except CaptureError as error:
        print(json.dumps({"status": "stopped", "accepted": count,
                          "unconfirmed_event_id": pending_id, "reason": str(error)}))
        return 1
    except Exception:
        print(json.dumps({"status": "stopped", "accepted": count, "unconfirmed_event_id": pending_id,
                          "reason": "Capture encountered an unexpected error."}))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
