"""Approved simplified UI against the disposable synthetic server on 127.0.0.1:8793.

No database setup, provider calls or external traffic. Business writes are driven
through the real UI; helper API calls only read. AI POSTs receive an explicit
test-only unavailable response, so error/history UI can be checked without an LLM.
Credentials and private ticket proof live only in memory, never in artifacts.
"""
import argparse
import base64
import json
from pathlib import Path
import shutil
import subprocess
import time
import urllib.parse
import urllib.request
from uuid import uuid4

from websockets.sync.client import connect

ROOT = Path(__file__).resolve().parents[3]
parser = argparse.ArgumentParser()
parser.add_argument("--origin", default="http://127.0.0.1:8793")
parser.add_argument("--credentials", type=Path, required=True)
parser.add_argument("--site", type=int, default=1)
parser.add_argument("--visual-only", action="store_true", help="Repeat the screenshot batch without business mutations")
parser.add_argument("--transactions-only", action="store_true", help="Continue business UAT after reviewing the captured visual batch")
parser.add_argument("--roles", nargs="+", choices=["manager", "staff", "customer", "admin"], help="Resume a visual-only subset after an external server restart")
args = parser.parse_args()
if args.roles and not args.visual_only:
    raise ValueError("Role subsets are allowed only for read-only visual confirmation")
if args.origin != "http://127.0.0.1:8793":
    raise ValueError("Only the disposable approved-demo server on 127.0.0.1:8793 is permitted")
credentials = json.loads(args.credentials.read_text(encoding="utf-8"))
marker = json.loads(Path(credentials["database"] + ".demo.json").read_text(encoding="utf-8"))
if credentials.get("profile") != "single-lot-academic-v1" or marker.get("synthetic_history") is not True:
    raise ValueError("Explicit synthetic database marker and academic credential sidecar required")
if any(role + "_demo" not in credentials["accounts"] for role in ("manager", "staff", "customer", "admin")):
    raise ValueError("Four prepared demo accounts are required; this harness never creates users")

RUN = ROOT / "backend/artifacts/approved-demo-browser" / uuid4().hex[:10]
RUN.mkdir(parents=True)
print(json.dumps({"artifact_directory": str(RUN), "phase": "starting"}, ensure_ascii=True), flush=True)
PROFILE = RUN / "chrome-profile"
checks, requests, http_errors, runtime_errors, blocked_external, blocked_provider = [], [], [], [], [], []
completed = False
suffix = uuid4().hex[:6].upper()
walkin_plate = "UAT" + suffix
booking_plate = "DAT" + suffix
proof = None
walkin_id = None
own_vehicle = None
own_active = False
car_type = None
unplated_type = None
monthly_baseline = []


class VisualComplete(Exception):
    """End the read-only confirmation pass through the same guarded cleanup."""

HELPERS = r"""(()=>{
  window.delay=(ms=150)=>new Promise(r=>setTimeout(r,ms));
  window.main=()=>document.querySelector('main');
  window.text=()=>main()?.innerText||'';
  window.dialog=()=>[...document.querySelectorAll('.MuiDialog-root [role=dialog]')].at(-1);
  window.button=(label,scope=document)=>[...scope.querySelectorAll('button,a')].find(e=>e.textContent.trim()===label);
  window.starts=(label,scope=document)=>[...scope.querySelectorAll('button,a')].find(e=>e.textContent.trim().startsWith(label));
  window.tab=(label)=>[...document.querySelectorAll('[role=tab]')].find(e=>e.textContent.trim()===label);
  window.field=(label,scope=document)=>{const l=[...scope.querySelectorAll('label,[id$="-label"]')].find(e=>e.textContent.replace('*','').trim()===label);return l&&(document.getElementById(l.htmlFor)||[...scope.querySelectorAll('[role=combobox]')].find(e=>e.getAttribute('aria-labelledby')?.split(' ').includes(l.id)));};
  window.input=(label,value,scope=document)=>{const e=field(label,scope);if(!e)throw Error('Missing field');Object.getOwnPropertyDescriptor(e.tagName==='TEXTAREA'?HTMLTextAreaElement.prototype:HTMLInputElement.prototype,'value').set.call(e,String(value));e.dispatchEvent(new Event('input',{bubbles:true}));};
  window.choose=async(label,value,scope=document)=>{let e;for(let n=0;n<100;n++){e=field(label,scope);if(e&&e.getAttribute('aria-disabled')!=='true')break;await delay(50);}if(!e)throw Error('Missing selection');e.dispatchEvent(new MouseEvent('mousedown',{bubbles:true}));let o;for(let n=0;n<100;n++){o=[...document.querySelectorAll('[role=option]')].find(e=>e.textContent.trim()===value||e.textContent.trim().startsWith(value));if(o)break;await delay(50);}if(!o)throw Error('Missing option');o.click();await delay();};
  window.api=async path=>{const r=await fetch(path,{headers:{Authorization:'Bearer '+localStorage.getItem('token')}});if(!r.ok)throw Error('Read API failed '+r.status);return r.json();};
  window.rows=data=>Array.isArray(data)?data:(data.items||[]);
  window.nav=()=>[...document.querySelectorAll('.MuiDrawer-root a,[aria-label="Điều hướng khách hàng"] a')].map(e=>e.textContent.trim());
  window.menu=()=>[...document.querySelectorAll('.MuiDrawer-root,[aria-label="Điều hướng khách hàng"]')].map(e=>e.innerText).join(' ');
})()"""

log = (RUN / "process.log").open("w", encoding="utf-8")
chrome = subprocess.Popen([r"C:\Program Files\Google\Chrome\Application\chrome.exe", "--headless=new", "--disable-gpu",
    "--no-first-run", "--no-default-browser-check", "--disable-background-networking", "--disable-component-update", "--disable-sync",
    "--remote-debugging-port=18994", "--remote-debugging-address=127.0.0.1", "--window-size=1440,1050",
    "--user-data-dir=" + str(PROFILE), "about:blank"], stdout=log, stderr=log, creationflags=subprocess.CREATE_NO_WINDOW)
try:
    for _ in range(60):
        try:
            target = next(row for row in json.load(urllib.request.urlopen("http://127.0.0.1:18994/json", timeout=1)) if row["type"] == "page")
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
                response = json.loads(ws.recv(timeout=45))
                event = response.get("method")
                if event == "Fetch.requestPaused":
                    paused = response["params"]
                    request = paused["request"]
                    parsed = urllib.parse.urlsplit(request["url"])
                    local = parsed.netloc == "127.0.0.1:8793"
                    ai_post = local and request["method"] == "POST" and (parsed.path.endswith("/assistant") or "/ai/" in parsed.path)
                    payment_provider = local and any(part in parsed.path for part in ("payment-link", "/simulate", "/webhook", "/reconcile"))
                    allowed = (local and not payment_provider) or parsed.scheme in {"data", "blob", "about"}
                    sequence += 1
                    if ai_post:
                        # Explicit fixture for UI error state; no request reaches the AI backend.
                        body = json.dumps({"detail": "AI tạm tắt trong kiểm thử giao diện; chưa gọi mô hình."}, ensure_ascii=False)
                        command = {"id": sequence, "method": "Fetch.fulfillRequest", "params": {"requestId": paused["requestId"], "responseCode": 503,
                            "responseHeaders": [{"name": "Content-Type", "value": "application/json; charset=utf-8"}], "body": base64.b64encode(body.encode()).decode()}}
                    else:
                        if payment_provider:
                            blocked_provider.append({"method": request["method"], "path": parsed.path})
                        elif not allowed:
                            blocked_external.append({"host": parsed.hostname, "scheme": parsed.scheme})
                        command = {"id": sequence, "method": "Fetch.continueRequest" if allowed else "Fetch.failRequest",
                            "params": {"requestId": paused["requestId"], **({} if allowed else {"errorReason": "BlockedByClient"})}}
                    ws.send(json.dumps(command))
                if event == "Network.requestWillBeSent":
                    req = response["params"]["request"]
                    parsed = urllib.parse.urlsplit(req["url"])
                    if parsed.netloc == "127.0.0.1:8793":
                        requests.append({"method": req["method"], "path": parsed.path})
                if event == "Network.responseReceived":
                    item = response["params"]["response"]
                    path = urllib.parse.urlsplit(item["url"]).path
                    if item["status"] >= 400 and not (item["status"] == 503 and (path.endswith("/assistant") or "/ai/" in path)):
                        http_errors.append({"status": item["status"], "path": path})
                if event == "Runtime.exceptionThrown":
                    runtime_errors.append({"text": response["params"]["exceptionDetails"]["text"]})
                if response.get("id") == wanted:
                    if "error" in response:
                        raise RuntimeError("Browser command failed: " + method)
                    return response.get("result", {})

        def evaluate(expression):
            result = call("Runtime.evaluate", {"expression": expression, "awaitPromise": True, "returnByValue": True})
            if "exceptionDetails" in result:
                raise RuntimeError("Browser evaluation failed (details withheld to protect private inputs)")
            return result.get("result", {}).get("value")

        def check(name, expression, timeout=120):
            passed = False
            for _ in range(timeout):
                if evaluate(expression):
                    passed = True
                    break
                time.sleep(.1)
            checks.append({"name": name, "passed": passed})
            if not passed:
                checks[-1]["context"] = evaluate("({path:location.pathname,navigation:typeof menu==='function'?menu():'',labels:[...document.querySelectorAll('main label')].map(e=>e.textContent),dialogOpen:!!document.querySelector('.MuiDialog-root [role=dialog]')})")
                raise AssertionError(name)

        def metrics(mobile=False):
            call("Emulation.setDeviceMetricsOverride", {"width": 390 if mobile else 1440, "height": 844 if mobile else 1050, "deviceScaleFactor": 1, "mobile": mobile})

        def screenshot(name, mobile=False):
            metrics(mobile)
            evaluate("delay(300)")
            # Never capture login, ticket dialogs or secret credentials, even on failure.
            if evaluate("location.pathname==='/login'||!!document.querySelector('.parking-ticket-dialog')||[...document.querySelectorAll('input[type=password]')].some(e=>e.value)"):
                raise RuntimeError("Screenshot refused because private inputs are visible")
            evaluate("(()=>{let s=document.getElementById('uat-private-mask');if(!s){s=document.createElement('style');s.id='uat-private-mask';s.textContent='input[type=password],[data-payment-proof],[data-private]{visibility:hidden!important}';document.head.append(s);}})()")
            payload = call("Page.captureScreenshot", {"format": "png", "captureBeyondViewport": False})
            (RUN / (name + ".png")).write_bytes(base64.b64decode(payload["data"]))
            # Collect all representative layouts in one pass, even if one overflows.
            viewport = evaluate("({innerWidth,scrollWidth:document.documentElement.scrollWidth,clientWidth:document.documentElement.clientWidth,viewportWidth:visualViewport?.width,viewportScale:visualViewport?.scale,mainWidth:main()?.getBoundingClientRect().width})")
            target_width = 390 if mobile else 1440
            checks.append({"name": name + " fits viewport", "passed": viewport["scrollWidth"] <= target_width + 1 and viewport["innerWidth"] <= target_width + 1 and abs((viewport["viewportScale"] or 1) - 1) < .02, "viewport": viewport})
            metrics(False)

        def navigate(path):
            call("Page.navigate", {"url": args.origin + path})
            for _ in range(100):
                if evaluate("document.readyState==='complete'"):
                    break
                time.sleep(.1)
            evaluate(HELPERS)

        def login(role):
            call("Storage.clearDataForOrigin", {"origin": args.origin, "storageTypes": "all"})
            navigate("/login")
            check(role + " login form", "!!document.querySelector('#username')&&!!document.querySelector('#password')")
            for selector, value in (("#username", role + "_demo"), ("#password", credentials["accounts"][role + "_demo"])):
                evaluate("(()=>{const e=document.querySelector(" + json.dumps(selector) + ");Object.getOwnPropertyDescriptor(HTMLInputElement.prototype,'value').set.call(e," + json.dumps(value) + ");e.dispatchEvent(new Event('input',{bubbles:true}));})()")
            evaluate("document.querySelector('button[type=submit]').click()")
            check(role + " authenticated", "location.pathname!=='/login'&&!!main()&&!!document.querySelector('[aria-label=\"Mở trợ lý ParkingAI\"]')")

        def chat(role):
            evaluate("document.querySelector('[aria-label=\"Mở trợ lý ParkingAI\"]').click()")
            check(role + " floating assistant opens", "!!document.getElementById('parking-chat-title')")
            evaluate("input('Câu hỏi'," + json.dumps("Bảng giá gửi xe" if role == "customer" else "Khung giờ nào đông nhất tuần này?") + ")")
            evaluate("document.querySelector('[aria-label=\"Gửi câu hỏi\"]').click()")
            check(role + " assistant shows explicit unavailable state", "document.body.innerText.includes('AI tạm tắt trong kiểm thử giao diện')")
            screenshot(role + "-assistant-error")
            evaluate("document.querySelector('[aria-label=\"Đóng trợ lý\"]').click()")

        call("Network.enable")
        call("Runtime.enable")
        call("Fetch.enable", {"patterns": [{"urlPattern": "*"}]})
        metrics()

        # First pass batches all representative screenshots before any private ticket handling.
        for role in (() if args.transactions_only else args.roles or ("manager", "staff", "customer", "admin")):
            login(role)
            if role == "customer":
                navigate("/portal?tab=fees")
                check("customer compact four tasks", "['Phí gửi xe','Đặt chỗ trước','Vé & lịch sử','Hỗ trợ'].every(x=>menu().includes(x))&&!menu().includes('Tài khoản nhân sự')")
                check("customer fee form before profile verification", "!!field('Biển số hoặc mã xe')&&!!field('Loại xe')")
                screenshot("customer-fees-desktop")
                screenshot("customer-fees-mobile", True)
                if not args.visual_only:
                    owned = evaluate("api('/api/v2/me/vehicles').then(rows)")
                    active = evaluate("api('/api/v2/me/sessions?limit=100').then(rows)")
                    own_active_rows = [row for row in active if row.get("status") == "active"]
                    own_vehicle = next((row for row in owned if any(stay["license_plate"] == row["license_plate"] for stay in own_active_rows)), owned[0] if owned else None)
                    own_active = bool(own_vehicle and any(row["license_plate"] == own_vehicle["license_plate"] for row in own_active_rows))
                navigate("/reservations")
                check("booking uses declared plate and time without ownership approval", "!!field('Biển số xe')&&!!field('Giờ đến dự kiến')&&!!button('Giữ chỗ · trả sau')")
                screenshot("customer-booking-desktop")
                screenshot("customer-booking-mobile", True)
                navigate("/portal?tab=tickets&view=history")
                check("customer history and receipts accessible", "text().includes('Chứng từ')")
                screenshot("customer-history-desktop")
                navigate("/portal?tab=support")
                check("customer support remains accessible", "!!field('Tiêu đề')&&!!button('Gửi yêu cầu')")
                screenshot("customer-support-mobile", True)
                chat(role)
            else:
                check(role + " seven primary destinations", "['Tổng quan','Vận hành','Bãi đỗ','Lịch sử gửi xe','Khách & vé','Thu chi & báo cáo','Loại xe & bảng giá'].every(x=>menu().includes(x))")
                check(role + " administration boundary", "menu().includes('Tài khoản nhân sự')===" + ("false" if role == "staff" else "true"))
                navigate("/")
                check(role + " overview loaded", "!!main()&&text().includes('Tổng quan')")
                screenshot(role + "-overview-desktop")
                if role == "manager":
                    screenshot("manager-overview-mobile", True)
                navigate("/sites")
                check(role + " manual operations ready", "!!tab('Nhập tay')&&!!tab('Camera')&&!!button('Ghi nhận xe vào')")
                screenshot(role + "-operations-desktop")
                if role in {"manager", "staff"}:
                    screenshot(role + "-operations-mobile", True)
                evaluate("tab('Camera').click()")
                check(role + " camera mode accessible", "!field('Biển số xe')||!!button('Bắt đầu camera')||text().includes('camera')")
                screenshot(role + "-camera-desktop")
                navigate("/reports")
                check(role + " real scoped report visible", "text().includes('Lượt')&&!!main()")
                if role == "staff":
                    check("staff report has no revenue", "!text().includes('Thu gửi xe')&&!text().includes('Doanh thu thuần')")
                screenshot(role + "-reports-desktop")
                if role == "manager":
                    screenshot("manager-reports-mobile", True)
                    navigate("/ai")
                    check("AI analysis page available", "text().includes('AI')&&!!main()")
                    screenshot("manager-ai-desktop")
                    screenshot("manager-ai-mobile", True)
                    navigate("/parking-slots")
                    check("lot zone availability visible", "text().includes('Còn trống')")
                    screenshot("manager-lot-desktop")
                    screenshot("manager-lot-mobile", True)
                    navigate("/monthly-passes")
                    check("monthly lifecycle controls available", "!!button('Đăng ký vé tháng')&&!!document.querySelector('[aria-label^=\"Gia hạn thẻ\"]')")
                    screenshot("manager-monthly-desktop")
                    monthly_baseline = evaluate("api('/api/v1/monthly-passes?limit=100').then(rows)")
                    for route, title, field_name in (("/vehicle-types", "vehicle-type", "Tiền tố mã xe (ví dụ XD)"), ("/zones", "zone", "Sức chứa")):
                        navigate(route)
                        check(title + " create available", "!!button('Thêm mới')")
                        evaluate("button('Thêm mới').click()")
                        check(title + " full editor fields", "!!dialog()&&!!field(" + json.dumps(field_name) + ",dialog())")
                        if route == "/vehicle-types":
                            check("unplated vehicle type switch", "dialog().innerText.includes('Có biển số')&&!!dialog().querySelector('input[type=checkbox]')")
                        screenshot("manager-" + title + "-form")
                        evaluate("button('Hủy',dialog()).click()")
                    navigate("/parking-slots")
                    check("slot editor available from map", "!!button('Thêm / sửa vị trí đỗ')")
                    evaluate("button('Thêm / sửa vị trí đỗ').click()")
                    check("slot list create available", "!!button('Thêm mới')")
                    evaluate("button('Thêm mới').click()")
                    check("slot editor links vehicle type and zone", "!!dialog()&&!!field('Mã vị trí',dialog())&&!!field('Khu vực',dialog())&&!!field('Loại xe',dialog())")
                    screenshot("manager-slot-form")
                    evaluate("button('Hủy',dialog()).click()")
                if role == "admin":
                    navigate("/users")
                    check("admin inherits account management", "text().includes('Tài khoản')||text().includes('người dùng')")
                    screenshot("admin-accounts-desktop")
                chat(role)

        if args.visual_only:
            call("Storage.clearDataForOrigin", {"origin": args.origin, "storageTypes": "all"})
            raise VisualComplete()

        if args.transactions_only:
            login("customer")
            owned = evaluate("api('/api/v2/me/vehicles').then(rows)")
            active = evaluate("api('/api/v2/me/sessions?limit=100').then(rows)")
            own_active_rows = [row for row in active if row.get("status") == "active"]
            own_vehicle = next((row for row in owned if any(stay["license_plate"] == row["license_plate"] for stay in own_active_rows)), owned[0] if owned else None)
            own_active = bool(own_vehicle and any(row["license_plate"] == own_vehicle["license_plate"] for row in own_active_rows))

        # Real UI transactions on the disposable synthetic database.
        login("manager")
        if args.transactions_only:
            monthly_baseline = evaluate("api('/api/v1/monthly-passes?limit=100').then(rows)")
        catalog = evaluate("api('/api/v2/catalog/vehicle-types').then(rows)")
        availability = evaluate(f"api('/api/v2/sites/{args.site}/availability')")
        available_types = {slot["vehicle_type_id"] for slot in availability["slots"] if slot.get("available_now")}
        car_type = next((row for row in catalog if row.get("is_active", True) and row.get("requires_plate", True) and row["id"] in available_types), None)
        unplated_type = next((row for row in catalog if row.get("is_active", True) and row.get("requires_plate") is False and row["id"] in available_types), None)
        if not car_type:
            raise AssertionError("Scratch seed needs one available plated vehicle type")

        def admit(plate, type_name):
            navigate("/sites")
            check("admission form ready", "!!field('Loại xe')&&!!button('Ghi nhận xe vào')")
            evaluate("choose('Loại xe'," + json.dumps(type_name) + ")")
            if plate:
                evaluate("input('Biển số xe'," + json.dumps(plate) + ")")
            else:
                check("unplated admission needs no plate", "!!field('Mã xe (không bắt buộc)')&&!field('Mã xe (không bắt buộc)').required")
            evaluate("button('Ghi nhận xe vào').click()")
            check("walk-in admitted without reservation", "text().includes('Đã ghi nhận xe vào')&&!!button('Xem vé')")

        admit(walkin_plate, car_type["name"])
        walkin = evaluate(f"api('/api/v2/sites/{args.site}/sessions?status=active&license_plate={walkin_plate}').then(rows)")[0]
        walkin_id = walkin["id"]
        ticket = evaluate(f"api('/api/v2/sites/{args.site}/sessions/{walkin_id}/ticket')")
        proof = ticket.get("payment_access_code")
        if not proof:
            raise AssertionError("Ticket must issue separate private payment proof")
        del ticket
        check("new walk-in has server fee", "text().includes('Còn thanh toán')")
        if own_vehicle and not own_active:
            owned_type_id = own_vehicle.get("vehicle_type_id")
            owned_type = next((row for row in catalog if row["id"] == owned_type_id), None)
            if not owned_type:
                raise AssertionError("Owned vehicle type missing from catalog")
            admit(own_vehicle["license_plate"], owned_type["name"])
        if unplated_type:
            admit("", unplated_type["name"])
            check("generated vehicle code shown after unplated entry", "!text().includes('Nhập biển số hoặc chọn một xe bên dưới.')")
        else:
            checks.append({"name": "unplated admission fixture available", "passed": False, "reason": "No available non-plated type in prepared scratch seed"})

        login("customer")
        navigate("/portal?tab=fees")
        check("customer lookup type loaded", "!!field('Loại xe')")
        if own_vehicle:
            own_type = next(row for row in catalog if row["id"] == own_vehicle["vehicle_type_id"])
            evaluate("input('Biển số hoặc mã xe'," + json.dumps(own_vehicle["license_plate"]) + ")")
            evaluate("choose('Loại xe'," + json.dumps(own_type["name"]) + ")")
            evaluate("button('Xem phí gửi xe').click()")
            check("owner fee lookup succeeds without proof", "text().includes('Thanh toán phí lượt gửi')&&text().includes('Còn thanh toán')")
        else:
            raise AssertionError("Prepared customer needs an owned vehicle for fee UAT")
        navigate("/portal?tab=fees")
        check("walk-in fee form loaded", "!!field('Loại xe')")
        evaluate("input('Biển số hoặc mã xe'," + json.dumps(walkin_plate) + ")")
        evaluate("choose('Loại xe'," + json.dumps(car_type["name"]) + ")")
        evaluate("button('Xe chưa liên kết? Dùng mã thanh toán trên vé').click()")
        evaluate("input('Mã thanh toán riêng'," + json.dumps(proof) + ")")
        evaluate("button('Xem phí gửi xe').click()")
        check("walk-in proof fee lookup succeeds", "text().includes('Đang xem đúng lượt đã xác minh')&&text().includes('Thanh toán phí lượt gửi')")
        check("private proof cleared after request", "field('Mã thanh toán riêng').value===''&&!location.href.includes('PAP1')")
        check("unconfigured provider never appears as paid", "!text().includes('Đã thanh toán thành công')")
        proof = None
        navigate("/reservations")
        check("advance booking form ready", "!!button('Giữ chỗ · trả sau')")
        evaluate("input('Biển số xe'," + json.dumps(booking_plate) + ")")
        evaluate("choose('Loại xe'," + json.dumps(car_type["name"]) + ")")
        evaluate("button('Giữ chỗ · trả sau').click()")
        check("declared booking created with no vehicle approval or prepayment", "text().includes('Đã giữ chỗ. Bạn thanh toán phí theo lượt gửi thực tế')")
        check("created booking row loaded before cancel", "!![...main().querySelectorAll('tr')].find(e=>e.textContent.includes(" + json.dumps(booking_plate) + "))?.querySelector('button')")
        evaluate("[...main().querySelectorAll('tr')].find(e=>e.textContent.includes(" + json.dumps(booking_plate) + ")).querySelector('button').click()")
        check("customer cancels advance hold", "text().includes('Đã hủy đặt chỗ')")
        navigate("/portal?tab=support")
        check("support form ready", "!!field('Tiêu đề')")
        evaluate("input('Tiêu đề','UAT giao diện " + suffix + "');input('Nội dung','Kiểm tra hỗ trợ sau khi gửi xe trong cơ sở dữ liệu mô phỏng.')")
        evaluate("button('Gửi yêu cầu').click()")
        check("support request saved and conversation opens", "!!dialog()&&dialog().innerText.includes('UAT giao diện " + suffix + "')")
        evaluate("button('Đóng',dialog()).click()")

        login("manager")
        navigate("/sites")
        check("manual exit lookup ready", "!!tab('Xe ra')")
        evaluate("tab('Xe ra').click()")
        evaluate("input('Biển số xe'," + json.dumps(walkin_plate) + ")")
        evaluate("button('Tra phí & xử lý xe ra').click()")
        check("exit loads signed server quote", "!!button('Thanh toán & cho xe ra')||!!button('Kiểm tra & xác nhận xe ra')")
        evaluate("(button('Thanh toán & cho xe ra')||button('Kiểm tra & xác nhận xe ra')).click()")
        check("checkout dialog preserves explicit payment confirmation", "!!dialog()&&dialog().innerText.includes('Xem phí và xác nhận xe ra')&&!!dialog().querySelector('dl')")
        if evaluate("!!button('Đã thu tiền — cho xe ra',dialog())"):
            check("checkout blocked before cash acknowledgment", "button('Đã thu tiền — cho xe ra',dialog()).disabled")
            evaluate("dialog().querySelector('input[type=radio][value=cash]').click()")
            evaluate("dialog().querySelector('input[type=checkbox]').click()")
            evaluate("button('Đã thu tiền — cho xe ra',dialog()).click()")
        else:
            evaluate("starts('Xác nhận xe ra',dialog()).click()")
        check("walk-in checkout completed", "!dialog()")
        result = evaluate(f"api('/api/v2/sites/{args.site}/sessions?status=completed&license_plate={walkin_plate}').then(rows)")
        checks.append({"name": "server persisted completed paid-or-free stay", "passed": bool(result and result[0]["status"] == "completed" and result[0].get("parking_fee") is not None)})
        navigate("/history")
        check("history includes plate ticket and date filters", "!!field('Tìm đúng biển số')&&!!field('Mã vé (mã lượt)')&&!!field('Ngày vào từ')")
        evaluate("choose('Trạng thái lượt gửi','Đã ra')")
        evaluate("input('Tìm đúng biển số'," + json.dumps(walkin_plate) + ")")
        evaluate("button('Tìm lượt gửi').click()")
        check("completed walk-in discoverable in history", "text().includes(" + json.dumps(walkin_plate) + ")")

        # Renew a prepared card using a fresh future window; deactivate only its new period.
        navigate("/monthly-passes")
        check("monthly page loaded for lifecycle", "!!document.querySelector('[aria-label^=\"Gia hạn thẻ\"]')")
        selected_card = evaluate("document.querySelector('[aria-label^=\"Gia hạn thẻ\"]').getAttribute('aria-label').replace('Gia hạn thẻ ','')")
        evaluate("document.querySelector('[aria-label^=\"Gia hạn thẻ\"]').click()")
        check("monthly renewal keeps identity and old period", "!!dialog()&&field('Mã thẻ (NFC/RFID)',dialog()).disabled&&!!button('Gia hạn và ghi nhận thu',dialog())")
        latest_end = max((str(row["end_date"])[:10] for row in monthly_baseline if (row.get("card_code") or row.get("pass_code")) == selected_card), default="2026-09-23")
        from datetime import date, timedelta
        start = max(date.fromisoformat(latest_end) + timedelta(days=1), date.today() + timedelta(days=45))
        evaluate("input('Ngày bắt đầu'," + json.dumps(start.isoformat()) + ",dialog());input('Ngày hết hạn'," + json.dumps((start + timedelta(days=29)).isoformat()) + ",dialog())")
        evaluate("button('Gia hạn và ghi nhận thu',dialog()).click()")
        check("monthly renewal completes", "!dialog()")
        after_passes = evaluate("api('/api/v1/monthly-passes?limit=100').then(rows)")
        new_passes = [row for row in after_passes if row["id"] not in {p["id"] for p in monthly_baseline}]
        checks.append({"name": "renewal adds period and retains historical periods", "passed": len(new_passes) == 1 and all(p["id"] in {row["id"] for row in after_passes} for p in monthly_baseline)})
        if len(new_passes) != 1:
            raise AssertionError("Expected exactly one renewed period")
        new_id = new_passes[0]["id"]
        for _ in range(20):
            if evaluate("!!document.querySelector('[data-id=\"" + str(new_id) + "\"] [aria-label=\"Ngừng hoạt động kỳ vé\"]')"):
                break
            if not evaluate("!!document.querySelector('[aria-label=\"Go to next page\"]:not([disabled])')"):
                raise AssertionError("New monthly period not reachable in paginated table")
            evaluate("document.querySelector('[aria-label=\"Go to next page\"]').click();delay()")
        evaluate("document.querySelector('[data-id=\"" + str(new_id) + "\"] [aria-label=\"Ngừng hoạt động kỳ vé\"]').click()")
        check("monthly deactivation confirmation", "!!button('Xác nhận Hủy',dialog())")
        evaluate("button('Xác nhận Hủy',dialog()).click()")
        check("monthly deactivation returns to list", "!dialog()")
        remaining = evaluate("api('/api/v1/monthly-passes?limit=100').then(rows)")
        checks.append({"name": "deactivation preserves new period and old records", "passed": any(row["id"] == new_id and row.get("is_active") is False for row in remaining) and len(remaining) == len(after_passes)})
        call("Storage.clearDataForOrigin", {"origin": args.origin, "storageTypes": "all"})
        completed = True
except VisualComplete:
    completed = True
finally:
    proof = None
    chrome.terminate()
    try:
        chrome.wait(timeout=5)
    except subprocess.TimeoutExpired:
        chrome.kill(); chrome.wait(timeout=5)
    log.close()
    # Resolve and verify the one private helper directory before recursive cleanup.
    if PROFILE.resolve().parent == RUN.resolve() and RUN.resolve().is_relative_to((ROOT / "backend/artifacts/approved-demo-browser").resolve()):
        for _ in range(30):
            try:
                shutil.rmtree(PROFILE)
                break
            except FileNotFoundError:
                break
            except PermissionError:
                time.sleep(.1)
    report = {"passed": completed and all(row["passed"] for row in checks) and not http_errors and not runtime_errors and not blocked_external and not blocked_provider,
        "scope": "Real React/FastAPI on disposable synthetic local8793; cash is synthetic; AI unavailable response mocked; no provider calls",
        "checks": checks, "requests": requests, "http_errors": http_errors, "runtime_errors": runtime_errors,
        "blocked_external": blocked_external, "blocked_provider": blocked_provider, "private_browser_profile_removed": not PROFILE.exists()}
    (RUN / "result.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"passed": report["passed"], "checks": len(checks), "artifact_directory": str(RUN)}, ensure_ascii=True))
    if completed and not report["passed"]:
        raise AssertionError("Acceptance recorded a failure; inspect sanitized result.json")
