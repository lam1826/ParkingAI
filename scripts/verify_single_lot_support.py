"""HTTP acceptance for the public lot page, customer support and receipt refunds.

Runs only against an explicitly marked local synthetic single-lot database.
Creates labeled DEMO/counter orders and refund decisions; no bank request, no
provider, no credential output. Results are written as JSON for the dossier.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import secrets
import sys
from urllib.parse import urlsplit
from uuid import uuid4

import httpx

ROOT = Path(__file__).resolve().parents[1]
FORBIDDEN_PUBLIC_KEYS = {"license_plate", "phone_number", "password_hash", "demo_token", "revenue", "customer_id",
    "user_id", "secret_key", "api_key", "public_profile_updated_by_id"}


def _keys(value, found):
    if isinstance(value, dict):
        for key, item in value.items():
            found.add(key)
            _keys(item, found)
    elif isinstance(value, list):
        for item in value:
            _keys(item, found)


def verify(base_url, credentials_path, output):
    target = urlsplit(base_url)
    if (target.scheme != 'http' or target.hostname not in {'localhost', '127.0.0.1', '::1'}
            or target.username or target.password or target.path not in ('', '/') or target.query or target.fragment):
        raise ValueError('Only a loopback demo origin is accepted')
    credentials = json.loads(credentials_path.read_text(encoding='utf-8'))
    marker = json.loads(Path(credentials['database'] + '.demo.json').read_text(encoding='utf-8'))
    if (credentials.get('profile') != 'single-lot-academic-v1' or marker.get('profile') != credentials['profile']
            or marker.get('synthetic_history') is not True):
        raise ValueError('Requires an explicitly marked single-lot synthetic database')
    output.parent.mkdir(parents=True, exist_ok=True)
    checks, tokens, ids = [], {}, {}
    site = marker['single_site_id']
    with httpx.Client(base_url=base_url, timeout=30, follow_redirects=False, trust_env=False) as client:
        advertised = client.get('/config.js')
        if advertised.status_code != 200 or 'DEMO: true' not in advertised.text:
            raise ValueError('Server must advertise the synthetic demo profile')

        def call(name, method, path, *, role=None, code=200, **kwargs):
            headers = dict(kwargs.pop('headers', {}))
            if role in tokens:
                headers['Authorization'] = 'Bearer ' + tokens[role]
            response = client.request(method, path, headers=headers, **kwargs)
            if response.status_code != code:
                raise AssertionError(f'{name}: expected HTTP {code}, received {response.status_code}: {response.text[:300]}')
            checks.append({'check': name, 'status': 'PASS', 'http_status': response.status_code})
            return response

        # --- 1. anonymous public page and API -------------------------------------------------
        spa = call('anonymous_public_page_html', 'GET', '/gioi-thieu')
        assert '<div id="root"' in spa.text
        profile = call('anonymous_public_profile', 'GET', f'/api/v2/public/sites/{site}').json()
        assert profile['id'] == site and profile['name'] and isinstance(profile['plans'], list)
        found = set()
        _keys(profile, found)
        assert not found & FORBIDDEN_PUBLIC_KEYS, found & FORBIDDEN_PUBLIC_KEYS
        checks.append({'check': 'public_profile_has_no_private_keys', 'status': 'PASS'})
        call('anonymous_cannot_read_operational_sessions', 'GET', f'/api/v2/sites/{site}/sessions', code=401)
        call('anonymous_cannot_edit_public_profile', 'PUT', f'/api/v2/sites/{site}/public-profile', code=401,
            json={'address': 'x'})
        call('anonymous_directory', 'GET', '/api/v2/public/sites')

        for role in ('manager', 'staff', 'customer'):
            username = role + '_demo'
            login = call('login_' + role, 'POST', '/api/auth/login', json={'username': username, 'password': credentials['accounts'][username]})
            tokens[role] = login.json()['access_token']

        # --- 2. manager publishes; staff/customer cannot ---------------------------------------
        body = {'address': 'DEMO - 1 Đường Thử Nghiệm', 'description': 'Bãi đồ án một bãi (dữ liệu giả lập).',
                'opening_hours': '06:00–22:00 hằng ngày', 'contact_phone': '0900000000', 'contact_email': 'demo@example.com',
                'latitude': 10.7769, 'longitude': 106.7009}
        call('staff_cannot_publish_profile', 'PUT', f'/api/v2/sites/{site}/public-profile', role='staff', code=403, json=body)
        call('customer_cannot_publish_profile', 'PUT', f'/api/v2/sites/{site}/public-profile', role='customer', code=403, json=body)
        call('manager_rejects_half_coordinates', 'PUT', f'/api/v2/sites/{site}/public-profile', role='manager', code=422,
            json={**body, 'longitude': None})
        saved = call('manager_publishes_profile', 'PUT', f'/api/v2/sites/{site}/public-profile', role='manager', json=body).json()
        assert saved['can_edit'] is True and saved['location'] == {'latitude': 10.7769, 'longitude': 106.7009}
        public = call('public_reflects_publication', 'GET', f'/api/v2/public/sites/{site}').json()
        assert public['opening_hours'] == body['opening_hours'] and public['contact']['phone'] == '0900000000'
        assert public['profile_updated_at'] is not None
        staff_view = call('staff_reads_editor_read_only', 'GET', f'/api/v2/sites/{site}/public-profile', role='staff').json()
        assert staff_view['can_edit'] is False

        # --- 3. support thread ----------------------------------------------------------------
        suffix = uuid4().hex[:8]
        ticket = call('customer_creates_support_request', 'POST', '/api/v2/me/support-requests', role='customer', code=201,
            json={'subject': 'UAT hỗ trợ ' + suffix, 'category': 'general', 'message': 'Tôi cần hỗ trợ (UAT).'}).json()
        assert ticket['status'] == 'open' and ticket['site_id'] == site
        ids['support'] = ticket['id']
        call('staff_cannot_read_support_queue', 'GET', f'/api/v2/sites/{site}/support-requests', role='staff', code=403)
        queue = call('manager_lists_open_support', 'GET', f'/api/v2/sites/{site}/support-requests', role='manager',
            params={'status': 'open'}).json()['items']
        assert any(row['id'] == ticket['id'] for row in queue)
        answered = call('manager_replies', 'POST', f"/api/v2/sites/{site}/support-requests/{ticket['id']}/messages", role='manager',
            json={'body': 'Đã nhận, đang xử lý (UAT).'}).json()
        assert answered['status'] == 'answered'
        seen = call('customer_reads_reply', 'GET', f"/api/v2/me/support-requests/{ticket['id']}", role='customer').json()
        assert [m['author_role'] for m in seen['messages']] == ['customer', 'manager']
        notices = call('customer_notified_of_reply', 'GET', '/api/v2/me/notifications', role='customer').json()['items']
        assert any('phản hồi' in row['message'] for row in notices)
        closed = call('manager_closes_support', 'POST', f"/api/v2/sites/{site}/support-requests/{ticket['id']}/close", role='manager',
            json={'note': 'Đã giải quyết (UAT).'}).json()
        assert closed['status'] == 'closed'
        call('customer_cannot_reply_closed', 'POST', f"/api/v2/me/support-requests/{ticket['id']}/messages", role='customer',
            code=409, json={'body': 'x'})

        # --- 4. DEMO refund ------------------------------------------------------------------
        plans = call('customer_reads_plans', 'GET', '/api/v2/plans', role='customer').json()['items']
        vehicles = call('customer_reads_vehicles', 'GET', '/api/v2/me/vehicles', role='customer').json()['items']
        monthly = [plan for plan in plans if plan['product_kind'] == 'monthly']
        chosen = None
        for vehicle in vehicles:
            plan = next((row for row in monthly if row['vehicle_type_id'] == vehicle['vehicle_type_id']), None)
            if plan:
                chosen = (vehicle, plan)
                break
        assert chosen, 'Seed must offer a monthly plan for an owned vehicle'
        vehicle, plan = chosen
        order = call('customer_creates_demo_order', 'POST', '/api/v2/me/orders', role='customer',
            json={'plan_id': plan['id'], 'vehicle_id': vehicle['id'], 'idempotency_key': 'uat-demo-' + suffix, 'payment_mode': 'demo'}).json()
        paid = call('customer_simulates_demo_success', 'POST', f"/api/v2/me/orders/{order['id']}/simulate", role='customer',
            json={'token': order['demo_token'], 'outcome': 'success'}).json()
        assert paid['status'] == 'fulfilled' and paid['receipt_id']
        receipts = call('customer_reads_receipts_with_refund_state', 'GET', '/api/v2/me/receipts', role='customer').json()['items']
        receipt = next(row for row in receipts if row['id'] == paid['receipt_id'])
        assert receipt['refund']['eligible'] is True and receipt['refund']['refundable_amount'] == plan['price']
        assert receipt['refund']['payment_channel'] == 'demo'
        call('client_amount_is_rejected', 'POST', f"/api/v2/me/receipts/{paid['receipt_id']}/refund-requests", role='customer',
            code=422, json={'reason': 'x', 'amount': 1})
        request = call('customer_requests_demo_refund', 'POST', f"/api/v2/me/receipts/{paid['receipt_id']}/refund-requests",
            role='customer', code=201, json={'reason': 'UAT hoàn DEMO'}).json()
        assert request['status'] == 'pending' and request['demo'] is True
        replay = call('duplicate_request_returns_same', 'POST', f"/api/v2/me/receipts/{paid['receipt_id']}/refund-requests",
            role='customer', code=201, json={'reason': 'lại'}).json()
        assert replay['id'] == request['id']
        ids['demo_refund'] = request['id']
        url = f"/api/v2/sites/{site}/refund-requests/{request['id']}"
        call('customer_cannot_approve', 'POST', url + '/approve', role='customer', code=403, json={})
        call('staff_cannot_approve', 'POST', url + '/approve', role='staff', code=403, json={})
        call('over_refund_rejected', 'POST', url + '/approve', role='manager', code=409, json={'amount': plan['price'] + 1})
        approved = call('manager_approves_demo_refund', 'POST', url + '/approve', role='manager', json={'note': 'UAT duyệt'}).json()
        assert approved['status'] == 'refunded' and approved['refund_method'] == 'demo' and approved['refund_payment_id']
        again = call('second_approval_is_idempotent', 'POST', url + '/approve', role='manager', json={'note': 'UAT duyệt'}).json()
        assert again['refund_payment_id'] == approved['refund_payment_id']
        call('demo_refund_cannot_be_recorded_twice', 'POST', url + '/record-refund', role='manager', code=409,
            json={'method': 'cash', 'confirmed': True})
        rows = call('customer_sees_demo_refund_receipt', 'GET', '/api/v2/me/receipts', role='customer').json()['items']
        assert any(row['kind'] == 'refund' and row['method'] == 'demo' and row['id'] == approved['refund_payment_id'] for row in rows)
        exhausted = next(row for row in rows if row['id'] == paid['receipt_id'])
        assert exhausted['refund']['blocked_reason'] == 'fully_refunded'

        # --- 5. counter (non-DEMO) refund: approve then record with a reference --------------
        second = call('customer_creates_manual_order', 'POST', '/api/v2/me/orders', role='customer',
            json={'plan_id': plan['id'], 'vehicle_id': vehicle['id'], 'idempotency_key': 'uat-manual-' + suffix, 'payment_mode': 'manual'}).json()
        assert second['status'] == 'pending' and second.get('receipt_id') is None
        call('unpaid_order_has_no_refundable_receipt', 'POST', f"/api/v2/me/orders/{second['id']}/refund-requests", role='customer',
            code=409, json={'reason': 'chưa trả'})
        collected = call('manager_collects_cash', 'POST', f"/api/v2/portal/admin/orders/{second['id']}/collect", role='manager',
            json={'payment_method': 'cash', 'confirmed': True}).json()
        assert collected['status'] == 'fulfilled' and collected['receipt_id']
        counter = call('counter_receipt_is_refundable', 'GET', '/api/v2/me/receipts', role='customer').json()['items']
        counter_receipt = next(row for row in counter if row['id'] == collected['receipt_id'])
        assert counter_receipt['refund']['payment_channel'] == 'counter' and counter_receipt['refund']['eligible'] is True
        request2 = call('customer_requests_counter_refund', 'POST', f"/api/v2/me/receipts/{collected['receipt_id']}/refund-requests",
            role='customer', code=201, json={'reason': 'UAT hoàn tại quầy'}).json()
        ids['counter_refund'] = request2['id']
        url2 = f"/api/v2/sites/{site}/refund-requests/{request2['id']}"
        reviewing = call('manager_starts_review', 'POST', url2 + '/review', role='manager', json={'note': 'Đang đối chiếu'}).json()
        assert reviewing['status'] == 'reviewing'
        half = plan['price'] // 2
        approved2 = call('manager_approves_partial', 'POST', url2 + '/approve', role='manager',
            json={'amount': half, 'note': 'Hoàn phần chưa dùng'}).json()
        assert approved2['status'] == 'approved' and approved2['refund_payment_id'] is None and approved2['approved_amount'] == half
        mine = call('customer_sees_approved_not_yet_refunded', 'GET', '/api/v2/me/refund-requests', role='customer').json()['items']
        assert next(row for row in mine if row['id'] == request2['id'])['status'] == 'approved'
        call('transfer_record_needs_reference', 'POST', url2 + '/record-refund', role='manager', code=422,
            json={'method': 'transfer', 'confirmed': True})
        call('record_needs_confirmation', 'POST', url2 + '/record-refund', role='manager', code=422,
            json={'method': 'transfer', 'external_reference': 'UAT-FT-' + suffix, 'confirmed': False})
        recorded = call('manager_records_external_refund', 'POST', url2 + '/record-refund', role='manager',
            json={'method': 'transfer', 'external_reference': 'UAT-FT-' + suffix, 'confirmed': True}).json()
        assert recorded['status'] == 'refunded' and recorded['approved_amount'] == half and recorded['external_reference'] == 'UAT-FT-' + suffix
        replay2 = call('record_replay_is_idempotent', 'POST', url2 + '/record-refund', role='manager',
            json={'method': 'transfer', 'external_reference': 'UAT-FT-' + suffix, 'confirmed': True}).json()
        assert replay2['refund_payment_id'] == recorded['refund_payment_id']
        ledger = call('customer_sees_transfer_refund_receipt', 'GET', '/api/v2/me/receipts', role='customer').json()['items']
        refund_row = next(row for row in ledger if row['id'] == recorded['refund_payment_id'])
        assert refund_row['kind'] == 'refund' and refund_row['method'] == 'transfer' and refund_row['amount'] == half
        finance = call('manager_reads_site_finance_ledger', 'GET', f'/api/v2/sites/{site}/payments', role='manager',
            params={'limit': 100}).json()
        finance_rows = finance if isinstance(finance, list) else finance.get('items', [])
        assert any(row['id'] == recorded['refund_payment_id'] for row in finance_rows), 'refund must appear in the site ledger'
        listed = call('manager_lists_refunded', 'GET', f'/api/v2/sites/{site}/refund-requests', role='manager',
            params={'status': 'refunded'}).json()['items']
        assert {request['id'], request2['id']} <= {row['id'] for row in listed}

        # --- 6. cross-account isolation --------------------------------------------------------
        stranger = 'uat_' + suffix
        password = 'Uat-' + secrets.token_urlsafe(12)
        call('register_second_customer', 'POST', '/api/auth/register', code=201,
            json={'username': stranger, 'full_name': 'Khách UAT khác', 'password': password, 'role': 'customer', 'registration_code': None})
        tokens['stranger'] = call('login_second_customer', 'POST', '/api/auth/login', json={'username': stranger, 'password': password}).json()['access_token']
        call('second_customer_creates_profile', 'POST', '/api/v2/me/profile', role='stranger',
            json={'full_name': 'Khách UAT khác', 'phone_number': '09' + suffix[:8].encode().hex()[:8]})
        call('stranger_cannot_read_support', 'GET', f"/api/v2/me/support-requests/{ticket['id']}", role='stranger', code=404)
        call('stranger_cannot_request_refund_on_foreign_receipt', 'POST', f"/api/v2/me/receipts/{collected['receipt_id']}/refund-requests",
            role='stranger', code=404, json={'reason': 'hack'})
        call('stranger_cannot_link_foreign_order', 'POST', '/api/v2/me/support-requests', role='stranger', code=404,
            json={'subject': 'Gắn đơn người khác', 'message': 'x', 'linked_type': 'order', 'linked_id': order['id']})
        assert call('stranger_refund_list_is_empty', 'GET', '/api/v2/me/refund-requests', role='stranger').json()['items'] == []
    output.write_text(json.dumps({'base_url': base_url, 'site_id': site, 'checks': checks, 'passed': len(checks),
        'ids': ids, 'note': 'Synthetic single-lot database; DEMO and counter money only, no bank transfer.'},
        ensure_ascii=False, indent=2), encoding='utf-8')
    return checks


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--base-url', default='http://127.0.0.1:8771')
    parser.add_argument('--credentials', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    checks = verify(args.base_url, args.credentials, args.output)
    print(f'PASS {len(checks)} checks -> {args.output}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
