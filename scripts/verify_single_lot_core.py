"""Exercise the core against a running, explicitly marked local demo server.

Creates labelled UAT records in that isolated database; never contacts a
provider. Credentials are read locally and excluded from the evidence report.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import secrets
from urllib.parse import urlparse
from uuid import uuid4

import httpx


def verify(base_url, credentials_path):
    parsed = urlparse(base_url)
    if parsed.scheme != "http" or parsed.hostname not in {"127.0.0.1", "localhost", "::1"} or parsed.username or parsed.password:
        raise ValueError("Only an HTTP loopback demo server is accepted")
    credentials = json.loads(credentials_path.read_text(encoding="utf-8"))
    if credentials.get("profile") != "single-lot-academic-v1":
        raise ValueError("Credentials must belong to the isolated single-lot profile")
    marker = json.loads(Path(credentials["database"] + ".demo.json").read_text(encoding="utf-8"))
    if marker.get("profile") != credentials["profile"] or not marker.get("synthetic_history"):
        raise ValueError("Missing synthetic single-lot marker")
    checks = []
    tokens = {}
    with httpx.Client(base_url=base_url, timeout=30, follow_redirects=False) as client:
        config = client.get("/config.js")
        if (config.status_code != 200 or "DEMO: true" not in config.text
                or f"SINGLE_SITE_ID: {marker['single_site_id']}" not in config.text):
            raise ValueError("Server must advertise the single-lot demo frontend")

        def call(name, method, path, role="staff", code=200, **kwargs):
            headers = {"Authorization": "Bearer " + tokens[role]} if role in tokens else {}
            response = client.request(method, path, headers=headers, **kwargs)
            if response.status_code != code:
                raise AssertionError(f"{name}: expected HTTP {code}, received {response.status_code}")
            checks.append({"check": name, "status": "PASS", "http_status": response.status_code})
            return response

        for role in ("manager", "staff", "customer"):
            user = role + "_demo"
            response = call(f"login_{role}", "POST", "/api/auth/login", role=role,
                            json={"username": user, "password": credentials["accounts"][user]})
            tokens[role] = response.json()["access_token"]
        sites = call("exactly_one_site", "GET", "/api/v2/sites").json()
        assert len(sites) == 1 and sites[0]["id"] == marker["single_site_id"]
        prefix = f"/api/v2/sites/{sites[0]['id']}"
        capabilities = call("staff_single_lot_capability", "GET", "/api/v2/system/capabilities").json()
        assert capabilities["legacy_workspace_allowed"] and capabilities["showcase_mode"]
        for collection in ("vehicle-types", "price-configs", "zones", "parking-slots", "customers", "monthly-passes"):
            call("staff_read_" + collection, "GET", "/api/v1/" + collection)
        call("customer_core_denied", "GET", prefix + "/reports/summary", role="customer", code=403)
        initial = call("initial_availability", "GET", prefix + "/availability").json()
        assert initial["total"] >= 36  # Four reserve positions are inactive.
        suffix = uuid4().hex[:8]
        roles = call("manager_read_roles", "GET", "/api/v1/roles", role="manager").json()
        role_ids = {row["name"]: row["id"] for row in roles}
        new_password = secrets.token_urlsafe(20)
        user_payload = {"username": "uat_staff_" + suffix, "full_name": "UAT Staff " + suffix,
                        "role_id": role_ids["staff"], "password": new_password, "is_active": True}
        call("manager_cannot_create_admin", "POST", "/api/v1/users", role="manager", code=403,
            json={**user_payload, "role_id": role_ids["admin"]})
        new_user = call("manager_creates_staff", "POST", "/api/v1/users", role="manager", code=201, json=user_payload).json()
        tokens["new_staff"] = call("new_staff_login", "POST", "/api/auth/login", role="new_staff",
            json={"username": user_payload["username"], "password": new_password}).json()["access_token"]
        new_sites = call("new_staff_has_site_membership", "GET", "/api/v2/sites", role="new_staff").json()
        assert [row["id"] for row in new_sites] == [sites[0]["id"]]
        call("manager_cannot_promote_staff", "PUT", f"/api/v1/users/{new_user['id']}", role="manager", code=403,
            json={"role_id": role_ids["manager"]})
        call("manager_locks_staff", "PUT", f"/api/v1/users/{new_user['id']}", role="manager", json={"is_active": False})
        call("locked_staff_token_rejected", "GET", "/api/v2/sites", role="new_staff", code=401)
        vehicle_type = call("manager_create_type", "POST", "/api/v1/vehicle-types", role="manager", code=201,
            json={"name": "UAT " + suffix, "description": "Synthetic core journey"}).json()
        price_payload = {"vehicle_type_id": vehicle_type["id"], "ticket_type": "HOURLY", "price": 5000,
                         "effective_date": "2020-01-01", "is_active": True}
        call("staff_price_write_denied", "POST", "/api/v1/price-configs", code=403, json=price_payload)
        price = call("manager_create_price", "POST", "/api/v1/price-configs", role="manager", code=201, json=price_payload).json()
        zone_payload = {"name": "UAT " + suffix, "capacity": 1, "is_active": True}
        call("staff_zone_write_denied", "POST", prefix + "/zones", code=403, json=zone_payload)
        zone = call("manager_create_zone", "POST", prefix + "/zones", role="manager", code=201, json=zone_payload).json()
        slot = call("manager_create_slot", "POST", prefix + "/slots", role="manager", code=201,
            json={"slot_name": "UAT-" + suffix, "zone_id": zone["id"], "vehicle_type_id": vehicle_type["id"], "is_active": True}).json()
        plate = "UAT" + suffix.upper()
        admission = {"license_plate": plate, "vehicle_type_id": vehicle_type["id"], "parking_slot_id": slot["id"]}
        session = call("staff_check_in", "POST", prefix + "/check-in", code=201, json=admission).json()
        session_id = session.get("session_id", session.get("id"))
        assert session_id
        call("duplicate_admission_rejected", "POST", prefix + "/check-in", code=400, json=admission)
        call("occupied_type_cannot_be_disabled", "PUT", f"/api/v1/vehicle-types/{vehicle_type['id']}", role="manager", code=409, json={"is_active": False})
        call("occupied_slot_cannot_be_disabled", "PUT", f"/api/v1/parking-slots/{slot['id']}", role="manager", code=409, json={"is_active": False})
        call("entry_snapshot_allows_future_price_edit", "PUT", f"/api/v1/price-configs/{price['id']}", role="manager", json={"price": 9000})
        occupied = call("availability_after_admission", "GET", prefix + "/availability").json()
        assert occupied["occupied"] == initial["occupied"] + 1
        session_url = prefix + f"/sessions/{session_id}"
        quote = call("quote_before_collecting", "GET", session_url + "/checkout-quote").json()
        assert quote["parking_fee"] in {0, 5000}
        assert quote["billing_basis"]["rate_source"] == "entry_snapshot"
        assert quote["billing_basis"]["unit_price"] == 5000
        confirmation = {"quote_token": quote["quote_token"], "payment_confirmed": True,
                        "payment_method": "cash" if quote["parking_fee"] else None}
        call("staff_checkout", "PUT", session_url + "/check-out", json=confirmation)
        call("checkout_replay", "PUT", session_url + "/check-out", json=confirmation)
        after = call("slot_released", "GET", prefix + "/availability").json()
        assert after["occupied"] == initial["occupied"]
        today = datetime.now(timezone(timedelta(hours=7))).date()
        found = call("search_plate_and_dates", "GET", prefix + "/sessions",
            params={"license_plate": plate, "date_from": str(today), "date_to": str(today)}).json()
        assert any(item["id"] == session_id for item in found)
        saved = next(item for item in found if item["id"] == session_id)
        assert saved["billing_basis"]["unit_price"] == 5000
        exact = call("search_exact_ticket_id", "GET", prefix + "/sessions",
                     params={"session_id": session_id, "license_plate": plate, "status": "completed"}).json()
        assert len(exact) == 1 and exact[0]["id"] == session_id
        assert call("ticket_prefix_is_not_a_match", "GET", prefix + "/sessions",
                    params={"session_id": session_id[:-1]}).json() == []
        # A new admission uses the edited tariff. Manager lost-ticket approval
        # adds evidence, then staff follows the ordinary confirmed checkout.
        lost = call("new_admission_uses_new_tariff", "POST", prefix + "/check-in", code=201, json=admission).json()
        lost_id = lost.get("session_id", lost.get("id"))
        lost_url = prefix + f"/sessions/{lost_id}"
        exception_body = {"reason": "UAT synthetic lost ticket verified by manager", "request_id": str(uuid4())}
        call("staff_cannot_approve_lost_ticket", "POST", lost_url + "/lost-ticket", code=403, json=exception_body)
        loss = call("manager_approves_lost_ticket", "POST", lost_url + "/lost-ticket", role="manager", json=exception_body).json()
        replay = call("lost_ticket_replay", "POST", lost_url + "/lost-ticket", role="manager", json=exception_body).json()
        assert replay["event"]["id"] == loss["event"]["id"]
        loss_quote = call("lost_ticket_fee_has_no_automatic_penalty", "GET", lost_url + "/checkout-quote").json()
        assert loss_quote["billing_basis"]["unit_price"] == 9000 and loss_quote["parking_fee"] in {0, 9000}
        call("lost_ticket_normal_checkout", "PUT", lost_url + "/check-out", json={
            "quote_token": loss_quote["quote_token"], "payment_confirmed": True,
            "payment_method": "cash" if loss_quote["parking_fee"] else None})
        mistaken = call("mistaken_admission", "POST", prefix + "/check-in", code=201, json=admission).json()
        mistaken_id = mistaken.get("session_id", mistaken.get("id"))
        mistaken_url = prefix + f"/sessions/{mistaken_id}"
        cancel_body = {"reason": "UAT synthetic mistaken admission", "request_id": str(uuid4())}
        call("staff_cannot_cancel", "POST", mistaken_url + "/cancel", code=403, json=cancel_body)
        cancelled = call("manager_cancels_and_preserves_history", "POST", mistaken_url + "/cancel", role="manager", json=cancel_body).json()
        assert cancelled["status"] == "cancelled"
        repeat = call("cancel_replay", "POST", mistaken_url + "/cancel", role="manager", json=cancel_body).json()
        assert repeat["event"]["id"] == cancelled["event"]["id"]
        call("cancelled_admission_cannot_exit", "GET", mistaken_url + "/checkout-quote", code=409)
        assert call("cancel_releases_slot", "GET", prefix + "/availability").json()["occupied"] == initial["occupied"]
        correction = call("admission_for_plate_correction", "POST", prefix + "/check-in", code=201, json=admission).json()
        correction_id = correction.get("session_id", correction.get("id"))
        correction_url = prefix + f"/sessions/{correction_id}"
        call("tariff_changes_before_correction", "PUT", f"/api/v1/price-configs/{price['id']}", role="manager", json={"price": 12000})
        correction_body = {"license_plate": "FIX" + suffix.upper(), "reason": "UAT synthetic plate correction",
                           "request_id": str(uuid4())}
        call("staff_cannot_correct_plate", "POST", correction_url + "/correct-plate", code=403, json=correction_body)
        corrected = call("manager_replaces_mistaken_plate", "POST", correction_url + "/correct-plate", role="manager", json=correction_body).json()
        assert corrected["status"] == "cancelled" and corrected["replacement_session_id"]
        repeated = call("plate_correction_replay", "POST", correction_url + "/correct-plate", role="manager", json=correction_body).json()
        assert repeated["replacement_session_id"] == corrected["replacement_session_id"]
        replacement_url = prefix + f"/sessions/{corrected['replacement_session_id']}"
        corrected_quote = call("replacement_keeps_original_tariff", "GET", replacement_url + "/checkout-quote").json()
        assert corrected_quote["billing_basis"]["unit_price"] == 9000
        assert corrected_quote["license_plate"] == correction_body["license_plate"]
        call("replacement_can_depart_normally", "PUT", replacement_url + "/check-out", json={
            "quote_token": corrected_quote["quote_token"], "payment_confirmed": True,
            "payment_method": "cash" if corrected_quote["parking_fee"] else None})
        operational = call("staff_operational_report", "GET", prefix + "/reports/summary").json()
        assert operational["data_scope"] == "operations" and operational["revenue"] is None
        financial = call("manager_financial_report", "GET", prefix + "/reports/summary", role="manager").json()
        assert financial["data_scope"] == "management" and financial["revenue"] is not None
        assert financial["total_movements"] == financial["total_arrivals"] + financial["total_departures"]
        call("staff_legacy_finance_denied", "GET", "/reports/revenue", code=403)
        call("staff_legacy_statistics_denied", "GET", "/parking/statistics", code=403)
        for role in ("manager", "staff"):
            exported = call(role + "_exports_authorized_csv", "GET", prefix + "/reports/export", role=role,
                            params={"period": "week", "anchor_date": str(today)})
            assert exported.content.startswith(b"\xef\xbb\xbf")
            csv_text = exported.content.decode("utf-8-sig")
            assert ("Tài chính," in csv_text) == (role == "manager")
        customer = call("staff_create_customer", "POST", "/api/v1/customers", code=201,
            json={"full_name": "UAT " + suffix, "phone_number": "UAT" + suffix}).json()
        vehicle = call("staff_register_customer_vehicle", "POST", "/api/v1/vehicles", code=201,
            json={"license_plate": "M" + plate, "vehicle_type_id": vehicle_type["id"], "customer_id": customer["id"]}).json()
        monthly_payload = {"customer_id": customer["id"], "vehicle_id": vehicle["id"], "pass_code": "UAT" + suffix,
                           "start_date": str(today), "end_date": str(today + timedelta(days=29)), "price": 0}
        call("staff_monthly_issue_denied", "POST", "/api/v1/monthly-passes", code=403, json=monthly_payload)
        call("manager_monthly_issue", "POST", "/api/v1/monthly-passes", role="manager", code=201, json=monthly_payload)
        monthly_session = call("monthly_vehicle_admission", "POST", prefix + "/check-in", code=201,
            json={**admission, "license_plate": vehicle["license_plate"]}).json()
        monthly_id = monthly_session.get("session_id", monthly_session.get("id"))
        monthly_url = prefix + f"/sessions/{monthly_id}"
        free_quote = call("monthly_covered_fee_zero", "GET", monthly_url + "/checkout-quote").json()
        assert free_quote["parking_fee"] == 0
        free_confirmation = {"quote_token": free_quote["quote_token"], "payment_confirmed": True, "payment_method": None}
        call("monthly_checkout", "PUT", monthly_url + "/check-out", json=free_confirmation)
        call("monthly_free_checkout_replay", "PUT", monthly_url + "/check-out", json=free_confirmation)
        call("manager_disables_unused_type", "PUT", f"/api/v1/vehicle-types/{vehicle_type['id']}", role="manager", json={"is_active": False})
        call("disabled_type_cannot_admit", "POST", prefix + "/check-in", code=409, json=admission)
        call("manager_reactivates_type", "PUT", f"/api/v1/vehicle-types/{vehicle_type['id']}", role="manager", json={"is_active": True})
        ai_status = call("ai_status_explicit", "GET", prefix + "/ai/status").json()
        assert not ai_status["enabled"]
        call("disabled_ai_no_fake_output", "POST", prefix + "/ai/analyses", code=503,
            json={"kind": "report", "request_id": str(uuid4())})
        call("reports_still_work_when_ai_disabled", "GET", prefix + "/reports/summary")
    return {"checked_at": datetime.now(timezone.utc).isoformat(), "result": "PASS", "checks": checks,
            "scope": "HTTP on isolated synthetic single-lot DB; no provider or real payment",
            "live_ai_verified": False, "real_money_received": 0, "new_paid_stay_fee": quote["parking_fee"]}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://127.0.0.1:8766")
    parser.add_argument("--credentials", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = verify(args.base_url, args.credentials)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"result": result["result"], "checks": len(result["checks"]), "output": str(args.output)}))
