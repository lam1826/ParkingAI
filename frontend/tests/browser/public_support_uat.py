"""Browser acceptance for the public lot page, login continuation, support and refunds.

Drives a private headless Chrome over CDP against the isolated single-lot
synthetic server only. Every network request is inspected: external hosts are
blocked, and business writes are allowed solely to that loopback origin whose
database is explicitly marked synthetic. Screenshots never include a password
field. Money in this database is DEMO/counter fixture money.
"""
import argparse
import base64
import json
from pathlib import Path
import subprocess
import time
import urllib.parse
import urllib.request
from uuid import uuid4

from websockets.sync.client import connect

ROOT = Path(__file__).resolve().parents[3]
parser = argparse.ArgumentParser()
parser.add_argument('--origin', default='http://127.0.0.1:8771')
parser.add_argument('--credentials', type=Path, required=True)
parser.add_argument('--site', type=int, default=1)
args = parser.parse_args()
target = urllib.parse.urlsplit(args.origin)
if target.scheme != 'http' or target.hostname not in {'127.0.0.1', 'localhost'} or target.path:
    raise ValueError('Loopback synthetic origin required')
credentials = json.loads(args.credentials.read_text(encoding='utf-8'))
marker = json.loads(Path(credentials['database'] + '.demo.json').read_text(encoding='utf-8'))
if credentials.get('profile') != 'single-lot-academic-v1' or marker.get('synthetic_history') is not True:
    raise ValueError('Requires the explicitly marked single-lot synthetic database')
ORIGIN_NETLOC = target.netloc
RUN = ROOT / 'backend/artifacts/public-support-browser' / uuid4().hex[:10]
RUN.mkdir(parents=True)
PROFILE = RUN / 'chrome-profile'
checks, requests, mutations, http_errors, runtime_errors, blocked_external = [], [], [], [], [], []
fail_public_once = {'armed': False, 'empty': False}
suffix = uuid4().hex[:6]

log = (RUN / 'process.log').open('w', encoding='utf-8')
chrome = subprocess.Popen([r"C:\Program Files\Google\Chrome\Application\chrome.exe", "--headless=new", "--disable-gpu",
    "--no-first-run", "--no-default-browser-check", "--disable-background-networking", "--disable-component-update", "--disable-sync",
    "--remote-debugging-port=18991", "--remote-debugging-address=127.0.0.1", "--window-size=1440,1050",
    "--user-data-dir=" + str(PROFILE), "about:blank"], stdout=log, stderr=log, creationflags=subprocess.CREATE_NO_WINDOW)
completed = False
try:
    for _ in range(50):
        try:
            page = next(row for row in json.load(urllib.request.urlopen("http://127.0.0.1:18991/json", timeout=1)) if row["type"] == "page")
            break
        except (OSError, StopIteration):
            if chrome.poll() is not None:
                raise RuntimeError("Private Chrome exited")
            time.sleep(.2)
    else:
        raise RuntimeError("Private Chrome did not start")
    with connect(page["webSocketDebuggerUrl"], max_size=20_000_000) as ws:
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
                    request = paused["request"]
                    parsed = urllib.parse.urlsplit(request["url"])
                    local = parsed.netloc == ORIGIN_NETLOC
                    allowed = local or parsed.scheme in {"data", "blob", "about"}
                    sequence += 1
                    public_profile = local and parsed.path == f"/api/v2/public/sites/{args.site}"
                    if public_profile and fail_public_once['armed']:
                        fail_public_once['armed'] = False
                        command = dict(id=sequence, method="Fetch.failRequest", params={"requestId": paused["requestId"], "errorReason": "ConnectionFailed"})
                    elif public_profile and fail_public_once['empty']:
                        fail_public_once['empty'] = False
                        body = dict(id=args.site, name="Bãi rỗng (mô phỏng)", address=None, description=None, opening_hours=None,
                            contact=dict(phone=None, email=None), location=None, profile_updated_at=None, demo_labeled=True,
                            vehicle_types=[], plans=[], walk_in_rates=[], capacity=dict(zones=0, slots=0), payment_modes=[], booking_mode="legacy")
                        command = dict(id=sequence, method="Fetch.fulfillRequest", params=dict(requestId=paused["requestId"], responseCode=200,
                            responseHeaders=[dict(name="Content-Type", value="application/json; charset=utf-8")],
                            body=base64.b64encode(json.dumps(body, ensure_ascii=False).encode()).decode()))
                    else:
                        if not allowed:
                            blocked_external.append({"host": parsed.hostname, "scheme": parsed.scheme, "path": parsed.path})
                        if local and request["method"] not in {"GET", "HEAD", "OPTIONS"}:
                            mutations.append({"method": request["method"], "path": parsed.path})
                        command = dict(id=sequence, method="Fetch.continueRequest" if allowed else "Fetch.failRequest",
                            params={"requestId": paused["requestId"], **({} if allowed else {"errorReason": "BlockedByClient"})})
                    ws.send(json.dumps(command))
                if event == "Network.requestWillBeSent":
                    request = response["params"]["request"]
                    parsed = urllib.parse.urlsplit(request["url"])
                    if parsed.netloc == ORIGIN_NETLOC:
                        requests.append({"method": request["method"], "path": parsed.path})
                if event == "Network.responseReceived" and response["params"]["response"]["status"] >= 400:
                    item = response["params"]["response"]
                    http_errors.append({"status": item["status"], "path": urllib.parse.urlsplit(item["url"]).path})
                if event == "Runtime.exceptionThrown":
                    runtime_errors.append({"text": response["params"]["exceptionDetails"]["text"]})
                if response.get("id") == wanted:
                    if "error" in response:
                        raise RuntimeError("Browser command failed: " + method)
                    return response.get("result", {})

        def evaluate(expression):
            result = call("Runtime.evaluate", {"expression": expression, "awaitPromise": True, "returnByValue": True})
            if "exceptionDetails" in result:
                raise RuntimeError("Browser evaluation failed: " + json.dumps(result["exceptionDetails"].get("exception", {}).get("description", ""))[:300])
            return result.get("result", {}).get("value")

        def screenshot(name):
            if evaluate("!!document.querySelector('input[type=password]')"):
                return
            evaluate("new Promise(r=>setTimeout(r,400))")
            payload = call("Page.captureScreenshot", {"format": "png", "captureBeyondViewport": False})
            (RUN / (name + ".png")).write_bytes(base64.b64decode(payload["data"]))

        def check(name, expression, timeout=120):
            passed = False
            for _ in range(timeout):
                if evaluate(expression):
                    passed = True
                    break
                time.sleep(.1)
            checks.append({"name": name, "passed": passed})
            if not passed:
                screenshot("failed-" + name.replace(" ", "-")[:60])
                raise AssertionError(name)

        def helpers():
            evaluate(r"""(()=>{
              window.delay=(ms=120)=>new Promise(r=>setTimeout(r,ms));
              window.main=()=>document.querySelector('main');
              window.dialog=()=>[...document.querySelectorAll('.MuiDialog-root [role=dialog]')].at(-1);
              window.button=(text,scope=document)=>[...scope.querySelectorAll('button,a')].find(el=>el.textContent.trim()===text);
              window.buttonStarts=(text,scope=document)=>[...scope.querySelectorAll('button,a')].find(el=>el.textContent.trim().startsWith(text));
              window.tab=(text)=>[...document.querySelectorAll('[role=tab]')].find(e=>e.textContent.trim()===text);
              window.field=(label,scope=document)=>{const el=[...scope.querySelectorAll('label,[id$="-label"]')].find(el=>el.textContent.replace('*','').trim()===label);return el&&(document.getElementById(el.htmlFor)||[...scope.querySelectorAll('[role=combobox]')].find(input=>input.getAttribute('aria-labelledby')?.split(' ').includes(el.id)));};
              window.input=(label,value,scope=document)=>{const el=field(label,scope);const proto=el.tagName==='TEXTAREA'?HTMLTextAreaElement.prototype:HTMLInputElement.prototype;Object.getOwnPropertyDescriptor(proto,'value').set.call(el,String(value));el.dispatchEvent(new Event('input',{bubbles:true}));};
              window.choose=async(label,text,scope=document)=>{field(label,scope).dispatchEvent(new MouseEvent('mousedown',{bubbles:true}));await delay();[...document.querySelectorAll('[role=option]')].find(el=>el.textContent===text||el.textContent.startsWith(text)).click();await delay();};
              window.api=async(path,body,method='POST')=>{const response=await fetch('/api/v2'+path,{method:body===undefined?'GET':method,headers:{Authorization:'Bearer '+localStorage.getItem('token'),...(body===undefined?{}:{'Content-Type':'application/json'})},body:body===undefined?undefined:JSON.stringify(body)});if(!response.ok)throw Error('Local API failed '+response.status+' '+path);return response.json();};
              window.rows=data=>Array.isArray(data)?data:data.items;
              window.go=async(path)=>{history.pushState({},'',path);dispatchEvent(new PopStateEvent('popstate'));await delay();};
              window.text=()=>document.body.innerText;
            })()""")

        def navigate(path):
            call("Page.navigate", {"url": args.origin + path})
            check("navigate " + path, "document.readyState==='complete'")
            helpers()

        def login(role, path="/login"):
            call("Storage.clearDataForOrigin", {"origin": args.origin, "storageTypes": "all"})
            navigate(path)
            check(role + " login form", "!!document.querySelector('#username')&&!!document.querySelector('#password')")
            for selector, value in (("#username", role + "_demo"), ("#password", credentials["accounts"][role + "_demo"])):
                evaluate("(()=>{const e=document.querySelector(" + json.dumps(selector) + ");Object.getOwnPropertyDescriptor(HTMLInputElement.prototype,'value').set.call(e," + json.dumps(value) + ");e.dispatchEvent(new Event('input',{bubbles:true}));})()")
            evaluate("document.querySelector('button[type=submit]').click()")

        def metrics(mobile):
            call("Emulation.setDeviceMetricsOverride", {"width": 390 if mobile else 1440, "height": 844 if mobile else 1050, "deviceScaleFactor": 1, "mobile": mobile})

        call("Network.enable")
        call("Runtime.enable")
        call("Fetch.enable", {"patterns": [{"urlPattern": "*"}]})
        metrics(False)

        # --- 1. anonymous public page, redirects, error/empty/retry states -------------------
        call("Storage.clearDataForOrigin", {"origin": args.origin, "storageTypes": "all"})
        navigate("/")
        check("anonymous root redirects to public page", "location.pathname==='/gioi-thieu'")
        check("public page renders lot name and price section", "/Bảng giá & gói vé/.test(text())&&!!document.querySelector('h1')")
        check("public page offers login and register", "!!button('Đăng nhập')&&!!button('Đăng ký')&&!!button('Đăng nhập để mua vé')")
        check("public page never shows plates or phone list", "!/Biển số/.test(text())")
        screenshot("public-anonymous-desktop")
        metrics(True)
        check("public page fits mobile width", "document.documentElement.scrollWidth<=innerWidth+1")
        screenshot("public-anonymous-mobile")
        metrics(False)
        fail_public_once['armed'] = True
        navigate("/gioi-thieu")
        check("public page shows API error with retry", "/Không tải được thông tin bãi xe/.test(text())&&!!button('Thử lại')")
        screenshot("public-api-error")
        evaluate("button('Thử lại').click()")
        check("retry recovers the public page", "/Bảng giá & gói vé/.test(text())&&!/Không tải được/.test(text())")
        fail_public_once['empty'] = True
        navigate("/gioi-thieu")
        check("empty catalog shows not-published placeholders", "/chưa công bố gói vé/.test(text())&&/Chưa cập nhật/.test(text())")
        screenshot("public-empty-catalog")
        navigate("/portal")
        check("private path redirects to login with continuation", "location.pathname==='/login'&&new URLSearchParams(location.search).get('next')==='/portal'")
        navigate("/login?next=https%3A%2F%2Fevil.example%2F")
        check("open redirect target is ignored on the login page", "!/tiếp tục thao tác/.test(text())")

        # --- 2. login continuation from the public call to action ------------------------------
        navigate("/gioi-thieu")
        check("public call to action ready", "!!button('Đăng nhập để mua vé')")
        evaluate("button('Đăng nhập để mua vé').click()")
        check("call to action lands on login with purchase continuation", "location.pathname==='/login'&&(new URLSearchParams(location.search).get('next')||'').startsWith('/portal?tab=purchase')&&/tiếp tục thao tác/.test(text())")
        for selector, value in (("#username", "customer_demo"), ("#password", credentials["accounts"]["customer_demo"])):
            evaluate("(()=>{const e=document.querySelector(" + json.dumps(selector) + ");Object.getOwnPropertyDescriptor(HTMLInputElement.prototype,'value').set.call(e," + json.dumps(value) + ");e.dispatchEvent(new Event('input',{bubbles:true}));})()")
        evaluate("document.querySelector('button[type=submit]').click()")
        check("customer resumes the purchase flow after login", "location.pathname==='/portal'&&new URLSearchParams(location.search).get('tab')==='purchase'&&!!document.querySelector('main')")
        helpers()
        check("purchase tab is selected", "tab('Mua vé & đơn hàng')?.getAttribute('aria-selected')==='true'")
        screenshot("customer-purchase-after-login")
        navigate("/gioi-thieu")
        check("signed-in customer sees own portal button on public page", "!!button('Bãi xe của tôi')&&!!button('Mua vé')")
        navigate("/gioi-thieu")
        check("refresh keeps the public page without redirect loop", "location.pathname==='/gioi-thieu'")

        # --- 3. customer opens a support request ----------------------------------------------
        navigate("/portal?tab=support")
        check("support tab opens from continuation", "tab('Hỗ trợ & hoàn tiền')?.getAttribute('aria-selected')==='true'")
        evaluate("input('Tiêu đề','UAT hỗ trợ " + suffix + "')")
        evaluate("input('Nội dung','Xin hỗ trợ kiểm tra vé (UAT trình duyệt).')")
        evaluate("button('Gửi yêu cầu').click()")
        check("support request created and thread dialog opens", "!!dialog()&&/UAT hỗ trợ " + suffix + "/.test(dialog().textContent)&&/Chờ phản hồi/.test(dialog().textContent)")
        screenshot("customer-support-created")
        evaluate("button('Đóng',dialog()).click()")
        check("support list shows the new request", "/UAT hỗ trợ " + suffix + "/.test(main().textContent)")
        metrics(True)
        check("support tab fits mobile width", "document.documentElement.scrollWidth<=innerWidth+1")
        screenshot("customer-support-mobile")
        metrics(False)

        # --- 4. manager replies in the browser -----------------------------------------------
        login("manager")
        check("manager login completes", "location.pathname==='/sites'&&!!document.querySelector('main')")
        helpers()
        navigate("/portal-admin")
        check("manager admin page loaded", "!!tab('Hỗ trợ khách')")
        evaluate("tab('Hỗ trợ khách').click()")
        check("manager sees the open support request", "/UAT hỗ trợ " + suffix + "/.test(main().textContent)")
        evaluate("[...main().querySelectorAll('tr')].find(tr=>tr.textContent.includes('UAT hỗ trợ " + suffix + "')).querySelector('button').click()")
        check("manager thread dialog open", "!!dialog()&&/Xin hỗ trợ kiểm tra vé/.test(dialog().textContent)")
        evaluate("input('Phản hồi cho khách','Đã kiểm tra, vé hợp lệ (UAT).',dialog())")
        evaluate("button('Gửi phản hồi',dialog()).click()")
        check("manager reply recorded", "/Đã phản hồi/.test(dialog().textContent)&&/Đã kiểm tra, vé hợp lệ/.test(dialog().textContent)")
        screenshot("manager-support-replied")
        evaluate("button('Đóng',dialog()).click()")

        # --- 5. manager publishes the public profile ----------------------------------------
        navigate("/sites")
        check("sites workspace loaded", "!!main()&&/Vận hành|Bãi/.test(main().textContent)")
        check("site configuration tab available to the manager", "!!tab('Cấu hình bãi')")
        evaluate("tab('Cấu hình bãi').click()")
        check("public profile editor visible", "/Trang giới thiệu công khai/.test(main().textContent)&&!!field('Giờ mở cửa')")
        evaluate("input('Giờ mở cửa','05:30–23:00 (UAT " + suffix + ")')")
        evaluate("input('Địa chỉ','DEMO - 1 Đường Thử Nghiệm')")
        evaluate("button('Lưu thông tin công khai').click()")
        check("public profile saved", "/Đã cập nhật trang giới thiệu/.test(main().textContent)")
        screenshot("manager-public-profile-saved")
        call("Storage.clearDataForOrigin", {"origin": args.origin, "storageTypes": "all"})
        navigate("/gioi-thieu")
        check("anonymous page shows the published opening hours", "/05:30–23:00 \\(UAT " + suffix + "\\)/.test(text())&&!!button('Chỉ đường')")
        screenshot("public-after-publish")

        # --- 6. customer reads the reply and closes; refund flow -----------------------------
        login("customer")
        check("customer login completes", "location.pathname==='/portal'&&!!document.querySelector('main')")
        helpers()
        check("customer tabs ready", "!!tab('Hỗ trợ & hoàn tiền')")
        evaluate("tab('Hỗ trợ & hoàn tiền').click()")
        check("customer sees answered status", "/Đã phản hồi/.test(main().textContent)")
        evaluate("[...main().querySelectorAll('tr')].find(tr=>tr.textContent.includes('UAT hỗ trợ " + suffix + "')).querySelector('button').click()")
        check("customer reads manager reply", "!!dialog()&&/Đã kiểm tra, vé hợp lệ/.test(dialog().textContent)")
        evaluate("button('Đóng yêu cầu',dialog()).click()")
        check("customer closed the request", "/Đã đóng/.test(dialog().textContent)")
        screenshot("customer-support-closed")
        evaluate("button('Đóng',dialog()).click()")
        # A fresh DEMO monthly purchase via the local API from the browser context (synthetic DB only).
        plans = evaluate("api('/plans').then(rows)")
        vehicles = evaluate("api('/me/vehicles').then(rows)")
        monthly = [plan for plan in plans if plan["product_kind"] == "monthly"]
        chosen = next(((v, p) for v in vehicles for p in monthly if p["vehicle_type_id"] == v["vehicle_type_id"]), None)
        assert chosen, "Seed must offer a monthly plan for an owned vehicle"
        vehicle, plan = chosen
        order = evaluate("api('/me/orders'," + json.dumps({"plan_id": plan["id"], "vehicle_id": vehicle["id"], "idempotency_key": "uat-browser-" + suffix, "payment_mode": "demo"}) + ")")
        if order.get("status") == "pending":
            paid = evaluate("api('/me/orders/" + order["id"] + "/simulate'," + json.dumps({"token": order["demo_token"], "outcome": "success"}) + ")")
            assert paid["status"] == "fulfilled", paid
        check("history tab ready", "!!tab('Lịch sử & chứng từ')")
        evaluate("tab('Lịch sử & chứng từ').click()")
        evaluate("button('Làm mới').click()")
        check("customer sees refund button on eligible receipt", "!!button('Yêu cầu hoàn',main())")
        evaluate("button('Yêu cầu hoàn',main()).click()")
        check("refund dialog states the server refundable amount", "!!dialog()&&/Số có thể hoàn theo máy chủ/.test(dialog().textContent)")
        evaluate("input('Lý do yêu cầu hoàn','UAT trình duyệt hoàn DEMO " + suffix + "',dialog())")
        evaluate("button('Gửi yêu cầu hoàn',dialog()).click()")
        check("refund request submitted and shown as received", "tab('Hỗ trợ & hoàn tiền')?.getAttribute('aria-selected')==='true'&&/Đã tiếp nhận/.test(main().textContent)")
        screenshot("customer-refund-requested")
        metrics(True)
        check("refund list fits mobile width", "document.documentElement.scrollWidth<=innerWidth+1")
        screenshot("customer-refund-mobile")
        metrics(False)

        # --- 7. manager approves the DEMO refund in the browser ------------------------------
        login("manager")
        check("manager second login completes", "location.pathname==='/sites'")
        helpers()
        navigate("/portal-admin")
        check("manager admin loaded again", "!!tab('Yêu cầu hoàn')")
        evaluate("tab('Yêu cầu hoàn').click()")
        check("manager sees pending refund", "/UAT trình duyệt hoàn DEMO/.test(main().textContent)&&!!button('Duyệt',main())")
        evaluate("[...main().querySelectorAll('tr')].find(tr=>tr.textContent.includes('UAT trình duyệt hoàn DEMO " + suffix + "')).querySelector('button').click()")
        check("refund decision dialog shows server balance", "!!dialog()&&/còn có thể hoàn/.test(dialog().textContent)")
        screenshot("manager-refund-dialog")
        if evaluate("dialog().textContent.includes('Bắt đầu xem xét')"):
            evaluate("dialog().querySelector('input[type=checkbox]').click()")
            evaluate("button('Xác nhận',dialog()).click()")
            check("review recorded and row offers approval", "(()=>{if(dialog())return false;const tr=[...main().querySelectorAll('tr')].find(tr=>tr.textContent.includes('UAT trình duyệt hoàn DEMO " + suffix + "'));return !!tr&&/Đang xem xét/.test(tr.textContent)&&!!button('Duyệt',tr)&&!button('Xem xét',tr);})()")
            # The list may re-render right after the decision; click a fresh element until the dialog is open.
            opened = False
            for _ in range(10):
                evaluate("delay(500).then(()=>{const tr=[...main().querySelectorAll('tr')].find(tr=>tr.textContent.includes('UAT trình duyệt hoàn DEMO " + suffix + "'));const b=tr&&button('Duyệt',tr);if(b)b.click();})")
                if evaluate("!!dialog()&&/Duyệt yêu cầu hoàn/.test(dialog().textContent)"):
                    opened = True
                    break
            checks.append({"name": "approve dialog open after review", "passed": opened})
            if not opened:
                screenshot("failed-approve-dialog")
                raise AssertionError("approve dialog open after review")
        evaluate("input('Ghi chú xử lý','Đã đối chiếu (UAT)',dialog())")
        evaluate("dialog().querySelector('input[type=checkbox]').click()")
        evaluate("button('Xác nhận',dialog()).click()")
        check("refund approved and settled as DEMO", "/Đã ghi nhận quyết định/.test(main().textContent)")
        evaluate("[...document.querySelectorAll('[role=combobox]')].find(el=>el.textContent.includes('Đang chờ')||el.textContent.includes('tiếp nhận'))?.dispatchEvent(new MouseEvent('mousedown',{bubbles:true}))")
        evaluate("delay().then(()=>[...document.querySelectorAll('[role=option]')].find(el=>el.textContent==='Đã hoàn tiền')?.click())")
        check("manager list shows refunded DEMO row", "/Đã hoàn mô phỏng \\(DEMO\\)/.test(main().textContent)")
        screenshot("manager-refund-done")
        login("customer")
        check("customer final login", "location.pathname==='/portal'")
        helpers()
        check("customer tabs ready again", "!!tab('Hỗ trợ & hoàn tiền')")
        evaluate("tab('Hỗ trợ & hoàn tiền').click()")
        check("customer sees DEMO refund completed", "/Đã hoàn mô phỏng \\(DEMO\\)/.test(main().textContent)")
        evaluate("tab('Lịch sử & chứng từ').click()")
        check("customer ledger shows the DEMO refund row", "[...main().querySelectorAll('td')].some(td=>td.textContent==='Hoàn')")
        screenshot("customer-refund-completed")
        completed = True
finally:
    for path, payload in (("checks.json", checks), ("requests.json", requests), ("mutations.json", mutations),
                          ("http-errors.json", http_errors), ("runtime-errors.json", runtime_errors), ("blocked-external.json", blocked_external)):
        (RUN / path).write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    (RUN / "result.json").write_text(json.dumps({"completed": completed, "origin": args.origin, "passed": sum(c["passed"] for c in checks),
        "total": len(checks), "mutations": len(mutations), "blocked_external": len(blocked_external), "http_errors": len(http_errors),
        "runtime_errors": len(runtime_errors), "artifacts": str(RUN)}, ensure_ascii=False, indent=2), encoding="utf-8")
    chrome.terminate()
    try:
        chrome.wait(timeout=10)
    except subprocess.TimeoutExpired:
        chrome.kill()
    log.close()
print(json.dumps({"completed": completed, "passed": sum(c["passed"] for c in checks), "total": len(checks), "artifacts": str(RUN),
    "mutations": len(mutations), "blocked_external": len(blocked_external), "http_errors": http_errors[:5], "runtime_errors": runtime_errors[:3]}, ensure_ascii=False))
