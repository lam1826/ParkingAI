"""Opt-in real-provider acceptance against the marked local academic database.
No secrets enter the report. Successful text still needs human/source review.
"""
import argparse
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from time import monotonic
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from uuid import uuid4

parser = argparse.ArgumentParser()
parser.add_argument('--credentials', type=Path, required=True)
parser.add_argument('--output', type=Path, required=True)
parser.add_argument('--cases', nargs='+', choices=[
    'daily_report', 'weekly_report', 'management_question', 'staffing',
    'empty_period', 'customer_public_question',
], help='Optional bounded subset for an explicit follow-up; keep the original evidence.')
args = parser.parse_args()
if args.output.exists():
    raise ValueError('Output already exists; use a new filename to preserve evidence')
credentials = json.loads(args.credentials.read_text(encoding='utf-8'))
marker = json.loads(Path(credentials['database'] + '.demo.json').read_text(encoding='utf-8'))
if credentials.get('profile') != 'single-lot-academic-v1' or marker.get('synthetic_history') is not True:
    raise ValueError('Only the marked synthetic one-lot database is permitted')
site = marker['single_site_id']
origin = 'http://127.0.0.1:8793'

def request(path, payload=None, token=None):
    headers = {'Content-Type': 'application/json'}
    if token:
        headers['Authorization'] = 'Bearer ' + token
    req = Request(origin + path, data=None if payload is None else json.dumps(payload).encode(), headers=headers)
    try:
        with urlopen(req, timeout=105) as response:
            return response.status, json.load(response)
    except HTTPError as error:
        raw = error.read()
        try:
            body = json.loads(raw)
        except (ValueError, UnicodeDecodeError):
            body = {'detail': 'Non-JSON response; body omitted'}
        return error.code, body
    except (URLError, TimeoutError) as error:
        return 0, {'detail': type(error).__name__}

def login(role):
    name = role + '_demo'
    code, body = request('/api/auth/login', {'username': name, 'password': credentials['accounts'][name]})
    if code != 200:
        raise RuntimeError('Synthetic login failed; private response omitted')
    return body['access_token']

manager = login('manager')
prefix = f'/api/v2/sites/{site}'
status, config = request(prefix + '/ai/status', token=manager)
report = {'origin': origin, 'synthetic_only': True, 'mocked': False, 'provider_status_http': status,
          'provider_status': config, 'cases': [], 'semantic_review': 'PENDING', 'complete': False}
args.output.parent.mkdir(parents=True, exist_ok=True)

def save():
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')

save()
today = datetime.now(timezone(timedelta(hours=7))).date().isoformat()
for label, kind, period, anchor, question in [
    ('daily_report', 'report', 'day', today, ''),
    ('weekly_report', 'report', 'week', today, ''),
    ('management_question', 'question', 'week', today, 'Trong kỳ có bao nhiêu lượt xe vào, giờ nào cao điểm? Hiện còn bao nhiêu chỗ?'),
    ('staffing', 'staff', 'week', today, ''),
    ('empty_period', 'report', 'day', '1900-01-01', ''),
]:
    if args.cases and label not in args.cases:
        continue
    payload = {'kind': kind, 'period': period, 'anchor_date': anchor, 'question': question, 'request_id': str(uuid4())}
    start = monotonic()
    code, body = request(prefix + '/ai/analyses', payload, manager)
    report['cases'].append({'case': label, 'http': code, 'elapsed_seconds': round(monotonic()-start, 2),
                            'request': payload, 'response': body,
                            'status': 'NEEDS_SEMANTIC_REVIEW' if code == 201 else 'FAIL'})
    save()
    print(label + ': HTTP ' + str(code), flush=True)
if not args.cases or 'customer_public_question' in args.cases:
    customer = login('customer')
    profile_http, profile = request(f'/api/v2/public/sites/{site}')
    availability_http, availability = request(prefix + '/availability', token=manager)
    start = monotonic()
    code, body = request(f'/api/v2/public/sites/{site}/assistant', {'question': 'Bãi hiện còn bao nhiêu chỗ? Giá gửi xe máy tính thế nào?'}, customer)
    report['cases'].append({'case': 'customer_public_question', 'http': code, 'elapsed_seconds': round(monotonic()-start, 2),
                            'response': body, 'status': 'NEEDS_SEMANTIC_REVIEW' if code == 200 else 'FAIL',
                            'reference_before_request': {'profile_http': profile_http, 'profile': profile,
                                'availability_http': availability_http, 'availability': availability},
                            'reference_note': 'Captured before generation; concurrent changes may require semantic review.'})
    print('customer_public_question: HTTP ' + str(code), flush=True)
report['complete'] = True
save()
print('Evidence: ' + str(args.output), flush=True)
raise SystemExit(1 if any(case['status'] == 'FAIL' for case in report['cases']) else 0)
