"""Compare the real local app with the approved prototype, using prepared synthetic accounts."""
import argparse
import base64
import json
from pathlib import Path
import shutil
import socket
import subprocess
import time
import urllib.parse
import urllib.request
from uuid import uuid4
from websockets.sync.client import connect

ROOT = Path(__file__).resolve().parents[3]
parser = argparse.ArgumentParser()
parser.add_argument("--credentials", type=Path, required=True)
parser.add_argument("--flows", action="store_true")
parser.add_argument("--fresh-mobile", action="store_true", help="Reload operations at the mobile viewport to diagnose resize-only scale retention")
parser.add_argument("--roles", nargs="+", default=["customer", "manager", "admin", "staff"], choices=["customer", "manager", "admin", "staff"])
args = parser.parse_args()
credentials = json.loads(args.credentials.read_text(encoding="utf-8"))
marker = json.loads(Path(credentials["database"] + ".demo.json").read_text(encoding="utf-8"))
if credentials.get("profile") != "single-lot-academic-v1" or marker.get("synthetic_history") is not True:
    raise ValueError("Prepared synthetic database is required")
ORIGIN = "http://127.0.0.1:8793"
OUT = ROOT / "backend/artifacts/prototype-real-comparison" / uuid4().hex[:10]
OUT.mkdir(parents=True)
PROFILE = OUT / "chrome-profile"
print(json.dumps({"artifacts": str(OUT)}, ensure_ascii=True), flush=True)
checks, errors, screenshots = [], [], []
completed = False
with socket.socket() as channel:
    channel.bind(("127.0.0.1", 0))
    port = channel.getsockname()[1]
log = (OUT / "browser.log").open("w", encoding="utf-8")
process = subprocess.Popen([r"C:\Program Files\Google\Chrome\Application\chrome.exe", "--headless=new", "--disable-gpu", "--no-first-run", "--no-default-browser-check", "--disable-background-networking", "--disable-component-update", "--disable-sync", "--remote-debugging-address=127.0.0.1", f"--remote-debugging-port={port}", "--user-data-dir=" + str(PROFILE), "about:blank"], stdout=log, stderr=log, creationflags=subprocess.CREATE_NO_WINDOW)
try:
    for _ in range(100):
        try:
            page = next(row for row in json.load(urllib.request.urlopen(f"http://127.0.0.1:{port}/json", timeout=1)) if row["type"] == "page")
            break
        except (OSError, StopIteration):
            time.sleep(.1)
    with connect(page["webSocketDebuggerUrl"], max_size=20_000_000) as ws:
        seq = 0
        def call(method, params=None):
            global seq
            seq += 1
            wanted = seq
            ws.send(json.dumps({"id": wanted, "method": method, "params": params or {}}))
            while True:
                result = json.loads(ws.recv(timeout=40))
                if result.get("method") == "Fetch.requestPaused":
                    paused = result["params"]
                    req = paused["request"]
                    parsed = urllib.parse.urlsplit(req["url"])
                    local = parsed.netloc == "127.0.0.1:8793"
                    ai = local and req["method"] == "POST" and ("/ai/" in parsed.path or parsed.path.endswith("/assistant"))
                    payment = any(part in parsed.path for part in ("payment-link", "/webhook", "/reconcile", "/simulate"))
                    allowed = (local and not payment) or parsed.scheme in {"data", "blob", "about"}
                    seq += 1
                    if ai:
                        body = json.dumps({"detail": "AI tạm tắt trong kiểm thử giao diện; chưa gọi mô hình."}, ensure_ascii=False)
                        command = {"id": seq, "method": "Fetch.fulfillRequest", "params": {"requestId": paused["requestId"], "responseCode": 503, "responseHeaders": [{"name": "Content-Type", "value": "application/json; charset=utf-8"}], "body": base64.b64encode(body.encode()).decode()}}
                    else:
                        command = {"id": seq, "method": "Fetch.continueRequest" if allowed else "Fetch.failRequest", "params": {"requestId": paused["requestId"], **({} if allowed else {"errorReason": "BlockedByClient"})}}
                    ws.send(json.dumps(command))
                if result.get("method") == "Runtime.exceptionThrown":
                    errors.append({"kind": "browser_runtime", "text": result["params"]["exceptionDetails"]["text"]})
                if result.get("id") == wanted:
                    if "error" in result:
                        raise RuntimeError(method)
                    return result.get("result", {})
        def js(source):
            result = call("Runtime.evaluate", {"expression": source, "returnByValue": True, "awaitPromise": True})
            if "exceptionDetails" in result:
                raise RuntimeError("Browser expression failed; private values withheld")
            return result.get("result", {}).get("value")
        def check(label, source):
            for _ in range(120):
                if js(source):
                    checks.append({"check": label, "passed": True})
                    return
                time.sleep(.1)
            checks.append({"check": label, "passed": False})
            raise AssertionError(label)
        def click(selector):
            js("document.querySelector(" + json.dumps(selector) + ").click()")
        def set_value(selector, value):
            js("(()=>{const e=document.querySelector(" + json.dumps(selector) + ");const proto=e.tagName==='SELECT'?HTMLSelectElement.prototype:e.tagName==='TEXTAREA'?HTMLTextAreaElement.prototype:HTMLInputElement.prototype;Object.getOwnPropertyDescriptor(proto,'value').set.call(e," + json.dumps(value) + ");e.dispatchEvent(new Event(e.tagName==='SELECT'?'change':'input',{bubbles:true}));})()")
        def navigate(path):
            call("Page.navigate", {"url": ORIGIN + path})
            check("page rendered " + path.split("?")[0], "document.readyState==='complete'&&!!document.querySelector('main h1')")
            js("new Promise(r=>setTimeout(r,250))")
        def screenshot(name, mobile=False):
            call("Emulation.setDeviceMetricsOverride", {"width": 390 if mobile else 1440, "height": 844 if mobile else 1000, "deviceScaleFactor": 1, "mobile": mobile})
            if args.fresh_mobile and name == "manager-operations-mobile":
                call("Page.reload")
                check("operations freshly loaded at mobile viewport", "!!document.querySelector('#operation-plate')")
            js("window.scrollTo(0,0)")
            js("new Promise(r=>setTimeout(r,300))")
            if js("location.pathname==='/login'||[...document.querySelectorAll('input[type=password]')].some(e=>e.value)||!!document.querySelector('.parking-ticket-dialog')"):
                raise RuntimeError("Private screenshot prevented")
            metrics = js("({innerWidth,scrollWidth:document.documentElement.scrollWidth,scale:visualViewport.scale,mainWidth:document.querySelector('main')?.getBoundingClientRect().width,panels:[...document.querySelectorAll('main .content-grid>.surface,main .content-grid>div>.surface')].map(e=>({width:e.getBoundingClientRect().width,x:e.getBoundingClientRect().x,y:e.getBoundingClientRect().y}))})")
            metrics["diagnostics"] = js("(()=>{const info=e=>{const r=e.getBoundingClientRect(),s=getComputedStyle(e);return {tag:e.tagName,class:e.className?.baseVal??e.className,x:r.x,y:r.y,right:r.right,width:r.width,scrollWidth:e.scrollWidth,clientWidth:e.clientWidth,minWidth:s.minWidth,cssWidth:s.width,overflowX:s.overflowX,display:s.display,flexWrap:s.flexWrap,position:s.position,clip:s.clip,columns:s.gridTemplateColumns}};return {overflow:[...document.querySelectorAll('body *')].filter(e=>{const r=e.getBoundingClientRect();return (!e.parentElement?.closest('.table-wrap,.MuiTableContainer-root,.sidebar')||e.classList.contains('sr-only'))&&r.width>0&&(r.right>document.documentElement.clientWidth+1||e.scrollWidth>e.clientWidth+1)}).slice(0,30).map(e=>({...info(e),parents:[e.parentElement,e.parentElement?.parentElement].filter(Boolean).map(info)})),splits:[...document.querySelectorAll('main .split')].map(e=>({...info(e),children:[...e.children].map(info)}))}})()")
            checks.append({"check": name + " viewport", "passed": metrics["scrollWidth"] <= (391 if mobile else 1441) and abs(metrics["scale"] - 1) < .02})
            screenshots.append({"file": name + ".png", "metrics": metrics})
            (OUT / (name + ".png")).write_bytes(base64.b64decode(call("Page.captureScreenshot", {"format": "png", "captureBeyondViewport": False})["data"]))
        def pair(name):
            screenshot(name + "-desktop")
            screenshot(name + "-mobile", True)
        def dialog_layout(label):
            layout = js("(()=>{const e=document.querySelector('[role=dialog] .prototype-ui'),d=document.querySelector('[role=dialog]');return e?{minHeight:parseFloat(getComputedStyle(e).minHeight),height:e.getBoundingClientRect().height,dialogHeight:d.getBoundingClientRect().height,viewportHeight:innerHeight}:null})()")
            checks.append({"check": label + " content-sized wrapper", "passed": bool(layout and layout["minHeight"] == 0), "layout": layout})
            if layout and layout["minHeight"] > 0:
                # One-variable diagnosis, restored immediately; never substitutes for a source fix.
                experiment = js("(()=>{const e=document.querySelector('[role=dialog] .prototype-ui'),old=e.style.minHeight;e.style.minHeight='0';const height=e.getBoundingClientRect().height;e.style.minHeight=old;return {height}})()")
                checks[-1]["zero_minimum_experiment"] = experiment
        def login(role):
            call("Storage.clearDataForOrigin", {"origin": ORIGIN, "storageTypes": "all"})
            call("Page.navigate", {"url": ORIGIN + "/login"})
            check(role + " login form", "!!document.querySelector('#username')&&!!document.querySelector('#password')")
            set_value("#username", role + "_demo")
            set_value("#password", credentials["accounts"][role + "_demo"])
            click("button[type=submit]")
            check(role + " authenticated", "location.pathname!=='/login'&&!!document.querySelector('main h1')")
        def api(path):
            return js("fetch(" + json.dumps("/api/v2" + path) + ",{headers:{Authorization:'Bearer '+localStorage.getItem('token')}}).then(r=>{if(!r.ok)throw Error('Read failed');return r.json()})")
        def rows(data):
            return data if isinstance(data, list) else data.get("items", [])
        call("Runtime.enable")
        call("Fetch.enable", {"patterns": [{"urlPattern": "*"}]})
        for role in args.roles:
            login(role)
            if role == "customer":
                for tab, path, title in (("fees", "/portal?tab=fees", "Tra phí & thanh toán"), ("booking", "/reservations", "Đặt chỗ trước"), ("tickets", "/portal?tab=tickets", "Vé & lịch sử"), ("support", "/portal?tab=support", "Bạn cần hỗ trợ?")):
                    navigate(path)
                    check(tab + " exact prototype heading", "document.querySelector('main h1')?.textContent===" + json.dumps(title))
                    check(tab + " two prototype panels", "document.querySelectorAll('main .content-grid .surface').length>=2")
                    pair("customer-" + tab)
                navigate("/portal?tab=fees")
                vehicles = rows(api("/me/vehicles"))
                sessions = rows(api("/me/sessions?limit=100"))
                active = next((s for s in sessions if s["status"] == "active" and any(v["license_plate"] == s["license_plate"] for v in vehicles)), None)
                if active:
                    vehicle = next(v for v in vehicles if v["license_plate"] == active["license_plate"])
                    set_value("#customer-plate", vehicle["license_plate"])
                    set_value("#customer-type", vehicle["vehicle_type_id"])
                    click("main form button[type=submit]")
                    check("own fee uses real active balance", "!!document.querySelector('.fee-total')")
                    pair("customer-fee-result")
                    if js("!!document.querySelector('.fee-panel button')"):
                        click(".fee-panel button")
                        check("payment opens existing quote workflow", "document.body.innerText.includes('Thanh toán phí lượt gửi')")
                        js("[...document.querySelectorAll('[role=dialog] button')].find(e=>e.textContent.trim()==='Đóng').click()")
                click('[aria-label="Mở trợ lý ParkingAI"]')
                check("public chat visible", "!!document.querySelector('#parking-chat-question')")
                pair("customer-chat")
                set_value("#parking-chat-question", "Còn bao nhiêu chỗ?")
                click('[aria-label="Gửi câu hỏi"]')
                check("public chat explicit no-provider error", "document.body.innerText.includes('AI tạm tắt trong kiểm thử giao diện')")
                click('[aria-label="Đóng trợ lý"]')
                if args.flows:
                    navigate("/reservations")
                    unique_plate = "DAT" + uuid4().hex[:6].upper()
                    set_value("#booking-plate", unique_plate)
                    click("main form button[type=submit]")
                    check("advance booking accepted without prepayment", "document.querySelector('.booking-row')?.parentElement.innerText.includes(" + json.dumps(unique_plate) + ")")
                    js("[...document.querySelectorAll('.booking-row')].find(e=>e.innerText.includes(" + json.dumps(unique_plate) + ")).querySelector('button').click()")
                    check("advance booking cancelled", "[...document.querySelectorAll('.booking-row')].find(e=>e.innerText.includes(" + json.dumps(unique_plate) + "))?.innerText.includes('Đã hủy')")
                    navigate("/portal?tab=support")
                    set_value("#support-message", "Kiểm thử giao diện đã phê duyệt; không phải yêu cầu thanh toán thật.")
                    click("main form button[type=submit]")
                    check("support submitted through actual API", "document.querySelector('main .inline-note.success')?.innerText.includes('Đã gửi yêu cầu')&&document.querySelector('.list-row')?.innerText.includes('Thanh toán & hoàn tiền')&&document.querySelector('.list-row .badge')?.innerText.includes('Chờ phản hồi')")
                    click(".list-row button")
                    check("support thread opens", "!!document.querySelector('#support-reply')")
                    pair("customer-support-dialog")
                    dialog_layout("support dialog")
                    set_value("#support-reply", "Đã kiểm tra trao đổi, đóng yêu cầu thử.")
                    click("[role=dialog] button[type=submit]")
                    check("support reply stored", "document.querySelector('[role=dialog]')?.innerText.includes('Đã kiểm tra trao đổi, đóng yêu cầu thử.')")
                    js("[...document.querySelectorAll('[role=dialog] button')].find(e=>e.textContent.trim()==='Đóng yêu cầu').click()")
                    check("support closed", "document.querySelector('[role=dialog]')?.innerText.includes('Yêu cầu đã đóng')")
                    js("[...document.querySelectorAll('[role=dialog] button')].find(e=>e.textContent.trim()==='Đóng').click()")
            else:
                paths = [("overview", "/", "Tổng quan"), ("operations", "/sites", "Vận hành bãi")]
                if role == "staff":
                    paths = [("operations", "/sites", "Vận hành bãi")]
                elif role == "admin":
                    paths += [("users", "/users", None), ("audit", "/audit-logs", None), ("configuration", "/site-settings", None)]
                for label, path, title in paths:
                    navigate(path)
                    if title:
                        check(role + " " + label + " heading", "document.querySelector('main h1')?.textContent.includes(" + json.dumps(title) + ")")
                    pair(role + "-" + label)
                if role == "manager":
                    js("[...document.querySelectorAll('main button')].find(e=>e.textContent.trim()==='Camera').click()")
                    check("camera configuration accessible", "document.querySelector('main').innerText.includes('camera')")
                    pair("manager-camera")
                    click('[aria-label="Mở trợ lý ParkingAI"]')
                    check("internal chat visible", "!!document.querySelector('#parking-chat-question')")
                    pair("manager-chat")
                    click('[aria-label="Đóng trợ lý"]')
                    navigate("/parking-slots")
                    pair("manager-lot")
                    for label, path in [("reports", "/reports"), ("monthly", "/monthly-passes"), ("types", "/vehicle-types"), ("prices", "/price-configs")]:
                        navigate(path)
                        pair("manager-" + label)
                    if args.fresh_mobile:
                        navigate("/sites")
                        call("Emulation.setDeviceMetricsOverride", {"width": 390, "height": 844, "deviceScaleFactor": 1, "mobile": True})
                        js("new Promise(r=>setTimeout(r,300))")
                        probe = {"before": js("({innerWidth,scrollWidth:document.documentElement.scrollWidth,scale:visualViewport.scale,hidden:[...document.querySelectorAll('.data-table .sr-only')].map(e=>({x:e.getBoundingClientRect().x,right:e.getBoundingClientRect().right,width:e.getBoundingClientRect().width,position:getComputedStyle(e).position,clip:getComputedStyle(e).clip,parentPosition:getComputedStyle(e.parentElement).position}))})")}
                        js("document.querySelectorAll('.data-table .sr-only').forEach(e=>e.parentElement.style.position='relative')")
                        call("Emulation.resetPageScaleFactor")
                        js("new Promise(r=>setTimeout(r,300))")
                        probe["positioned_header_experiment"] = js("({innerWidth,scrollWidth:document.documentElement.scrollWidth,scale:visualViewport.scale})")
                        (OUT / "mobile-probe.json").write_text(json.dumps(probe, indent=2), encoding="utf-8")
                    if args.flows:
                        navigate("/sites")
                        walkin_plate = "UAT" + uuid4().hex[:6].upper()
                        check("manual native entry ready", "!!document.querySelector('#operation-plate')&&!!document.querySelector('#operation-type')")
                        type_data = api("/catalog/vehicle-types")
                        type_rows = rows(type_data)
                        type_id = str(next(row["id"] for row in type_rows if row.get("requires_plate", True) and row.get("is_active", True)))
                        set_value("#operation-type", type_id)
                        set_value("#operation-plate", walkin_plate)
                        click("main form button[type=submit]")
                        check("walk-in enters without a booking", "document.querySelector('main').innerText.includes('Đã ghi nhận xe vào')&&document.querySelector('main').innerText.includes(" + json.dumps(walkin_plate) + ")")
                        stays = rows(api("/sites/1/sessions?status=active&license_plate=" + walkin_plate))
                        stay = next((row for row in stays if row["license_plate"] == walkin_plate), None)
                        if not stay:
                            raise AssertionError("Created walk-in was not returned by authenticated server read")
                        ticket = api("/sites/1/sessions/" + str(stay["id"]) + "/ticket")
                        proof = ticket.get("payment_access_code")
                        if not proof:
                            raise AssertionError("Issued ticket did not contain private payment proof")
                        login("customer")
                        navigate("/portal?tab=fees")
                        check("customer fee form after reauthentication", "!!document.querySelector('#customer-type')")
                        set_value("#customer-plate", walkin_plate)
                        set_value("#customer-type", type_id)
                        js("[...document.querySelectorAll('main button')].find(e=>e.textContent.trim()==='Dùng mã trên vé').click()")
                        set_value("#ticket", proof)
                        js("[...document.querySelectorAll('main button')].find(e=>e.textContent.trim()==='Xác nhận vé').click()")
                        check("private ticket opens walk-in fee only", "!!document.querySelector('.fee-total')")
                        check("private proof removed after lookup", "!document.querySelector('#ticket')&&!location.href.includes('PAP1')")
                        proof = None
                        ticket = None
                        check("walk-in fee is positive", "Number(document.querySelector('.fee-total')?.textContent.replace(/[^0-9]/g,''))>0&&!!document.querySelector('.fee-panel button')")
                        click(".fee-panel button")
                        check("positive fee uses established quote flow", "document.querySelector('[role=dialog]')?.innerText.includes('Thanh toán phí lượt gửi')")
                        check("payment balance loaded", "document.querySelector('[role=dialog]')?.innerText.includes('Tổng phí hiện tại')")
                        pair("customer-payment-dialog")
                        dialog_layout("customer payment dialog")
                        check("unconfigured bank is never labelled paid", "!document.querySelector('[role=dialog]')?.innerText.includes('Đã thanh toán thành công')")
                        js("[...document.querySelectorAll('[role=dialog] button')].find(e=>e.textContent.trim()==='Đóng').click()")
                        login("manager")
                        navigate("/sites")
                        js("[...document.querySelectorAll('main button')].find(e=>e.textContent.trim()==='Xe ra').click()")
                        set_value("#operation-query", walkin_plate)
                        click("main form button[type=submit]")
                        check("manual exit loads server quote", "!![...document.querySelectorAll('main button')].find(e=>['Thu tiền mặt','Ghi nhận xe ra'].includes(e.textContent.trim()))")
                        js("[...document.querySelectorAll('main button')].find(e=>['Thu tiền mặt','Ghi nhận xe ra'].includes(e.textContent.trim())).click()")
                        check("signed checkout dialog ready", "!!document.querySelector('[role=dialog] dl')")
                        cash = js("!![...document.querySelectorAll('[role=dialog] button')].find(e=>e.textContent.trim()==='Đã thu tiền — cho xe ra')")
                        checks.append({"check": "positive walk-in requires cash collection", "passed": cash})
                        if cash:
                            check("cash requires explicit received confirmation", "[...document.querySelectorAll('[role=dialog] button')].find(e=>e.textContent.trim()==='Đã thu tiền — cho xe ra').disabled")
                            click("[role=dialog] input[type=checkbox]")
                            js("[...document.querySelectorAll('[role=dialog] button')].find(e=>e.textContent.trim()==='Đã thu tiền — cho xe ra').click()")
                        else:
                            js("[...document.querySelectorAll('[role=dialog] button')].find(e=>e.textContent.trim().startsWith('Xác nhận xe ra')).click()")
                        check("walk-in checkout completes", "!document.querySelector('[role=dialog]')")
                        ended = rows(api("/sites/1/sessions?status=completed&license_plate=" + walkin_plate))
                        checks.append({"check": "server confirms paid or free completed stay", "passed": any(row["id"] == stay["id"] and row["status"] == "completed" and row.get("parking_fee") is not None for row in ended)})
        completed = all(row["passed"] for row in checks) and not errors
finally:
    process.terminate()
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        process.kill(); process.wait(timeout=5)
    log.close()
    if PROFILE.resolve().parent == OUT.resolve() and OUT.resolve().is_relative_to((ROOT / "backend/artifacts/prototype-real-comparison").resolve()):
        for _ in range(30):
            try:
                shutil.rmtree(PROFILE); break
            except FileNotFoundError:
                break
            except PermissionError:
                time.sleep(.1)
    result = {"origin": ORIGIN, "complete": completed, "checks": checks, "screenshots": screenshots, "runtime_errors": errors, "private_profile_removed": not PROFILE.exists()}
    (OUT / "result.json").write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps({"artifacts": str(OUT), "screenshots": len(screenshots), "passed": sum(x["passed"] for x in checks), "checks": len(checks), "complete": completed}, ensure_ascii=True), flush=True)

if not completed:
    raise SystemExit(1)
