"""Read-only production RBAC contract probe.

Credentials are read only from role-scoped environment variables. The script
logs neither passwords nor bearer tokens and calls no mutating business API.
"""

from __future__ import annotations

import argparse
import json
import os
import urllib.error
import urllib.request
from dataclasses import dataclass
from urllib.parse import urlparse


ROLES = ("customer", "staff", "manager", "admin")


@dataclass(frozen=True)
class ProbeCase:
    name: str
    path: str
    method: str
    expected_status: dict[str, int]


PROBE_CASES = (
    ProbeCase(
        name="own profile",
        path="/api/auth/me",
        method="GET",
        expected_status={role: 200 for role in ROLES},
    ),
    ProbeCase(
        name="staff zone list",
        path="/api/v1/zones?limit=1",
        method="GET",
        expected_status={
            "customer": 403,
            "staff": 200,
            "manager": 200,
            "admin": 200,
        },
    ),
    ProbeCase(
        name="manager user list",
        path="/api/v1/users?limit=1",
        method="GET",
        expected_status={
            "customer": 403,
            "staff": 403,
            "manager": 200,
            "admin": 200,
        },
    ),
    ProbeCase(
        name="manager role list",
        path="/api/v1/roles?limit=1",
        method="GET",
        expected_status={
            "customer": 403,
            "staff": 403,
            "manager": 200,
            "admin": 200,
        },
    ),
)


def credential_env_names(role: str) -> tuple[str, str]:
    if role not in ROLES:
        raise ValueError(f"Unknown role: {role}")
    prefix = f"PARKINGAI_PROBE_{role.upper()}"
    return f"{prefix}_USERNAME", f"{prefix}_PASSWORD"


def validate_base_url(value: str) -> str:
    parsed = urlparse(value)
    if parsed.scheme != "https":
        raise ValueError("HTTPS is required for a production RBAC probe")
    if not parsed.hostname or parsed.query or parsed.fragment:
        raise ValueError("Base URL must be an HTTPS origin")
    if parsed.path not in ("", "/"):
        raise ValueError("Base URL must be an origin without a path")
    return value.rstrip("/")


def _request_json(
    url: str,
    *,
    method: str,
    timeout: float,
    body: dict[str, str] | None = None,
    token: str | None = None,
) -> tuple[int, object | None]:
    headers = {
        "Accept": "application/json",
        "User-Agent": "ParkingAI-production-rbac-probe/1.0",
    }
    payload = None
    if body is not None:
        headers["Content-Type"] = "application/json"
        payload = json.dumps(body).encode("utf-8")
    if token is not None:
        headers["Authorization"] = f"Bearer {token}"
    request = urllib.request.Request(
        url,
        data=payload,
        headers=headers,
        method=method,
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw = response.read()
            status = response.status
    except urllib.error.HTTPError as exc:
        raw = exc.read()
        status = exc.code
    decoded = json.loads(raw) if raw else None
    return status, decoded


def _login(
    base_url: str,
    *,
    role: str,
    timeout: float,
) -> str:
    username_name, password_name = credential_env_names(role)
    username = os.environ.get(username_name)
    password = os.environ.get(password_name)
    if not username or not password:
        raise RuntimeError(
            f"Missing {username_name} or {password_name}; credentials are never logged"
        )
    status, response = _request_json(
        f"{base_url}/api/auth/login",
        method="POST",
        timeout=timeout,
        body={"username": username, "password": password},
    )
    if status != 200 or not isinstance(response, dict):
        raise RuntimeError(f"Login failed for role {role} with HTTP {status}")
    token = response.get("access_token")
    if not isinstance(token, str) or not token:
        raise RuntimeError(f"Login response for role {role} has no token")
    return token


def run_role(
    base_url: str,
    *,
    role: str,
    timeout: float,
) -> list[dict[str, object]]:
    token = _login(base_url, role=role, timeout=timeout)
    results: list[dict[str, object]] = []
    for case in PROBE_CASES:
        actual, response = _request_json(
            f"{base_url}{case.path}",
            method=case.method,
            timeout=timeout,
            token=token,
        )
        expected = case.expected_status[role]
        passed = actual == expected
        if case.name == "own profile" and actual == 200:
            passed = (
                passed
                and isinstance(response, dict)
                and response.get("role") == role
            )
        results.append(
            {
                "role": role,
                "case": case.name,
                "expected": expected,
                "actual": actual,
                "passed": passed,
            }
        )
    return results


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Verify production RBAC with login plus GET-only API calls"
    )
    parser.add_argument("--base-url", default="https://api.parkingai.am")
    parser.add_argument("--role", action="append", choices=ROLES, required=True)
    parser.add_argument("--timeout", type=float, default=10.0)
    args = parser.parse_args()

    try:
        base_url = validate_base_url(args.base_url)
        results: list[dict[str, object]] = []
        for role in dict.fromkeys(args.role):
            results.extend(run_role(base_url, role=role, timeout=args.timeout))
    except (OSError, ValueError, RuntimeError, urllib.error.URLError) as exc:
        print(json.dumps({"passed": False, "error": str(exc)}, ensure_ascii=True))
        return 1

    passed = all(bool(result["passed"]) for result in results)
    print(
        json.dumps(
            {"passed": passed, "results": results},
            ensure_ascii=True,
            indent=2,
        )
    )
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
