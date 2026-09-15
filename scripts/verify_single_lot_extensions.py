"""P4/P6 HTTP acceptance on an explicitly marked local synthetic database only.

Creates labeled orders, vehicles, receipts and a synthetic video. No bank request,
physical camera, AI provider, credential output or rewriting of stored timestamps.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import time
from urllib.parse import urlsplit
from uuid import uuid4

import httpx
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]


def verify(base_url, credentials_path, artifacts, *, session_payments=False):
    target = urlsplit(base_url)
    if (target.scheme != 'http' or target.hostname not in {'localhost', '127.0.0.1', '::1'}
            or target.username or target.password or target.path not in ('', '/') or target.query or target.fragment):
        raise ValueError('Only a loopback demo origin is accepted')
    credentials = json.loads(credentials_path.read_text(encoding='utf-8'))
    marker = json.loads(Path(credentials['database'] + '.demo.json').read_text(encoding='utf-8'))
    if (credentials.get('profile') != 'single-lot-academic-v1' or marker.get('profile') != credentials['profile']
            or marker.get('synthetic_history') is not True):
        raise ValueError('Requires an explicitly marked single-lot synthetic database')
    artifacts.mkdir(parents=True, exist_ok=True)
    checks, tokens, ids = [], {}, {}
    with httpx.Client(base_url=base_url, timeout=30, follow_redirects=False, trust_env=False) as client:
        advertised = client.get('/config.js')
        if advertised.status_code != 200 or 'DEMO: true' not in advertised.text:
            raise ValueError('Server must advertise the synthetic demo profile')
        if f"SINGLE_SITE_ID: {marker['single_site_id']}" not in advertised.text:
            raise ValueError('Server and local profile do not match')

        def call(name, method, path, *, role='customer', code=200, **kwargs):
            headers = dict(kwargs.pop('headers', {}))
            if role in tokens:
                headers['Authorization'] = 'Bearer ' + tokens[role]
            response = client.request(method, path, headers=headers, **kwargs)
            if response.status_code != code:
                raise AssertionError(f'{name}: expected HTTP {code}, received {response.status_code}')
            checks.append({'check': name, 'status': 'PASS', 'http_status': response.status_code})
            return response

        for role in ('manager', 'staff', 'customer'):
            username = role + '_demo'
            login = call('login_' + role, 'POST', '/api/auth/login', role=role,
                json={'username': username, 'password': credentials['accounts'][username]})
            tokens[role] = login.json()['access_token']
        site = marker['single_site_id']
        prefix = f'/api/v2/sites/{site}'
        kinds = call('staff_reads_vehicle_types', 'GET', '/api/v1/vehicle-types', role='staff').json()
        kind = next(row for row in kinds if row['is_active'])
        initial = call('initial_capacity', 'GET', prefix + '/availability', role='staff').json()
        profile = call('customer_profile', 'GET', '/api/v2/me/profile').json()
        assert profile['linked'] is True
        suffix = uuid4().hex[:8]
        plate = 'UAT' + suffix.upper()
        requested = call('customer_requests_vehicle', 'POST', '/api/v2/me/vehicle-requests',
            json={'license_plate': plate, 'vehicle_type_id': kind['id'], 'note': 'UAT synthetic P4'})
        request_id = requested.json()['id']
        call('staff_cannot_approve_ownership', 'POST', f'/api/v2/portal/admin/vehicle-requests/{request_id}/resolve',
            role='staff', code=403, json={'approve': True})
        call('manager_approves_vehicle', 'POST', f'/api/v2/portal/admin/vehicle-requests/{request_id}/resolve',
            role='manager', json={'approve': True})
        vehicles = call('owned_vehicles', 'GET', '/api/v2/me/vehicles').json()['items']
        vehicle = next(row for row in vehicles if row['license_plate'] == plate)
        plan = call('manager_creates_hourly_plan', 'POST', '/api/v2/portal/admin/plans', role='manager',
            json={'name': 'UAT 1 giờ ' + suffix, 'site_id': site, 'vehicle_type_id': kind['id'],
                  'product_kind': 'hourly', 'duration_minutes': 60, 'price': 12000}).json()
        start = datetime.now(timezone.utc) + timedelta(seconds=8)
        body = {'plan_id': plan['id'], 'vehicle_id': vehicle['id'], 'idempotency_key': 'uat-' + suffix,
                'payment_mode': 'demo', 'start_at': start.isoformat()}
        call('customer_cannot_set_amount', 'POST', '/api/v2/me/orders', code=422, json={**body, 'amount': 1})
        order = call('creates_timed_hold', 'POST', '/api/v2/me/orders', json=body).json()
        assert order['status'] == 'pending' and order['product_kind'] == 'hourly'
        assert order['amount'] == 12000 and order['slot']['id']
        ids.update(order=order['id'], vehicle=vehicle['id'], slot=order['slot']['id'])
        held = call('hold_affects_availability', 'GET', prefix + '/availability', role='staff').json()
        assert held['available_now'] == initial['available_now'] - 1
        call('staff_cannot_simulate_customer_payment', 'POST', f"/api/v2/me/orders/{order['id']}/simulate",
            role='staff', code=409, json={'token': order['demo_token'], 'outcome': 'success'})
        paid = call('demo_payment_fulfills_ticket', 'POST', f"/api/v2/me/orders/{order['id']}/simulate",
            json={'token': order['demo_token'], 'outcome': 'success'}).json()
        assert paid['status'] == 'fulfilled' and paid['entitlement_status'] == 'ready'
        replay = call('purchase_replay_no_second_ticket', 'POST', '/api/v2/me/orders', json=body).json()
        assert replay['timed_pass_id'] == paid['timed_pass_id'] and replay['receipt_id'] == paid['receipt_id']
        receipt = call('customer_downloads_prepaid_receipt', 'GET', f"/api/v2/me/receipts/{paid['receipt_id']}/pdf")
        assert receipt.content.startswith(b'%PDF')
        (artifacts / 'prepaid-receipt.pdf').write_bytes(receipt.content)
        # Real HTTP admission time must reach the purchased window; do not edit DB clocks.
        while datetime.now(timezone.utc) < start:
            time.sleep(0.2)
        admitted = call('staff_admits_prepaid_vehicle', 'POST', prefix + '/check-in', role='staff', code=201,
            json={'license_plate': plate, 'vehicle_type_id': kind['id'], 'parking_slot_id': order['slot']['id']}).json()
        session_id = admitted.get('session_id', admitted.get('id'))
        ids['session'] = session_id
        session_url = prefix + '/sessions/' + session_id
        quote = call('covered_prepaid_checkout_zero', 'GET', session_url + '/checkout-quote', role='staff').json()
        assert quote['parking_fee'] == 0 and quote['billing_basis']['policy_version'] == 'prepaid-window-v1'
        assert quote['prepaid']['order_id'] == order['id'] and quote['prepaid']['amount'] == 12000
        if session_payments:
            balance = call('customer_reads_session_balance', 'GET', f'/api/v2/me/sessions/{session_id}/payment-status').json()
            assert balance['enabled'] is False and balance['can_quote'] is False
            assert (balance['gross_fee'], balance['online_paid'], balance['balance_due']) == (0, 0, 0)
            staff_balance = call('staff_reads_session_balance', 'GET', session_url + '/payment-status', role='staff').json()
            assert staff_balance['session_id'] == session_id and staff_balance['balance_due'] == 0
            call('customer_cannot_use_staff_balance_route', 'GET', session_url + '/payment-status', code=403)
            call('session_quote_cannot_accept_client_price', 'POST', f'/api/v2/me/sessions/{session_id}/payment-quote', code=422,
                json={'request_id': 'fee-' + suffix, 'amount': 1})
            call('payos_fee_quote_disabled_in_demo', 'POST', f'/api/v2/me/sessions/{session_id}/payment-quote', code=503,
                json={'request_id': 'fee-' + suffix})
        confirmation = {'quote_token': quote['quote_token'], 'payment_confirmed': True, 'payment_method': None}
        call('staff_confirms_prepaid_departure', 'PUT', session_url + '/check-out', role='staff', json=confirmation)
        call('prepaid_departure_replay', 'PUT', session_url + '/check-out', role='staff', json=confirmation)
        finished = call('capacity_restored_after_departure', 'GET', prefix + '/availability', role='staff').json()
        assert finished['available_now'] == initial['available_now'] and finished['occupied'] == initial['occupied']
        history = call('customer_sees_own_prepaid_session', 'GET', '/api/v2/me/sessions').json()['items']
        assert next(row for row in history if row['id'] == session_id)['prepaid']['amount'] == 12000
        call('payos_disabled_in_synthetic_demo', 'POST', '/api/v2/me/orders', code=503,
            json={**body, 'idempotency_key': 'bank-' + suffix, 'payment_mode': 'payos'})

        camera = call('manager_creates_uat_camera', 'POST', '/api/v2/cameras', role='manager', code=201,
            json={'site_id': site, 'name': 'UAT synthetic camera ' + suffix, 'retention_hours': 1}).json()
        assert camera['health'] == 'unseen'
        ids['camera'] = camera['id']
        call('staff_cannot_change_camera', 'PATCH', f"/api/v2/cameras/{camera['id']}", role='staff', code=403,
            json={'name': 'Forbidden'})
        token = call('manager_rotates_camera_token', 'POST', f"/api/v2/cameras/{camera['id']}/edge-token", role='manager').json()['token']
        import cv2
        import numpy as np
        video_path = artifacts / 'synthetic-capture.avi'
        writer = cv2.VideoWriter(str(video_path), cv2.VideoWriter_fourcc(*'MJPG'), 10, (320, 180))
        if not writer.isOpened():
            raise RuntimeError('Cannot prepare offline video fixture')
        try:
            for index in range(65):
                frame = np.full((180, 320, 3), 180, dtype=np.uint8)
                cv2.putText(frame, 'UAT SYNTHETIC ' + str(index), (10, 95), cv2.FONT_HERSHEY_SIMPLEX, .55, (30, 30, 30), 1)
                writer.write(frame)
        finally:
            writer.release()
        child_env = os.environ.copy()
        child_env['PARKINGAI_CAMERA_TOKEN'] = token
        captured = subprocess.run([sys.executable, str(ROOT / 'edge/capture_agent.py'), '--video', str(video_path),
            '--api-origin', base_url, '--camera-id', str(camera['id']), '--interval', '3', '--max-events', '2'],
            env=child_env, capture_output=True, text=True, timeout=35)
        child_env.pop('PARKINGAI_CAMERA_TOKEN', None)
        if captured.returncode:
            raise AssertionError('Synthetic edge capture did not complete; inspect sanitized capture output separately')
        events = [json.loads(line) for line in captured.stdout.splitlines() if line.startswith('{')]
        assert len(events) == 2 and events[-1]['accepted'] == 2
        checks.append({'check': 'real_capture_process_video_to_local_edge_http', 'status': 'PASS', 'frames': 2})
        cameras = call('camera_receipt_health', 'GET', '/api/v2/cameras', role='staff', params={'site_id': site}).json()
        assert next(row for row in cameras if row['id'] == camera['id'])['health'] == 'recent'
        observations = call('staff_reads_received_frames', 'GET', '/api/v2/vision/observations', role='staff', params={'site_id': site}).json()
        observed = [row for row in observations if row['camera_id'] == camera['id']]
        assert len(observed) == 2
        observation = observed[0]
        call('customer_cannot_read_camera_frame', 'GET', f"/api/v2/vision/observations/{observation['id']}/image", code=404)
        call('staff_manually_confirms_plate', 'POST', f"/api/v2/vision/observations/{observation['id']}/review", role='staff',
            json={'decision': 'accept', 'license_plate': plate})
        after_review = call('ocr_review_never_admits_vehicle', 'GET', prefix + '/availability', role='staff').json()
        assert after_review['occupied'] == initial['occupied']
        disabled = call('manager_disables_and_revokes_camera', 'DELETE', f"/api/v2/cameras/{camera['id']}", role='manager').json()
        assert disabled['health'] == 'disabled' and disabled['edge_enabled'] is False
        output = io.BytesIO()
        Image.new('RGB', (80, 60), 'white').save(output, 'JPEG')
        call('revoked_edge_token_rejected', 'POST', '/api/v2/vision/edge-events', role=None, code=401,
            headers={'X-Camera-Token': token}, data={'camera_id': camera['id'], 'event_id': str(uuid4())},
            files={'file': ('synthetic.jpg', output.getvalue(), 'image/jpeg')})
    return {'result': 'PASS', 'checked_at': datetime.now(timezone.utc).isoformat(), 'checks': checks,
            'created_ids': ids, 'scope': 'P4 + P6 local HTTP and synthetic video capture',
            'real_money_received': 0, 'physical_camera_tested': False, 'live_ocr_accuracy_measured': False}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--base-url', default='http://127.0.0.1:8768')
    parser.add_argument('--credentials', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--session-payments', action='store_true', help='Also check schema06 fee status and disabled bank payments')
    arguments = parser.parse_args()
    report = verify(arguments.base_url, arguments.credentials, arguments.output.parent, session_payments=arguments.session_payments)
    arguments.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({'result': report['result'], 'checks': len(report['checks']), 'output': str(arguments.output)}))
