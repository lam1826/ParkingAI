"""Bounded, read-only latency probe for ParkingAI health endpoints."""

from __future__ import annotations

import argparse
import json
import math
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from urllib.parse import urlparse


READ_ONLY_PATHS = frozenset({"/", "/ready"})
LOCAL_HOSTS = frozenset({"127.0.0.1", "localhost", "::1"})


@dataclass(frozen=True)
class Sample:
    status: int
    elapsed_ms: float
    error: str | None = None


def validate_target(
    base_url: str,
    path: str,
    *,
    allow_http_localhost: bool = False,
) -> str:
    if path not in READ_ONLY_PATHS:
        raise ValueError(
            "Load probe is read-only; path must be '/' or '/ready'"
        )
    parsed = urlparse(base_url)
    if parsed.query or parsed.fragment or not parsed.hostname:
        raise ValueError("Base URL must not contain query or fragment")
    if parsed.scheme != "https":
        local_http = (
            allow_http_localhost
            and parsed.scheme == "http"
            and parsed.hostname in LOCAL_HOSTS
        )
        if not local_http:
            raise ValueError("HTTPS is required except explicit localhost tests")
    return base_url.rstrip("/") + path


def percentile(values: list[float], quantile: float) -> float:
    if not values:
        raise ValueError("At least one sample is required")
    if not 0 < quantile <= 1:
        raise ValueError("Quantile must be in (0, 1]")
    ordered = sorted(values)
    index = max(0, math.ceil(len(ordered) * quantile) - 1)
    return ordered[index]


def _request_once(url: str, timeout: float) -> Sample:
    request = urllib.request.Request(
        url,
        headers={"User-Agent": "ParkingAI-read-only-load-probe/1.0"},
        method="GET",
    )
    started = time.perf_counter()
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            response.read()
            status = response.status
        error = None if 200 <= status < 300 else f"HTTP {status}"
    except urllib.error.HTTPError as exc:
        status = exc.code
        error = f"HTTP {exc.code}"
    except (OSError, urllib.error.URLError) as exc:
        status = 0
        error = type(exc).__name__
    elapsed_ms = (time.perf_counter() - started) * 1000
    return Sample(status=status, elapsed_ms=elapsed_ms, error=error)


def run_probe(
    url: str,
    *,
    requests_count: int,
    concurrency: int,
    timeout: float,
) -> list[Sample]:
    with ThreadPoolExecutor(max_workers=concurrency) as executor:
        return list(
            executor.map(
                lambda _: _request_once(url, timeout),
                range(requests_count),
            )
        )


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run a bounded GET-only load probe against / or /ready"
    )
    parser.add_argument("--base-url", default="https://api.parkingai.am")
    parser.add_argument("--path", choices=sorted(READ_ONLY_PATHS), default="/ready")
    parser.add_argument("--requests", type=int, default=100)
    parser.add_argument("--concurrency", type=int, default=10)
    parser.add_argument("--timeout", type=float, default=5.0)
    parser.add_argument("--max-error-rate", type=float, default=0.01)
    parser.add_argument("--max-p95-ms", type=float, default=1500.0)
    parser.add_argument("--allow-http-localhost", action="store_true")
    args = parser.parse_args()

    if not 1 <= args.requests <= 10_000:
        raise SystemExit("--requests must be between 1 and 10000")
    if not 1 <= args.concurrency <= min(200, args.requests):
        raise SystemExit("--concurrency must be between 1 and requests")

    target = validate_target(
        args.base_url,
        args.path,
        allow_http_localhost=args.allow_http_localhost,
    )
    samples = run_probe(
        target,
        requests_count=args.requests,
        concurrency=args.concurrency,
        timeout=args.timeout,
    )
    failures = [sample for sample in samples if sample.error is not None]
    elapsed = [sample.elapsed_ms for sample in samples]
    result = {
        "target": target,
        "requests": len(samples),
        "concurrency": args.concurrency,
        "errors": len(failures),
        "error_rate": len(failures) / len(samples),
        "p50_ms": round(percentile(elapsed, 0.5), 2),
        "p95_ms": round(percentile(elapsed, 0.95), 2),
        "max_ms": round(max(elapsed), 2),
        "failure_types": sorted({sample.error for sample in failures}),
    }
    print(json.dumps(result, ensure_ascii=True, indent=2))
    return int(
        result["error_rate"] > args.max_error_rate
        or result["p95_ms"] > args.max_p95_ms
    )


if __name__ == "__main__":
    raise SystemExit(main())
