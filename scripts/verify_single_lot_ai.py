"""Record real Gemini responses from an opted-in synthetic one-lot demo.

Runs five provider requests through the application, then checks replay,
history permissions and invalid input. Output holds aggregate input and real
responses for semantic review; an HTTP success is not a factuality verdict.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sqlite3
from time import monotonic
from urllib.parse import urlparse
from uuid import uuid4

import httpx


def verify(base_url: str, credentials_path: Path, output: Path):
    parsed = urlparse(base_url)
    if (parsed.scheme != "http" or parsed.hostname not in {"127.0.0.1", "localhost", "::1"}
            or parsed.username or parsed.password):
        raise ValueError("Only an HTTP loopback demo server is accepted")
    credentials = json.loads(credentials_path.read_text(encoding="utf-8"))
    if credentials.get("profile") != "single-lot-academic-v1":
        raise ValueError("Credentials must belong to the isolated one-lot profile")
    marker = json.loads(Path(credentials["database"] + ".demo.json").read_text(encoding="utf-8"))
    if (marker.get("profile") != credentials["profile"] or marker.get("synthetic_history") is not True
            or marker.get("parkingai_demo") is not True):
        raise ValueError("Missing synthetic one-lot marker")
    prefix = f"/api/v2/sites/{marker['single_site_id']}"
    evidence = {"started_at": datetime.now(timezone.utc).isoformat(), "result": "IN_PROGRESS",
                "scope": "Real configured Gemini; synthetic aggregate data only; no real payments/camera",
                "semantic_review": "PENDING", "checks": [], "analyses": []}
    output.parent.mkdir(parents=True, exist_ok=True)

    def save():
        output.write_text(json.dumps(evidence, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    tokens = {}
    try:
        with httpx.Client(base_url=base_url, timeout=100, follow_redirects=False) as client:
            def call(name, method, path, *, role="manager", code=200, **kwargs):
                headers = {"Authorization": "Bearer " + tokens[role]} if role in tokens else {}
                started = monotonic()
                response = client.request(method, path, headers=headers, **kwargs)
                check = {"name": name, "status": response.status_code, "expected": code,
                         "passed": response.status_code == code, "seconds": round(monotonic() - started, 2)}
                evidence["checks"].append(check)
                save()
                if not check["passed"]:
                    raise AssertionError(f"{name}: expected HTTP {code}, received {response.status_code}")
                return response

            config = call("demo_config", "GET", "/config.js").text
            if "DEMO: true" not in config or f"SINGLE_SITE_ID: {marker['single_site_id']}" not in config:
                raise ValueError("Server is not the marked one-lot demo")
            for role in ("manager", "staff"):
                user = role + "_demo"
                tokens[role] = call("login_" + role, "POST", "/api/auth/login", role=role,
                    json={"username": user, "password": credentials["accounts"][user]}).json()["access_token"]
                status = call("ai_status_" + role, "GET", prefix + "/ai/status", role=role).json()
                if not status["enabled"] or status["provider"] != "Gemini":
                    raise ValueError("Start the demo with --enable-ai and a configured Gemini key")
            capabilities = call("synthetic_capabilities", "GET", "/api/v2/system/capabilities").json()
            if capabilities.get("showcase_mode") is not True:
                raise ValueError("Live evaluation requires the synthetic-data flag")
            last_day = marker["history_end"]
            cases = [
                ("daily_report", "manager", "report", "day", last_day, ""),
                ("weekly_report", "manager", "report", "week", last_day, ""),
                ("operational_question", "staff", "question", "week", last_day,
                 "Khung giờ nào đông nhất theo lượt vào và theo tổng lượt vào/ra? Hiện tại còn bao nhiêu chỗ?"),
                ("staffing", "staff", "staff", "week", last_day, ""),
                ("empty_week", "manager", "report", "week", marker["empty_period"]["anchor_date"], ""),
            ]
            for name, role, kind, period, anchor, question in cases:
                context = call(name + "_input", "GET", prefix + "/reports/summary", role=role,
                               params={"period": period, "anchor_date": anchor}).json()
                if role == "staff" and (context["data_scope"] != "operations" or context["revenue"] is not None):
                    raise AssertionError("Staff context contains financial data")
                body = {"kind": kind, "period": period, "anchor_date": anchor,
                        "question": question, "request_id": str(uuid4())}
                print(json.dumps({"stage": "provider_request", "case": name}), flush=True)
                result = call(name, "POST", prefix + "/ai/analyses", role=role, code=201, json=body).json()
                if not result.get("content", "").strip() or result["source"] != "database":
                    raise AssertionError("Missing real analysis/provenance")
                database = Path(credentials["database"]).resolve()
                with sqlite3.connect(database.as_uri() + "?mode=ro", uri=True) as connection:
                    saved = connection.execute("SELECT context, content, model FROM site_ai_analyses WHERE id = ?",
                                               (result["id"],)).fetchone()
                if saved is None or saved[1] != result["content"] or saved[2] != result["model"]:
                    raise AssertionError("Analysis is not stored in the marked local database")
                # Use the exact context persisted with this generation. The
                # preceding GET has a different availability observation time.
                context = json.loads(saved[0])
                if role == "staff" and (context["data_scope"] != "operations" or context["revenue"] is not None):
                    raise AssertionError("Saved staff context contains financial data")
                evidence["analyses"].append({"name": name, "role": role, "request": body,
                                             "aggregate_input": context, "response": result})
                save()
                replay = call(name + "_replay", "POST", prefix + "/ai/analyses", role=role,
                              code=201, json=body).json()
                if replay != result:
                    raise AssertionError("Retry returned a different saved analysis")
                detail_path = prefix + "/ai/analyses/" + result["id"]
                detail = call(name + "_history", "GET", detail_path, role=role).json()
                if detail != result:
                    raise AssertionError("Saved history differs from the response")
                if role == "manager":
                    call(name + "_staff_denied", "GET", detail_path, role="staff", code=404)
            call("invalid_question_rejected", "POST", prefix + "/ai/analyses", code=422,
                 json={"kind": "question", "question": "", "request_id": str(uuid4())})
            evidence["result"] = "TRANSPORT_AND_PERSISTENCE_PASS"
            evidence["finished_at"] = datetime.now(timezone.utc).isoformat()
            save()
    except Exception as error:
        evidence["result"] = "FAIL"
        evidence["failure_type"] = type(error).__name__
        # Do not persist exception strings: transport errors can carry headers.
        save()
        raise RuntimeError(f"AI evaluation failed ({type(error).__name__}); see sanitized evidence") from None
    return evidence


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://127.0.0.1:8767")
    parser.add_argument("--credentials", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = verify(args.base_url, args.credentials, args.output)
    print(json.dumps({"result": result["result"], "checks": len(result["checks"]),
                      "analyses": len(result["analyses"]), "semantic_review": result["semantic_review"]}))
