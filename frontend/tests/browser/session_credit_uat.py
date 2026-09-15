"""Session credit UI acceptance. Explicit live-disabled versus fully mocked API modes.
Fixture mode intercepts ALL API requests: no real business writes or bank calls.
Live mode permits only local GET/HEAD/OPTIONS and login POST.
"""
import argparse
from datetime import datetime, timedelta, timezone
import base64
import io
import json
from pathlib import Path
import shutil
import subprocess
import time
import urllib.parse
import urllib.request
from uuid import uuid4

import numpy as np
from PIL import Image
from websockets.sync.client import connect

ROOT = Path(__file__).resolve().parents[3]
parser = argparse.ArgumentParser()
parser.add_argument('--origin', default='http://127.0.0.1:8769')
parser.add_argument('--mode', choices=['live-disabled', 'fixture'], required=True)
parser.add_argument('--credentials', type=Path)
args = parser.parse_args()
if args.origin != 'http://127.0.0.1:8769':
    raise ValueError('Dedicated schema06 local UAT origin required')
credentials = None
if args.mode == 'live-disabled':
    if args.credentials is None:
        raise ValueError('Live login requires the isolated demo credentials')
    credentials = json.loads(args.credentials.read_text(encoding='utf-8'))
    if credentials.get('profile') != 'single-lot-academic-v1':
        raise ValueError('Unexpected demo profile')
SITE = 1
RUN = ROOT / 'backend/artifacts/session-credit-browser' / uuid4().hex[:10]
RUN.mkdir(parents=True)
PROFILE = RUN / 'chrome-profile'
checks, requests, http_errors, runtime_errors, blocked_external, ids = [], [], [], [], [], {}
completed = False
role = 'customer'
SID = '11111111-1111-4111-8111-111111111111'
QID = '22222222-2222-4222-8222-222222222222'
instant = datetime.now(timezone(timedelta(hours=7)))
stamp = instant.isoformat()
expiry = (instant + timedelta(minutes=5)).isoformat()
entry = (instant - timedelta(minutes=70)).isoformat()
paid_through = (instant + timedelta(minutes=50)).isoformat()
fixture = dict(enabled=True, gross=10000, paid=0, has_quote=False, link_state='not_created', completed=False)
confirmations = []

def basis():
    return dict(policy_version='entry-v1', rate_source='entry_snapshot', rate_id=1,
        unit_price=5000, ticket_type='HOURLY', effective_date=instant.date().isoformat(),
        billable_from=entry, billable_seconds=4200, billable_blocks=fixture['gross']//5000)

def session():
    return dict(id=SID, session_id=SID, license_plate='UI-CREDIT-DEMO', vehicle_type_id=1,
        slot_name='A-01', zone_name='Khu A', check_in_time=entry,
        check_out_time=stamp if fixture['completed'] else None,
        parking_fee=fixture['gross'] if fixture['completed'] else None,
        status='completed' if fixture['completed'] else 'active', monthly_coverage_end=None,
        prepaid=None, billing_basis=basis() if fixture['completed'] else None,
        online_paid=fixture['paid'], balance_due=fixture['gross']-fixture['paid'])

def proposal():
    return dict(id=QID, session_id=SID, gross_fee=fixture['gross'], online_paid=0,
        balance_due=10000, quoted_at=stamp, paid_through=paid_through, expires_at=expiry,
        server_now=stamp, status='fulfilled' if fixture['link_state']=='paid' else 'pending', billing_basis=basis())

def status():
    return dict(session_id=SID, gross_fee=fixture['gross'], online_paid=fixture['paid'],
        session_status=fixture.get('status_override', 'completed' if fixture['completed'] else 'active'),
        balance_due=fixture['gross']-fixture['paid'], server_now=stamp,
        paid_through=paid_through if fixture['paid'] else None, enabled=fixture['enabled'],
        can_quote=fixture['enabled'] and not fixture['has_quote'],
        latest_quote=proposal() if fixture['has_quote'] else None,
        message='Thanh toán payOS chưa được bật cho bãi này.' if not fixture['enabled'] else 'Số dư kiểm thử mô phỏng, không chuyển tiền.')

def payment_link():
    state = fixture['link_state']
    ready = state=='ready'
    return dict(order_id=None, quote_id=QID, session_id=SID, provider='payos', enabled=True,
        state=state, amount=10000, currency='VND', provider_status='PAID' if state=='paid' else 'PENDING',
        expires_at=expiry, server_now=stamp, paid_through=paid_through,
        checkout_url='https://pay.payos.vn/web/TEST-DO-NOT-PAY' if ready else None,
        qr_code='SYNTHETIC-NOT-A-PAYMENT-CODE' if ready else None,
        qr_svg='<svg xmlns="http://www.w3.org/2000/svg" width="240" height="240"><rect width="240" height="240" fill="white"/><text x="10" y="120">TEST — DO NOT PAY</text></svg>' if ready else None,
        message={'ready':'Mô phỏng QR — không chuyển tiền.', 'unknown':'Chưa xác nhận được kết quả.',
            'paid':'Đã ghi nhận tiền online cho lượt gửi. Nhân viên sẽ xác nhận xe ra.'}.get(state,'Chưa tạo liên kết thanh toán.'),
        can_create=state=='not_created', can_refresh=state in {'ready','unknown'}, can_cancel=state in {'ready','unknown'}, review_reason=None)

def payload(path, method, body):
    if path == '/api/auth/login':
        return {'access_token':'fixture-only-not-an-auth-token','token_type':'bearer'}
    if path == '/api/auth/me':
        return dict(id=2 if role=='staff' else 4, username=role+'_fixture', role=role, is_active=True)
    if path == '/api/v2/system/capabilities':
        return dict(legacy_workspace_allowed=True, site_analytics_enabled=True, site_finance_enabled=True,
            demo_payments_enabled=False, showcase_mode=True)
    if path == '/api/v2/sites':
        return [dict(id=1,name='Bãi kiểm thử giao diện',role=role,is_active=True)]
    if path.endswith('/payment-status'):
        return status()
    if path.endswith('/payment-quote'):
        if set(body) != {'request_id'}:
            raise AssertionError('Client supplied financial values')
        fixture['has_quote']=True
        return proposal()
    if '/session-fee-quotes/' in path:
        if method=='POST' and path.endswith('/payment-link'):
            fixture['link_state']='ready'
        return payment_link()
    if path.endswith('/checkout-quote'):
        return dict(quote_token='fixture-signed-quote-not-valid-on-backend',session_id=SID,
            license_plate='UI-CREDIT-DEMO',check_in_time=entry,quoted_at=stamp,
            expires_at=(instant+timedelta(seconds=120)).isoformat(),duration_minutes=70,
            parking_fee=fixture['gross'],online_paid=fixture['paid'],balance_due=fixture['gross']-fixture['paid'],
            paid_through=paid_through,slot_name='A-01',zone_name='Khu A',billing_basis=basis(),prepaid=None)
    if path.endswith('/check-out'):
        if method!='PUT':
            raise AssertionError('Unexpected checkout method')
        confirmations.append(dict(method=body.get('payment_method'), confirmed=body.get('payment_confirmed'),
            keys=sorted(body), gross=fixture['gross'], paid=fixture['paid'], due=fixture['gross']-fixture['paid']))
        fixture['completed']=True
        return session()
    if path in {'/api/v2/me/sessions','/api/v2/sites/1/sessions'}:
        return [session()] if path.endswith('/me/sessions') or not fixture['completed'] else []
    if path=='/api/v2/me/profile':
        return dict(linked=True,customer=dict(id=1,full_name='Khách mô phỏng',phone_number='0900000000',email=None))
    if path=='/api/v2/me/vehicles':
        return [dict(id=1,license_plate='UI-CREDIT-DEMO',vehicle_type_id=1,type_name='Ô tô',slot_name='A-01')]
    if path=='/api/v2/catalog/vehicle-types':
        return [dict(id=1,name='Ô tô',is_active=True)]
    if path=='/api/v2/sites/1/availability':
        return dict(total=1,capacity_total=1,occupied=1,available=0,inactive_slots=0,zones=[],slots=[])
    if method not in {'GET','HEAD','OPTIONS'}:
        raise AssertionError('Unexpected mocked mutation '+path)
    return []


log = (RUN / "process.log").open("w", encoding="utf-8")
chrome = subprocess.Popen([r"C:\Program Files\Google\Chrome\Application\chrome.exe", "--headless=new", "--disable-gpu",
    "--no-first-run", "--no-default-browser-check", "--disable-background-networking", "--disable-component-update", "--disable-sync",
    "--remote-debugging-port=18989", "--remote-debugging-address=127.0.0.1", "--window-size=1440,1050",
    "--user-data-dir=" + str(PROFILE), "about:blank"], stdout=log, stderr=log, creationflags=subprocess.CREATE_NO_WINDOW)
try:
    for _ in range(50):
        try:
            target = next(row for row in json.load(urllib.request.urlopen("http://127.0.0.1:18989/json", timeout=1)) if row["type"] == "page")
            break
        except (OSError, StopIteration):
            if chrome.poll() is not None:
                raise RuntimeError("Private Chrome exited")
            time.sleep(.2)
    else:
        raise RuntimeError("Private Chrome did not start")
    with connect(target["webSocketDebuggerUrl"], max_size=20_000_000) as ws:
        sequence = 0

        def call(method, params=None):
            global sequence
            sequence += 1
            wanted = sequence
            ws.send(json.dumps({"id": wanted, "method": method, "params": params or {}}))
            while True:
                response = json.loads(ws.recv(timeout=40))
                event = response.get("method")
                if event == "Fetch.requestPaused":
                    paused = response["params"]
                    parsed = urllib.parse.urlsplit(paused["request"]["url"])
                    local = parsed.netloc == '127.0.0.1:8769'
                    mocked = args.mode=='fixture' and local and parsed.path.startswith('/api/')
                    allowed = ((local and (paused['request']['method'] in {'GET','HEAD','OPTIONS'}
                        or (parsed.path=='/api/auth/login' and paused['request']['method']=='POST')))
                        or parsed.scheme in {'data','blob','about'})
                    sequence += 1
                    if mocked:
                        request=paused['request']
                        raw=request.get('postData')
                        body=json.loads(raw) if raw and raw.startswith('{') else {}
                        result=payload(parsed.path,request['method'],body)
                        command=dict(id=sequence,method='Fetch.fulfillRequest',params=dict(requestId=paused['requestId'],responseCode=200,
                            responseHeaders=[dict(name='Content-Type',value='application/json; charset=utf-8')],
                            body=base64.b64encode(json.dumps(result,ensure_ascii=False).encode()).decode()))
                    else:
                        if not allowed:
                            blocked_external.append({'host':parsed.hostname,'scheme':parsed.scheme,'path':parsed.path})
                        command=dict(id=sequence,method='Fetch.continueRequest' if allowed else 'Fetch.failRequest',
                            params={'requestId':paused['requestId'],**({} if allowed else {'errorReason':'BlockedByClient'})})
                    ws.send(json.dumps(command))
                if event == "Network.requestWillBeSent":
                    request = response["params"]["request"]
                    parsed = urllib.parse.urlsplit(request["url"])
                    if parsed.netloc == "127.0.0.1:8769":
                        requests.append({"method": request["method"], "path": parsed.path})
                if event == "Network.responseReceived" and response["params"]["response"]["status"] >= 400:
                    item = response["params"]["response"]
                    http_errors.append({"status": item["status"], "path": urllib.parse.urlsplit(item["url"]).path})
                if event == "Runtime.exceptionThrown":
                    runtime_errors.append({"text": response["params"]["exceptionDetails"]["text"]})
                if response.get("id") == wanted:
                    if "error" in response:
                        raise RuntimeError("Browser command failed")
                    return response.get("result", {})

        def evaluate(expression):
            result = call("Runtime.evaluate", {"expression": expression, "awaitPromise": True, "returnByValue": True})
            if "exceptionDetails" in result:
                raise RuntimeError("Browser evaluation failed; no page payload recorded")
            return result.get("result", {}).get("value")

        def screenshot(name):
            # Never capture the one-time token dialog or a login form with credentials.
            if evaluate("!!document.querySelector('input[type=password]')"):
                return
            evaluate("new Promise(r=>setTimeout(r,350))")
            payload = call("Page.captureScreenshot", {"format": "png", "captureBeyondViewport": False})
            (RUN / (name + ".png")).write_bytes(base64.b64decode(payload["data"]))

        def check(name, expression):
            passed = False
            for _ in range(120):
                if evaluate(expression):
                    passed = True
                    break
                time.sleep(.1)
            checks.append({"name": name, "passed": passed})
            if not passed:
                screenshot("failed-view")
                raise AssertionError(name)

        def helpers():
            evaluate(r"""(()=>{
              window.delay=()=>new Promise(r=>setTimeout(r,120));
              window.main=()=>document.querySelector('main');
              window.dialog=()=>[...document.querySelectorAll('.MuiDialog-root [role=dialog]')].at(-1);
              window.button=(text,scope=document)=>[...scope.querySelectorAll('button')].find(el=>el.textContent.trim()===text);
              window.field=(label,scope=document)=>{const el=[...scope.querySelectorAll('label,[id$="-label"]')].find(el=>el.textContent.replace('*','').trim()===label);return el&&(document.getElementById(el.htmlFor)||[...scope.querySelectorAll('[role=combobox]')].find(input=>input.getAttribute('aria-labelledby')?.split(' ').includes(el.id)));};
              window.input=(label,value)=>{const el=field(label);const proto=el.tagName==='TEXTAREA'?HTMLTextAreaElement.prototype:HTMLInputElement.prototype;Object.getOwnPropertyDescriptor(proto,'value').set.call(el,String(value));el.dispatchEvent(new Event('input',{bubbles:true}));};
              window.choose=async(label,text)=>{field(label).dispatchEvent(new MouseEvent('mousedown',{bubbles:true}));await delay();[...document.querySelectorAll('[role=option]')].find(el=>el.textContent===text||el.textContent.startsWith(text+' ·')).click();await delay();};
              window.pickValue=async(label,value)=>{field(label).dispatchEvent(new MouseEvent('mousedown',{bubbles:true}));await delay();[...document.querySelectorAll('[role=option]')].find(el=>el.getAttribute('data-value')===String(value)).click();await delay();};
              window.api=async(path,body,method='POST')=>{const response=await fetch('/api/v2'+path,{method:body===undefined?'GET':method,headers:{Authorization:'Bearer '+localStorage.getItem('token'),...(body===undefined?{}:{'Content-Type':'application/json'})},body:body===undefined?undefined:JSON.stringify(body)});if(!response.ok)throw Error('Local API failed '+response.status);return response.json();};
              window.rows=data=>Array.isArray(data)?data:data.items;
              window.go=async(path)=>{history.pushState({},'',path);dispatchEvent(new PopStateEvent('popstate'));await delay();};
              window.uploadPattern=async(camera,b64)=>{const data=new FormData();data.append('camera_id',camera);data.append('event_id',crypto.randomUUID());data.append('file',new Blob([Uint8Array.from(atob(b64),c=>c.charCodeAt(0))],{type:'image/png'}),'synthetic-occupancy.png');const r=await fetch('/api/v2/vision/observations',{method:'POST',headers:{Authorization:'Bearer '+localStorage.getItem('token')},body:data});if(!r.ok)throw Error('Synthetic image failed');return r.json();};
              window.scrollTitle=text=>[...document.querySelectorAll('h1,h2,h3,h4,h5,h6')].find(el=>el.textContent===text)?.scrollIntoView({block:'start'});
            })()""")

        def login(role):
            call("Storage.clearDataForOrigin", {"origin": args.origin, "storageTypes": "all"})
            call("Page.navigate", {"url": args.origin + "/login"})
            check(role + " login form", "!!document.querySelector('#username')&&!!document.querySelector('#password')")
            for selector, value in (("#username", role + "_demo"), ("#password", (credentials["accounts"][role + "_demo"] if credentials else "fixture-only"))):
                evaluate("(()=>{const e=document.querySelector(" + json.dumps(selector) + ");Object.getOwnPropertyDescriptor(HTMLInputElement.prototype,'value').set.call(e," + json.dumps(value) + ");e.dispatchEvent(new Event('input',{bubbles:true}));})()")
            evaluate("document.querySelector('button[type=submit]').click()")
            check(role + " login completes", "location.pathname===" + json.dumps("/portal" if role == "customer" else "/sites") + "&&!!document.querySelector('main')")
            helpers()

        def metrics(mobile):
            call("Emulation.setDeviceMetricsOverride", {"width": 390 if mobile else 1440, "height": 844 if mobile else 1050, "deviceScaleFactor": 1, "mobile": mobile})

        call("Network.enable")
        call("Runtime.enable")
        call("Fetch.enable", {"patterns": [{"urlPattern": "*"}]})
        metrics(False)
        role='customer'
        login(role)
        check('customer history tab available', "[...main().querySelectorAll('[role=tab]')].some(e=>e.textContent==='Lịch sử & chứng từ')")
        evaluate("[...main().querySelectorAll('[role=tab]')].find(e=>e.textContent==='Lịch sử & chứng từ').click()")
        check('customer active stay has payment detail action', "!!button('Chi tiết & thanh toán',main())")
        evaluate("button('Chi tiết & thanh toán',main()).click()")
        check('customer fee panel loaded', "!!dialog()?.querySelector('[aria-label=\"Thanh toán phí lượt gửi\"]')&&dialog().textContent.includes('Tổng phí hiện tại:')")
        if args.mode=='live-disabled':
            check('live provider disabled label and no quote creation', "dialog().textContent.includes('chưa được')&&!button('Lập đề nghị thanh toán QR',dialog())&&!dialog().querySelector('img[alt^=QR]')")
            screenshot('live-customer-provider-disabled-desktop')
            metrics(True)
            check('live customer detail fits mobile', 'document.documentElement.scrollWidth<=innerWidth+1')
            screenshot('live-customer-provider-disabled-mobile')
        else:
            check('mock current gross10000 credit0 due10000', "(()=>{const t=dialog().textContent;return /Tổng phí hiện tại:.*10[.,]000/.test(t)&&/Đã trả online:.*0/.test(t)&&/Còn thanh toán: 10[.,]000/.test(t);})()")
            evaluate("button('Lập đề nghị thanh toán QR',dialog()).click()")
            check('mock proposed fee offers QR creation', "!!button('Tạo QR thanh toán',dialog())")
            evaluate("button('Tạo QR thanh toán',dialog()).click()")
            check('mock ready displays test QR', "!!dialog()?.querySelector('img[alt^=QR]')&&dialog().textContent.includes('Mô phỏng QR')")
            screenshot('mock-customer-ready-desktop')
            fixture['link_state']='unknown'
            evaluate("button('Tải lại trạng thái',dialog()).click()")
            check('mock unknown hides QR and external payment link', "dialog().textContent.includes('Chưa xác nhận được kết quả')&&!dialog().querySelector('img[alt^=QR]')&&!dialog().querySelector('a[href*=payos]')")
            screenshot('mock-customer-unknown-desktop')
            fixture['link_state']='paid'; fixture['paid']=10000
            evaluate("button('Tải lại trạng thái',dialog()).click()")
            check('mock paid has no payable QR', "!!button('Cập nhật số còn thu',dialog())&&!dialog().querySelector('img[alt^=QR]')")
            evaluate("button('Cập nhật số còn thu',dialog()).click()")
            check('mock paid updates credit and due to zero', "(()=>{const t=dialog().textContent;return /Đã trả online: 10[.,]000/.test(t)&&/Còn thanh toán: 0/.test(t);})()")
            metrics(True)
            check('mock credited customer detail fits mobile','document.documentElement.scrollWidth<=innerWidth+1')
            screenshot('mock-customer-paid-mobile')
            # The list can still show active while payment-status already knows
            # another operator completed checkout. D is then historical gate
            # collection, never a fresh customer debt or a reason to show QR.
            fixture['paid']=5000; fixture['link_state']='ready'; fixture['status_override']='completed'
            prior_link_reads=sum('/session-fee-quotes/' in request['path'] for request in requests)
            evaluate("button('Cập nhật số dư',dialog()).click()")
            check('mock completed status keeps gross and shows gate collection instead of debt', "(()=>{const t=dialog()?.textContent||'';return /Tổng phí hiện tại:.*10[.,]000/.test(t)&&/Đã trả online:.*5[.,]000/.test(t)&&/Đã thu khi ra: 5[.,]000/.test(t)&&!t.includes('Còn thanh toán:');})()")
            check('mock completed status suppresses pending proposal QR and creation', "!dialog().querySelector('[aria-label=\"Thanh toán chuyển khoản\"]')&&!dialog().querySelector('img[alt^=QR]')&&!button('Lập đề nghị thanh toán QR',dialog())")
            checks.append({'name':'mock completed status does not request pending quote link','passed':prior_link_reads==sum('/session-fee-quotes/' in request['path'] for request in requests)})
            screenshot('mock-customer-completed-stale-list-mobile')
            fixture.pop('status_override'); fixture['paid']=10000; fixture['link_state']='paid'
            metrics(False)
            role='staff'; login(role)
            check('mock staff operational stay available', "!!button('Xem phí / xe ra',main())")
            evaluate("button('Xem phí / xe ra',main()).click()")
            check('mock staff fully credited no cash controls', "!!button('Xác nhận xe ra — không thu thêm',dialog())&&!dialog().querySelector('input[type=radio]')&&!dialog().querySelector('input[type=checkbox]')")
            check('mock staff gross10000 credit10000 due0', "(()=>{const t=dialog().textContent;return /Tổng phí lượt gửi: 10[.,]000/.test(t)&&/Đã trả online: 10[.,]000/.test(t)&&/Số tiền còn thu0 VND/.test(t);})()")
            screenshot('mock-staff-fully-credited-desktop')
            evaluate("button('Xác nhận xe ra — không thu thêm',dialog()).click()")
            check('mock no-extra checkout closed', "!document.querySelector('[aria-labelledby=checkout-title]')")
            checks.append({'name':'mock no-extra confirmation has null payment method','passed':len(confirmations)==1 and confirmations[0]['method'] is None and confirmations[0]['due']==0})
            fixture['completed']=False; fixture['gross']=15000
            login(role)
            check('mock staff second accrued fee stay available', "!!button('Xem phí / xe ra',main())")
            evaluate("button('Xem phí / xe ra',main()).click()")
            check('mock staff accrued fee15000 credit10000 only5000 due', "(()=>{const t=dialog()?.textContent||'';return /Tổng phí lượt gửi: 15[.,]000/.test(t)&&/Đã trả online: 10[.,]000/.test(t)&&/Số tiền còn thu5[.,]000 VND/.test(t);})()")
            evaluate("dialog().querySelector('input[type=radio][value=cash]').click()")
            evaluate("dialog().querySelector('input[type=checkbox]').click()")
            check('mock partial payment requires confirmation only remainder', "!!button('Đã thu tiền — cho xe ra',dialog())&&!button('Đã thu tiền — cho xe ra',dialog()).disabled&&/nhận đủ 5[.,]000 VND/.test(dialog().textContent)")
            metrics(True)
            evaluate("[...dialog().querySelectorAll('p')].find(el=>el.textContent==='Số tiền còn thu').parentElement.scrollIntoView({block:'start'})")
            screenshot('mock-staff-partial-credit-mobile')
            evaluate("button('Đã thu tiền — cho xe ra',dialog()).click()")
            check('mock partial checkout closed', "!document.querySelector('[aria-labelledby=checkout-title]')")
            checks.append({'name':'mock partial confirmation has cash method and due5000','passed':len(confirmations)==2 and confirmations[-1]['method']=='cash' and confirmations[-1]['due']==5000})
        call("Storage.clearDataForOrigin", {"origin": args.origin, "storageTypes": "all"})
        completed = True

finally:
    chrome.terminate()
    try:
        chrome.wait(timeout=5)
    except subprocess.TimeoutExpired:
        chrome.kill(); chrome.wait(timeout=5)
    log.close()
    if PROFILE.resolve().parent == RUN.resolve():
        for _ in range(20):
            try:
                shutil.rmtree(PROFILE)
                break
            except FileNotFoundError:
                break
            except PermissionError:
                time.sleep(.1)
    writes = [request for request in requests if request["method"] not in {"GET", "HEAD", "OPTIONS"}]
    report = {"passed": completed and (args.mode == "fixture" or all(row["path"] == "/api/auth/login" for row in writes)) and all(row["passed"] for row in checks) and not http_errors and not runtime_errors and not blocked_external,
        "scope": "Session fee UI on isolated local8769; no provider/external access",
        "data_source": "mocked_all_API_and_bank_no_real_account_or_money" if args.mode=='fixture' else "real_backend_provider_disabled_read_only_except_login",
        "mock_confirmations": confirmations,
        "checks": checks, "synthetic_ids": ids, "writes": writes, "http_errors": http_errors,
        "runtime_errors": runtime_errors, "blocked_external": blocked_external,
        "private_browser_profile_removed": not PROFILE.exists()}
    (RUN / "result.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"passed": report["passed"], "checks": len(checks), "artifact_directory": str(RUN)}, ensure_ascii=True))
    if completed and not report["passed"]:
        raise AssertionError("Acceptance captured errors; inspect sanitized result")
