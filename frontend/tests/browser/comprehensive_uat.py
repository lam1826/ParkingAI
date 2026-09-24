"""Honest acceptance matrix on marked synthetic localhost8793. No provider calls.

Each route/function keeps its own PASS/FAIL/BLOCKED/NOT_RUN result. Browser
failures are retained rather than aborting unrelated cases. Passwords/tokens and
private payment proof are never included in results or screenshots.
"""
import argparse
import base64
from datetime import date, timedelta
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
ORIGIN = "http://127.0.0.1:8793"
parser = argparse.ArgumentParser()
parser.add_argument("--credentials", required=True, type=Path)
parser.add_argument("--mode", choices=["baseline", "routes", "functional", "followup", "anchors"], default="routes")
parser.add_argument("--skip-auth", action="store_true", help="Resume business checks without creating another public account; auth case stays NOT_RUN in this run")
parser.add_argument("--records", type=Path, help="Non-secret synthetic-records.json from a previous functional run, for a bounded follow-up")
args = parser.parse_args()
credentials = json.loads(args.credentials.read_text(encoding="utf-8"))
marker = json.loads(Path(credentials["database"] + ".demo.json").read_text(encoding="utf-8"))
if credentials.get("profile") != "single-lot-academic-v1" or marker.get("synthetic_history") is not True:
    raise ValueError("Marked synthetic database required")
OUT = ROOT / "backend/artifacts/comprehensive-uat" / uuid4().hex[:10]
OUT.mkdir(parents=True)
PROFILE = OUT / "chrome-profile"
print(json.dumps({"artifacts": str(OUT), "mode": args.mode}, ensure_ascii=True), flush=True)
checks, requests, errors, console_errors, blocked, screenshots = [], [], [], [], [], []
current = "startup"
completed = False
with socket.socket() as channel:
    channel.bind(("127.0.0.1", 0))
    port = channel.getsockname()[1]
log = (OUT / "browser.log").open("w", encoding="utf-8")
process = subprocess.Popen([r"C:\Program Files\Google\Chrome\Application\chrome.exe", "--headless=new", "--disable-gpu", "--no-first-run", "--no-default-browser-check", "--disable-background-networking", "--disable-component-update", "--disable-sync", "--remote-debugging-address=127.0.0.1", f"--remote-debugging-port={port}", "--user-data-dir=" + str(PROFILE), "about:blank"], stdout=log, stderr=log, creationflags=subprocess.CREATE_NO_WINDOW)
try:
    for _ in range(100):
        try:
            target = next(row for row in json.load(urllib.request.urlopen(f"http://127.0.0.1:{port}/json", timeout=1)) if row["type"] == "page")
            break
        except (OSError, StopIteration):
            time.sleep(.1)
    with connect(target["webSocketDebuggerUrl"], max_size=20_000_000) as ws:
        sequence = 0
        def call(method, params=None):
            global sequence
            sequence += 1
            wanted = sequence
            ws.send(json.dumps({"id": wanted, "method": method, "params": params or {}}))
            while True:
                result = json.loads(ws.recv(timeout=45))
                event = result.get("method")
                payload = result.get("params", {})
                if event == "Fetch.requestPaused":
                    req = payload["request"]
                    url = urllib.parse.urlsplit(req["url"])
                    local = url.netloc == "127.0.0.1:8793"
                    provider = req["method"] == "POST" and ("/ai/" in url.path or url.path.endswith("/assistant") or any(p in url.path for p in ("payment-link", "/webhook", "/reconcile", "/simulate")))
                    allowed = (local and not provider) or url.scheme in {"data", "blob", "about"}
                    if not allowed:
                        blocked.append({"case": current, "path": url.path, "host": url.hostname, "provider": provider})
                    sequence += 1
                    ws.send(json.dumps({"id": sequence, "method": "Fetch.continueRequest" if allowed else "Fetch.failRequest", "params": {"requestId": payload["requestId"], **({} if allowed else {"errorReason": "BlockedByClient"})}}))
                if event == "Network.requestWillBeSent":
                    req = payload["request"]
                    url = urllib.parse.urlsplit(req["url"])
                    if url.netloc == "127.0.0.1:8793":
                        requests.append({"case": current, "method": req["method"], "path": url.path})
                if event == "Network.responseReceived":
                    response = payload["response"]
                    if response["status"] >= 400:
                        errors.append({"case": current, "kind": "http", "status": response["status"], "path": urllib.parse.urlsplit(response["url"]).path})
                if event == "Runtime.exceptionThrown":
                    errors.append({"case": current, "kind": "runtime", "text": payload["exceptionDetails"]["text"]})
                if event == "Runtime.consoleAPICalled" and payload.get("type") == "error":
                    known_labels={"Login failed:","Không tìm thấy tài nguyên (404)!","Lỗi phân quyền: Bạn không có quyền thao tác!","Lỗi máy chủ nội bộ (500)!","Lỗi kết nối mạng. Không thể liên lạc với máy chủ."}
                    first=(payload.get("args") or [{}])[0].get("value")
                    console_errors.append({"case": current, "kind": "console_error", "label":first if isinstance(first,str) and first in known_labels else "Unclassified console error; values withheld", "argument_types": [a.get("type") for a in payload.get("args", [])]})
                if event == "Page.javascriptDialogOpening":
                    sequence += 1
                    ws.send(json.dumps({"id": sequence, "method": "Page.handleJavaScriptDialog", "params": {"accept": args.mode in {"functional","followup"}}}))
                if result.get("id") == wanted:
                    if "error" in result:
                        raise RuntimeError("Browser command failed: " + method)
                    return result.get("result", {})
        def js(source):
            result = call("Runtime.evaluate", {"expression": source, "returnByValue": True, "awaitPromise": True})
            if "exceptionDetails" in result:
                raise RuntimeError("Browser expression failed; private values withheld")
            return result.get("result", {}).get("value")
        def wait(source, timeout=10):
            start = time.monotonic()
            while time.monotonic() - start < timeout:
                if js(source):
                    return True
                time.sleep(.1)
            return False
        def record(name, passed, **evidence):
            checks.append({"case": current, "check": name, "status": "PASS" if passed else "FAIL", **evidence})
            return passed
        def require(name, source, timeout=10):
            if not record(name, wait(source, timeout)):
                raise AssertionError(name)
        def api(path):
            return js("fetch("+json.dumps(path)+",{headers:{Authorization:'Bearer '+localStorage.getItem('token')}}).then(async r=>({status:r.status,data:await r.json()}))")
        def rows(path):
            data = api(path)["data"]
            return data if isinstance(data, list) else data.get("items", [])
        def click(label, scope="document"):
            if not wait("(()=>{const s="+scope+";return !!s&&[...s.querySelectorAll('button,a')].some(e=>e.textContent.trim()==="+json.dumps(label)+"&&!e.disabled)})()"):
                raise AssertionError("Missing or disabled button: "+label)
            js("[..."+scope+".querySelectorAll('button,a')].find(e=>e.textContent.trim()==="+json.dumps(label)+").click()")
        def fill(name, value):
            set_value(':is(input,textarea,select)[name="'+name+'"]', value)
        def fill_label(label, value):
            field_id=js("[...document.querySelectorAll('main label')].find(e=>e.textContent.replace('*','').trim()==="+json.dumps(label)+")?.htmlFor")
            if not field_id:raise AssertionError("Label field absent: "+label)
            set_value("[id="+json.dumps(field_id)+"]",value)
        def choose(name, value):
            if not wait("!!document.querySelector('[name="+name+"]')"):
                raise AssertionError("Missing select: "+name)
            if js("document.querySelector('[name="+name+"]')?.tagName==='SELECT'"):
                fill(name, value)
            else:
                js("document.querySelector('[name="+name+"]').parentElement.querySelector('[role=combobox]').dispatchEvent(new MouseEvent('mousedown',{bubbles:true}))")
                if not wait("!!document.querySelector('[role=option][data-value=\""+str(value)+"\"]')"):
                    raise AssertionError("selection option missing")
                js("document.querySelector('[role=option][data-value=\""+str(value)+"\"]').click()")
                if not wait("!document.querySelector('[role=listbox]')&&document.querySelector('[name="+name+"]').value==="+json.dumps(str(value))):
                    raise AssertionError("Selection did not settle: "+name)
        def row_action(text, action):
            source="(()=>{const r=[...document.querySelectorAll('main tbody tr')].find(e=>e.textContent.includes("+json.dumps(text)+"));return !!r&&[...r.querySelectorAll('button')].some(e=>e.textContent.trim()==="+json.dumps(action)+"&&!e.disabled)})()"
            if not wait(source):raise AssertionError("Table action absent: "+action)
            js("(()=>{const r=[...document.querySelectorAll('main tbody tr')].find(e=>e.textContent.includes("+json.dumps(text)+"));const details=r.closest('details');if(details&&!details.open)details.querySelector('summary').click();[...r.querySelectorAll('button')].find(e=>e.textContent.trim()==="+json.dumps(action)+").click()})()")
        def search_table(value):
            selector = js("(()=>{const e=document.querySelector('main input[aria-label^=\"Tìm\"]');if(!e)return null;return '[aria-label='+JSON.stringify(e.getAttribute('aria-label'))+']'})()")
            if selector:
                set_value(selector,value)
        def run_case(name, action):
            global current
            current = name
            before=len(checks)
            try:
                action()
            except Exception as failure:
                context=js("({path:location.pathname,labels:[...document.querySelectorAll('main label')].map(e=>e.textContent),buttons:[...document.querySelectorAll('main button')].map(e=>e.textContent.trim()).slice(0,40),alerts:[...document.querySelectorAll('[role=alert]')].map(e=>e.textContent)})")
                record("case completed", False, reason=type(failure).__name__+": "+str(failure),context=context)
                try:screenshot("failed-"+str(len(checks)))
                except RuntimeError:pass
            print(json.dumps({"case":name,"pass":sum(r["status"]=="PASS" for r in checks[before:]),"fail":sum(r["status"]=="FAIL" for r in checks[before:])},ensure_ascii=True),flush=True)
        def expected_http(path, status, reason):
            found=next((row for row in reversed(errors) if row.get("kind")=="http" and row.get("path")==path and row.get("status")==status and not row.get("expected")),None)
            record("expected negative HTTP response",found is not None,path=path,http_status=status,reason=reason)
            if found:found.update(expected=True,reason=reason)
            console_label="Login failed:" if path=="/api/auth/login" and status==400 else "Không tìm thấy tài nguyên (404)!" if status==404 else None
            console=next((row for row in reversed(console_errors) if row["case"]==current and row.get("label")==console_label and not row.get("expected")),None)
            if found and console:console.update(expected=True,reason=reason)
        def set_value(selector, value):
            if not wait("!!document.querySelector("+json.dumps(selector)+")"):
                raise AssertionError("Missing input: "+selector)
            js("(()=>{const e=document.querySelector("+json.dumps(selector)+");const p=e.tagName==='SELECT'?HTMLSelectElement.prototype:e.tagName==='TEXTAREA'?HTMLTextAreaElement.prototype:HTMLInputElement.prototype;Object.getOwnPropertyDescriptor(p,'value').set.call(e,"+json.dumps(value)+");e.dispatchEvent(new Event(e.tagName==='SELECT'?'change':'input',{bubbles:true}));})()")
        def navigate(path):
            call("Page.navigate", {"url": ORIGIN + path})
            if not wait("document.readyState==='complete'&&!!document.querySelector('main')"):
                raise AssertionError("main route did not render")
            js("new Promise(r=>setTimeout(r,350))")
        def login(role):
            global current
            current = role + " login"
            call("Storage.clearDataForOrigin", {"origin": ORIGIN, "storageTypes": "all"})
            call("Page.navigate", {"url": ORIGIN + "/login"})
            if not wait("!!document.querySelector('#username')&&!!document.querySelector('#password')"):
                raise AssertionError("login form absent")
            set_value("#username", role + "_demo")
            set_value("#password", credentials["accounts"][role + "_demo"])
            js("document.querySelector('button[type=submit]').click()")
            if not record("login real credentials", wait("location.pathname!=='/login'&&!!document.querySelector('main')")):
                raise AssertionError("Login failed")
        def login_person(username, password):
            call("Storage.clearDataForOrigin", {"origin": ORIGIN, "storageTypes": "all"})
            call("Page.navigate", {"url": ORIGIN + "/login"})
            if not wait("!!document.querySelector('#username')"):
                raise AssertionError("login form absent")
            set_value("#username", username)
            set_value("#password", password)
            js("document.querySelector('button[type=submit]').click()")
            require("disposable account real login", "location.pathname!=='/login'&&!!document.querySelector('main')")
        def screenshot(name, mobile=False):
            call("Emulation.setDeviceMetricsOverride", {"width": 390 if mobile else 1440, "height": 844 if mobile else 1000, "deviceScaleFactor": 1, "mobile": mobile})
            js("window.scrollTo(0,0);new Promise(r=>setTimeout(r,180))")
            if js("location.pathname==='/login'||[...document.querySelectorAll('input[type=password]')].some(e=>e.value)||!!document.querySelector('.parking-ticket-dialog')"):
                raise RuntimeError("Private screenshot prevented")
            metrics = js("({innerWidth,width:document.documentElement.scrollWidth,scale:visualViewport.scale})")
            record(name + " viewport", metrics["width"] <= (391 if mobile else 1441) and abs(metrics["scale"]-1)<.02, metrics=metrics)
            (OUT / (name+".png")).write_bytes(base64.b64decode(call("Page.captureScreenshot", {"format": "png", "captureBeyondViewport": False})["data"]))
            screenshots.append(name+".png")
        def contrast_probe(selector="a.MuiButton-contained[href='/profile']",label="profile link",filename="account-contrast.json"):
            js("document.querySelector("+json.dumps(selector)+")?.scrollIntoView({block:'center'});new Promise(r=>setTimeout(r,200))")
            call("Input.dispatchMouseEvent", {"type":"mouseMoved","x":0,"y":0})
            source = """(()=>{const e=document.querySelector(SELECTOR);if(!e)return null;const s=getComputedStyle(e),rgb=v=>v.match(/[0-9.]+/g).slice(0,3).map(Number),lum=v=>rgb(v).map(x=>x/255).map(x=>x<=.04045?x/12.92:((x+.055)/1.055)**2.4).reduce((a,x,i)=>a+x*[.2126,.7152,.0722][i],0),a=lum(s.color),b=lum(s.backgroundColor),r=e.getBoundingClientRect();return {text:e.textContent,color:s.color,background:s.backgroundColor,contrast:(Math.max(a,b)+.05)/(Math.min(a,b)+.05),hovered:e.matches(':hover'),fontSize:s.fontSize,rect:{x:r.x,y:r.y,width:r.width,height:r.height},matchedRules:[...document.styleSheets].flatMap(ss=>{try{return [...ss.cssRules]}catch{return []}}).filter(rule=>rule.selectorText&&e.matches(rule.selectorText)&&rule.style?.color).map(rule=>({selector:rule.selectorText,color:rule.style.color}))}})()""".replace("SELECTOR", json.dumps(selector))
            probe = {"normal": js(source)}
            if probe["normal"]:
                r = probe["normal"]["rect"]
                call("Input.dispatchMouseEvent", {"type": "mouseMoved", "x": r["x"]+r["width"]/2, "y": r["y"]+r["height"]/2})
                js("new Promise(r=>setTimeout(r,300))")
                probe["hover"] = js(source)
                record(label+" text contrast >=4.5 normal", probe["normal"]["contrast"] >= 4.5, probe=probe["normal"])
                record(label+" text contrast >=4.5 hover", probe["hover"]["contrast"] >= 4.5 and probe["hover"]["hovered"], probe=probe["hover"])
            else:
                record(label+" found", False)
            (OUT / filename).write_text(json.dumps(probe, ensure_ascii=False, indent=2), encoding="utf-8")
        call("Network.enable")
        call("Page.enable")
        call("Runtime.enable")
        call("Fetch.enable", {"patterns": [{"urlPattern": "*"}]})
        call("Emulation.setDeviceMetricsOverride", {"width": 1440, "height": 1000, "deviceScaleFactor": 1, "mobile": False})
        login("admin")
        current = "admin /account baseline"
        navigate("/account")
        contrast_probe()
        screenshot("admin-account-desktop")
        screenshot("admin-account-mobile", True)
        if args.mode=="anchors":
            current="admin primary navigation link"
            call("Emulation.setDeviceMetricsOverride", {"width":1440,"height":1000,"deviceScaleFactor":1,"mobile":False})
            navigate("/")
            contrast_probe("main a.button.primary","native primary link","native-primary-contrast.json")
            nav=js("({inactive:getComputedStyle(document.querySelector('.sidebar a.nav-item:not(.active)')).color,active:getComputedStyle(document.querySelector('.sidebar a.nav-item.active')).color})")
            record("sidebar inactive and active colors preserve prototype",nav=={"inactive":"rgb(80, 96, 116)","active":"rgb(23, 103, 189)"},colors=nav)
            screenshot("native-primary-home")
            screenshot("native-primary-home-mobile",True)
            login("customer");navigate("/portal?tab=tickets")
            js("[...document.querySelectorAll('main details')].find(e=>e.querySelector('a.button.secondary')).querySelector('summary').click()")
            contrast_probe("main a.button.secondary","native secondary link","native-secondary-contrast.json")
            colors=js("({color:getComputedStyle(document.querySelector('main a.button.secondary')).color})")
            record("secondary link preserves prototype ink",colors["color"]=="rgb(51, 75, 101)",colors=colors)
            screenshot("native-secondary-customer")
        if args.mode == "routes":
            internal = ["/", "/sites", "/history", "/parking-slots", "/zones", "/vehicle-types", "/price-configs", "/customers", "/vehicles", "/monthly-passes", "/reports", "/ai", "/finance", "/users", "/roles", "/site-settings", "/audit-logs", "/portal-admin", "/vision", "/occupancy", "/insights", "/sessions", "/account", "/profile", "/settings"]
            for role in ("admin", "manager", "staff", "customer"):
                login(role)
                paths = internal if role in {"admin", "staff"} else (["/account", "/profile", "/settings", "/users", "/site-settings", "/reports", "/ai"] if role == "manager" else ["/portal?tab=fees", "/reservations", "/portal?tab=tickets", "/portal?tab=support", "/account", "/profile", "/settings", "/sites", "/users", "/reports"])
                for path in paths:
                    current = role + " " + path
                    try:
                        before = len(errors)
                        navigate(path)
                        info = js("({path:location.pathname,title:document.querySelector('main h1,main h5')?.textContent,mainLength:document.querySelector('main')?.innerText.length,alerts:[...document.querySelectorAll('main [role=alert],main .form-error')].map(e=>e.innerText),buttons:[...document.querySelectorAll('main button')].filter(e=>e.getBoundingClientRect().width).map(e=>e.innerText.trim()).slice(0,35),denied:document.querySelector('main')?.innerText.includes('Bạn không có quyền truy cập chức năng này.')})")
                        denied = (role == "customer" and path in {"/sites", "/users", "/reports"}) or (role == "staff" and path in {"/users", "/roles", "/site-settings", "/audit-logs", "/portal-admin"})
                        record("route boundary or meaningful loaded content", info["denied"] if denied else info["mainLength"] > 30 and not info["denied"], evidence=info)
                        record("route no HTTP/runtime failure", len(errors) == before, errors=errors[before:])
                        stem = role + "-" + path.strip("/").replace("?", "-").replace("=", "-").replace("&", "-")
                        screenshot(stem + "-desktop")
                        screenshot(stem + "-mobile", True)
                    except Exception as failure:
                        record("route harness completed", False, reason=type(failure).__name__ + ": " + str(failure))
                print(json.dumps({"role": role, "checks": len(checks), "fail": sum(r["status"]=="FAIL" for r in checks)}, ensure_ascii=True), flush=True)
        if args.mode == "functional":
            tag = uuid4().hex[:6].upper()
            state = {"tag": tag}
            call("Emulation.setDeviceMetricsOverride", {"width":1440,"height":1000,"deviceScaleFactor":1,"mobile":False})
            def account_flow():
                username="uat_profile_"+tag.lower()
                password="Uat!"+uuid4().hex
                updated_password="Uat!"+uuid4().hex
                call("Storage.clearDataForOrigin", {"origin":ORIGIN,"storageTypes":"all"})
                call("Page.navigate", {"url":ORIGIN+"/register"})
                require("registration form", "!!document.querySelector('[name=username]')")
                for name,value in {"username":username,"full_name":"SYNTHETIC UAT "+tag,"password":password,"confirm_password":password}.items(): fill(name,value)
                js("document.querySelector('button[type=submit]').click()")
                require("public customer registration completed", "location.pathname==='/login'")
                login_person(username,password)
                navigate("/account")
                require("account has profile navigation", "!!document.querySelector('a[href=\"/profile\"]')")
                js("document.querySelector('main a[href=\"/profile\"]').click()")
                require("profile navigation works", "location.pathname==='/profile'&&!!document.querySelector('[name=full_name]')")
                fill("full_name","SYNTHETIC UAT Edited "+tag)
                click("Lưu thay đổi")
                require("profile update UI success", "document.querySelector('main').innerText.includes('Cập nhật hồ sơ thành công')")
                record("profile persisted from actual auth API",api("/api/auth/me")["data"]["full_name"]=="SYNTHETIC UAT Edited "+tag)
                navigate("/settings")
                for name,value in {"current_password":password,"new_password":updated_password,"confirm_password":"Mismatch123!"}.items(): fill(name,value)
                click("Đổi mật khẩu")
                require("password confirmation mismatch explicit", "document.querySelector('main').innerText.includes('Mật khẩu xác nhận không khớp')")
                fill("confirm_password",updated_password)
                click("Đổi mật khẩu")
                require("change password real success", "document.querySelector('main').innerText.includes('Đổi mật khẩu thành công')")
                js("sessionStorage.setItem('parking_ai_chat_messages','[]')")
                click("Xóa lịch sử chatbot")
                record("clear local chat storage",js("sessionStorage.getItem('parking_ai_chat_messages')===null"))
                click("Đăng xuất")
                require("logout removes local credentials", "location.pathname==='/login'&&!localStorage.getItem('token')")
                login_person(username,updated_password)
                navigate("/sites")
                require("new customer cannot use operations", "document.querySelector('main').innerText.includes('Bạn không có quyền')")
                state["registered_user"] = username
            if args.skip_auth:
                checks.append({"case":"AUTH","check":"disposable registration profile password logout permissions","status":"NOT_RUN","reason":"Explicit business-only rerun; earlier auth artifacts retained separately"})
            else:
                run_case("AUTH disposable registration profile password logout permissions",account_flow)
            login("manager")
            def create_catalog():
                navigate("/zones"); click("Thêm khu vực")
                fill("name","SYNTHETIC UAT "+tag); fill("capacity",2); click("Lưu thay đổi")
                require("zone create closes editor","!document.querySelector('.core-editor')")
                state["zone"]=next(r for r in rows("/api/v1/zones?limit=100") if r["name"]=="SYNTHETIC UAT "+tag)
                row_action(state["zone"]["name"],"Sửa"); fill("name","SYNTHETIC UAT Edit "+tag); click("Lưu thay đổi")
                require("zone edit persisted in list","document.querySelector('main').innerText.includes('SYNTHETIC UAT Edit "+tag+"')&&!document.querySelector('.core-editor')")
                state["zone"]["name"]="SYNTHETIC UAT Edit "+tag
                navigate("/vehicle-types"); click("Thêm loại xe")
                fill("name","UAT TYPE "+tag); fill("description","Synthetic test record"); fill("code_prefix","U"+tag); click("Lưu thay đổi")
                require("vehicle type create closes editor","!document.querySelector('.core-editor')")
                state["type"]=next(r for r in rows("/api/v1/vehicle-types?limit=100") if r["name"]=="UAT TYPE "+tag)
                row_action(state["type"]["name"],"Sửa"); fill("description","Edited synthetic test record"); click("Lưu thay đổi")
                require("vehicle type edit persisted","!document.querySelector('.core-editor')&&document.querySelector('main').innerText.includes('Edited synthetic test record')")
                navigate("/parking-slots"); click("Thêm vị trí đỗ")
                fill("slot_name","UT"+tag); fill("zone_id",state["zone"]["id"]); fill("vehicle_type_id",state["type"]["id"]); click("Lưu thay đổi")
                require("named parking slot create","!document.querySelector('.core-editor')&&document.querySelector('main').innerText.includes('UT"+tag+"')")
                state["slot"]=next(r for r in rows("/api/v1/parking-slots?limit=100") if r["slot_name"]=="UT"+tag)
                row_action("UT"+tag,"Sửa"); fill("slot_name","UT"+tag+"E"); click("Lưu thay đổi")
                require("parking slot edit","!document.querySelector('.core-editor')&&document.querySelector('main').innerText.includes('UT"+tag+"E')")
                state["slot"]["slot_name"]="UT"+tag+"E"
                navigate("/price-configs"); click("Thêm bảng giá")
                for n,v in {"vehicle_type_id":state["type"]["id"],"ticket_type":"HOURLY","price":1234,"effective_date":date.today().isoformat()}.items(): fill(n,v)
                click("Lưu thay đổi"); require("price create closes editor","!document.querySelector('.core-editor')")
                state["price"]=next(r for r in rows("/api/v1/price-configs?limit=100") if r["vehicle_type_id"]==state["type"]["id"])
                row_action(state["type"]["name"],"Sửa"); fill("price",2345); click("Lưu thay đổi")
                require("price edit closes editor","!document.querySelector('.core-editor')")
                record("actual persisted hourly price",next(r for r in rows("/api/v1/price-configs?limit=100") if r["id"]==state["price"]["id"])["price"]==2345)
                screenshot("functional-catalog-price")
                navigate("/zones"); row_action(state["zone"]["name"],"Xóa")
                require("zone linked to slot deletion refused","document.body.innerText.includes('Không thể xóa khu vực')||document.body.innerText.includes('đang chứa')||document.body.innerText.includes('đang có')")
                expected_http("/api/v1/zones/"+str(state["zone"]["id"]),409,"Deliberate delete of synthetic zone with child slot; reference guard must refuse")
                record("zone remains after refused deletion",any(r["id"]==state["zone"]["id"] for r in rows("/api/v1/zones?limit=100")))
            run_case("CATALOG zone type slot price UI create edit and reference guard",create_catalog)
            def customers_monthly():
                navigate("/customers"); click("Thêm khách hàng")
                for n,v in {"full_name":"SYNTHETIC CUSTOMER "+tag,"phone_number":"090"+str(int(tag,16)).zfill(7)[-7:],"email":"uat-"+tag.lower()+"@example.com"}.items(): fill(n,v)
                click("Lưu thay đổi"); require("customer create closes editor","!document.querySelector('.core-editor')")
                state["customer"]=next(r for r in rows("/api/v1/customers?limit=100") if r["full_name"]=="SYNTHETIC CUSTOMER "+tag)
                search_table("SYNTHETIC CUSTOMER "+tag); row_action("SYNTHETIC CUSTOMER "+tag,"Sửa"); fill("full_name","SYNTHETIC CUSTOMER Edited "+tag); click("Lưu thay đổi")
                require("customer edit closes editor","!document.querySelector('.core-editor')")
                state["customer"]["full_name"]="SYNTHETIC CUSTOMER Edited "+tag
                navigate("/vehicles"); click("Thêm phương tiện")
                require("vehicle editor open","!!document.querySelector('[name=license_plate]')")
                fill("license_plate","UT"+tag); choose("vehicle_type_id",state["type"]["id"]); choose("customer_id",state["customer"]["id"]); click("Thêm mới")
                require("vehicle create closes editor","!document.querySelector('.core-editor')")
                state["vehicle"]=next(r for r in rows("/api/v1/vehicles?limit=100") if r["license_plate"]=="UT"+tag)
                search_table("UT"+tag); row_action("UT"+tag,"Sửa"); fill("license_plate","UT"+tag+"E"); click("Lưu thay đổi")
                require("vehicle edit closes editor","!document.querySelector('.core-editor')")
                state["vehicle"]["license_plate"]="UT"+tag+"E"
                navigate("/monthly-passes"); click("Thêm vé tháng")
                require("monthly editor open","!!document.querySelector('[name=pass_code]')")
                fill("pass_code","UAT"+tag); fill("price",50000); choose("vehicle_id",state["vehicle"]["id"]); choose("customer_id",state["customer"]["id"])
                fill("start_date",date.today().isoformat()); fill("end_date",(date.today()+timedelta(days=29)).isoformat())
                click("Đăng ký và ghi nhận thu"); require("monthly register actual receipt","!document.querySelector('.core-editor')")
                state["monthly"]=next(r for r in rows("/api/v1/monthly-passes?limit=100") if (r.get("card_code") or r["pass_code"])=="UAT"+tag)
                # Pagination is driven exactly as the user can drive it.
                wait("document.querySelectorAll('main tbody tr').length>0")
                for _ in range(40):
                    if js("[...document.querySelectorAll('main tbody tr')].some(e=>e.innerText.includes('UAT"+tag+"'))"): break
                    click("Trang sau")
                row_action("UAT"+tag,"Gia hạn")
                require("renewal preserves card identity","document.querySelector('[name=pass_code]')?.disabled===true")
                click("Gia hạn và ghi nhận thu"); require("monthly renewal completed","!document.querySelector('.core-editor')")
                periods=[r for r in rows("/api/v1/monthly-passes?limit=100") if (r.get("card_code") or r["pass_code"])=="UAT"+tag]
                record("renewal creates separate period retaining first",len(periods)==2 and state["monthly"]["id"] in {r["id"] for r in periods},period_ids=[r["id"] for r in periods])
                state["monthly_periods"]=[r["id"] for r in periods]
                row_action("UAT"+tag,"Ngừng vé"); click("Xác nhận Hủy","document.querySelector('[role=dialog]')")
                require("deactivate monthly confirmation completed","!document.querySelector('[role=dialog]')")
                record("monthly periods persist after deactivate",len([r for r in rows("/api/v1/monthly-passes?limit=100") if r["id"] in state["monthly_periods"]])==2)
                screenshot("functional-monthly")
            run_case("CUSTOMERS vehicle and monthly register renew deactivate",customers_monthly)
            def staff_account():
                navigate("/users"); click("Thêm tài khoản")
                require("manager account editor","!!document.querySelector('[name=username]')")
                record("manager can assign staff only",js("[...document.querySelector('[name=role_id]').options].filter(o=>o.value).every(o=>o.textContent==='staff')"))
                username="uat_staff_"+tag.lower(); password="Uat!"+uuid4().hex
                for n,v in {"full_name":"SYNTHETIC STAFF "+tag,"username":username,"password":password}.items():fill(n,v)
                click("Tạo tài khoản"); require("staff created through manager UI","!document.querySelector('.core-editor')")
                wait("document.querySelectorAll('main tbody tr').length>0")
                for _ in range(40):
                    if js("!!document.querySelector('[aria-label=\"Sửa tài khoản "+username+"\"]')"):break
                    click("Trang sau")
                js("document.querySelector('[aria-label=\"Sửa tài khoản "+username+"\"]').click()")
                fill("full_name","SYNTHETIC STAFF Edited "+tag)
                js("document.querySelector('[name=is_active]').click()")
                click("Lưu thay đổi"); require("manager locks synthetic staff","!document.querySelector('.core-editor')&&document.querySelector('main').innerText.includes('Đã khóa')")
                call("Storage.clearDataForOrigin", {"origin": ORIGIN,"storageTypes":"all"})
                call("Page.navigate", {"url":ORIGIN+"/login"}); wait("!!document.querySelector('#username')")
                set_value("#username",username);set_value("#password",password);js("document.querySelector('button[type=submit]').click()")
                require("locked account cannot authenticate","location.pathname==='/login'&&!!document.querySelector('[role=alert]')")
                expected_http("/api/auth/login",400,"Deliberate login with the newly locked synthetic staff account")
                login("manager");navigate("/users")
                for _ in range(40):
                    if js("!!document.querySelector('[aria-label=\"Sửa tài khoản "+username+"\"]')"):break
                    click("Trang sau")
                js("document.querySelector('[aria-label=\"Sửa tài khoản "+username+"\"]').click()")
                js("document.querySelector('[name=is_active]').click()")
                click("Lưu thay đổi");require("manager unlock completes","!document.querySelector('.core-editor')")
                login_person(username,password);navigate("/users")
                require("staff cannot open account manager","document.querySelector('main').innerText.includes('Bạn không có quyền')")
                login("manager")
                state["staff_user"]=username
            run_case("ACCOUNTS manager create edit lock unlock staff",staff_account)
            def reports_config():
                login("manager");navigate("/reports")
                require("day report real UI loaded","!!document.querySelector('.chart')||document.querySelector('main').innerText.includes('Chỗ trống hiện tại')")
                today=date.today().isoformat()
                day=api("/api/v2/sites/1/reports/summary?period=day&anchor_date="+today)
                record("daily aggregation one business day",day["status"]==200 and day["data"]["period"]=="day" and day["data"]["start_date"]==day["data"]["end_date"])
                js("(()=>{const e=[...document.querySelectorAll('main select')].find(e=>[...e.options].some(o=>o.value==='week'));Object.getOwnPropertyDescriptor(HTMLSelectElement.prototype,'value').set.call(e,'week');e.dispatchEvent(new Event('change',{bubbles:true}))})()")
                require("week UI selected","document.querySelector('main').innerText.includes('Ngày kết thúc')")
                week=api("/api/v2/sites/1/reports/summary?period=week&anchor_date="+today)
                record("week has seven daily buckets",week["status"]==200 and len(week["data"]["daily_traffic"])==7)
                record("week aggregate reconciles daily arrivals",sum(r["arrivals"] for r in week["data"]["daily_traffic"])==week["data"]["total_arrivals"],summary_keys=list(week["data"]))
                export_dir=OUT/"downloads";export_dir.mkdir(exist_ok=True)
                call("Browser.setDownloadBehavior",{"behavior":"allow","downloadPath":str(export_dir)})
                click("Xuất CSV")
                for _ in range(80):
                    js("new Promise(r=>setTimeout(r,100))")
                    if list(export_dir.glob("*.csv")):break
                files=list(export_dir.glob("*.csv"))
                record("CSV downloaded through UI",len(files)==1,files=[p.name for p in files])
                if files:record("CSV contains report data",len(files[0].read_text(encoding="utf-8-sig"))>100)
                screenshot("functional-week-report")
                navigate("/ai")
                status=api("/api/v2/sites/1/ai/status")
                record("AI status actual API readable",status["status"]==200,evidence={k:v for k,v in status["data"].items() if k in {"enabled","provider","model","configured"}})
                checks.append({"case":current,"check":"live AI day week question staffing empty-period generation","status":"NOT_RUN","reason":"Root agent runs provider cases separately; browser never mocks success or calls provider."})
                navigate("/site-settings")
                require("public profile real editor","document.querySelector('main').innerText.includes('Lưu thông tin công khai')")
                click("Lưu thông tin công khai")
                require("public profile unchanged-value roundtrip save","document.querySelector('main').innerText.includes('Đã cập nhật trang giới thiệu')")
                navigate("/audit-logs")
                record("audit records visible",js("document.querySelectorAll('main tbody tr').length>0"))
                screenshot("functional-audit")
            run_case("REPORTS daily weekly CSV public configuration audit AI status",reports_config)
            def customer_privacy():
                login("customer")
                own_before=rows("/api/v2/me/vehicles")
                login("manager")
                available=api("/api/v2/sites/1/availability")["data"]
                available_types={r["vehicle_type_id"] for r in available["slots"] if r.get("available_now")}
                vehicle_type=next(r for r in rows("/api/v2/catalog/vehicle-types") if r.get("requires_plate",True) and r["id"] in available_types and not r["name"].startswith("UAT"))
                navigate("/sites")
                set_value("#operation-plate","PR"+tag);set_value("#operation-type",vehicle_type["id"]);click("Ghi nhận xe vào")
                require("fresh private walk-in admitted through UI","document.querySelector('main').innerText.includes('Đã ghi nhận xe vào')")
                foreign=next(r for r in rows("/api/v2/sites/1/sessions?status=active&license_plate=PR"+tag) if r["license_plate"]=="PR"+tag)
                state["privacy_session_id"]=foreign["id"]
                ticket=api("/api/v2/sites/1/sessions/"+foreign["id"]+"/ticket")["data"]
                private_proof=ticket["payment_access_code"]
                del ticket
                login("customer");navigate("/portal?tab=fees")
                require("customer lookup ready","!!document.querySelector('#customer-type')&&document.querySelector('#customer-type').options.length>0")
                set_value("#customer-plate",foreign["license_plate"]);set_value("#customer-type",vehicle_type["id"])
                click("Tra phí gửi xe")
                require("unowned plate alone reveals no fee","!!document.querySelector('#ticket')&&!document.querySelector('.fee-total')&&!!document.querySelector('main [role=alert]')")
                expected_http("/api/v2/me/fee-lookup",404,"Known foreign synthetic plate must remain private without ticket proof")
                set_value("#ticket",private_proof);click("Xác nhận vé")
                require("private payment proof permits fee lookup","!!document.querySelector('.fee-total')")
                require("proof input removed and URL excludes secret","!document.querySelector('#ticket')&&!location.href.includes('PAP1')")
                private_proof=None
                own_after=rows("/api/v2/me/vehicles")
                record("ticket proof grants no vehicle ownership",{r["id"] for r in own_before}=={r["id"] for r in own_after})
                history=rows("/api/v2/me/sessions?limit=100")
                record("foreign stay not added to owner history",foreign["id"] not in {r["id"] for r in history})
                screenshot("functional-private-fee")
                login("manager");navigate("/sites");click("Xe ra")
                set_value("#operation-query",foreign["license_plate"])
                js("document.querySelector('main form button[type=submit]').click()")
                require("fresh walk-in exit quote","[...document.querySelectorAll('main button')].some(e=>['Thu tiền mặt','Ghi nhận xe ra'].includes(e.textContent.trim()))")
                js("[...document.querySelectorAll('main button')].find(e=>['Thu tiền mặt','Ghi nhận xe ra'].includes(e.textContent.trim())).click()")
                require("exit confirmation visible","!!document.querySelector('[role=dialog] dl')")
                if js("!![...document.querySelectorAll('[role=dialog] button')].find(e=>e.textContent.trim()==='Đã thu tiền — cho xe ra')"):
                    js("document.querySelector('[role=dialog] input[type=checkbox]').click()")
                    click("Đã thu tiền — cho xe ra","document.querySelector('[role=dialog]')")
                else:
                    js("[...document.querySelectorAll('[role=dialog] button')].find(e=>e.textContent.trim().startsWith('Xác nhận xe ra')).click()")
                require("fresh walk-in checkout completes","!document.querySelector('[role=dialog]')")
                record("fresh walk-in completed server state",any(r["id"]==foreign["id"] for r in rows("/api/v2/sites/1/sessions?status=completed&license_plate="+foreign["license_plate"])))
            run_case("CUSTOMER PRIVACY foreign plate requires private proof and never grants ownership",customer_privacy)
            def delete_synthetic_catalog():
                login("manager")
                # Linked monthly vehicle/type are retained to preserve financial history.
                # Use separate unreferenced records to prove each normal delete action.
                for route,button,body,label in [
                    ("/zones","Thêm khu vực",{"name":"UAT DELETE Z "+tag,"capacity":1},"UAT DELETE Z "+tag),
                    ("/vehicle-types","Thêm loại xe",{"name":"UAT DELETE T "+tag,"description":"Synthetic deletion test","code_prefix":"V"+tag},"UAT DELETE T "+tag),
                    ("/customers","Thêm khách hàng",{"full_name":"UAT DELETE C "+tag,"phone_number":"0900000000"},"UAT DELETE C "+tag)]:
                    navigate(route);click(button)
                    for n,v in body.items():fill(n,v)
                    click("Lưu thay đổi");require(route+" scratch create","!document.querySelector('.core-editor')")
                    search_table(label);row_action(label,"Xóa")
                    require(route+" scratch delete","![...document.querySelectorAll('main tbody tr')].some(e=>e.innerText.includes("+json.dumps(label)+"))")
                navigate("/parking-slots"); row_action(state["slot"]["slot_name"],"Xóa")
                require("unused named slot delete","![...document.querySelectorAll('main tbody tr')].some(e=>e.innerText.includes("+json.dumps(state["slot"]["slot_name"])+"))")
                navigate("/price-configs");row_action(state["type"]["name"],"Xóa")
                require("unused price config delete","![...document.querySelectorAll('main tbody tr')].some(e=>e.innerText.includes("+json.dumps(state["type"]["name"])+"))")
                navigate("/zones");row_action(state["zone"]["name"],"Xóa")
                require("zone delete once slot removed","![...document.querySelectorAll('main tbody tr')].some(e=>e.innerText.includes("+json.dumps(state["zone"]["name"])+"))")
                navigate("/vehicles");click("Thêm phương tiện")
                fill("license_plate","DEL"+tag);choose("vehicle_type_id",state["type"]["id"]);click("Thêm mới")
                require("unreferenced vehicle create","!document.querySelector('.core-editor')")
                search_table("DEL"+tag);row_action("DEL"+tag,"Xóa")
                click("Xác nhận Xóa","document.querySelector('[role=dialog]')")
                require("unreferenced vehicle delete","!document.querySelector('[role=dialog]')&&![...document.querySelectorAll('main tbody tr')].some(e=>e.innerText.includes('DEL"+tag+"'))")
            run_case("DELETE synthetic unreferenced catalog records",delete_synthetic_catalog)
            (OUT/"synthetic-records.json").write_text(json.dumps(state,ensure_ascii=False,indent=2),encoding="utf-8")
            for item,reason in [("Actual bank payment", "No payOS account; real money integration disabled"),("Physical camera and actual OCR", "Separate camera agent owns this acceptance"),("Advanced occupancy calibration forecast refunds waitlist fleet and portal products", "Routes inspected; transactional browser cases not run in this harness")]:
                checks.append({"case":"scope limits","check":item,"status":"BLOCKED" if item=="Actual bank payment" else "NOT_RUN","reason":reason})
        if args.mode == "followup":
            if not args.records:raise ValueError("Follow-up requires prior non-secret synthetic-records.json")
            state=json.loads(args.records.read_text(encoding="utf-8"));tag=state["tag"]
            login("manager")
            def monthly_followup():
                card="UAT"+tag
                before=[r for r in rows("/api/v1/monthly-passes?limit=100") if (r.get("card_code") or r["pass_code"])==card]
                record("registered monthly card persisted",len(before)==1 and before[0]["price"]==50000)
                navigate("/monthly-passes");row_action(card,"Gia hạn")
                require("renewal preserves card identity","document.querySelector('[name=pass_code]')?.disabled===true")
                click("Gia hạn và ghi nhận thu");require("monthly renewal completed","!document.querySelector('.core-editor')")
                after=[r for r in rows("/api/v1/monthly-passes?limit=100") if (r.get("card_code") or r["pass_code"])==card]
                record("renewal creates separate period and keeps old period",len(after)==len(before)+1 and {r["id"] for r in before}.issubset({r["id"] for r in after}),period_ids=[r["id"] for r in after])
                row_action(card,"Ngừng vé");click("Xác nhận Hủy","document.querySelector('[role=dialog]')")
                require("monthly deactivation confirmation completed","!document.querySelector('[role=dialog]')")
                final=[r for r in rows("/api/v1/monthly-passes?limit=100") if (r.get("card_code") or r["pass_code"])==card]
                record("deactivation retains periods and disables one",len(final)==len(after) and sum(not r["is_active"] for r in final)==1)
                screenshot("monthly-lifecycle-complete")
            run_case("MONTHLY bounded renewal and deactivation after prior registration",monthly_followup)
            def history_followup():
                stay=next(r for r in rows("/api/v2/sites/1/sessions?session_id="+state["privacy_session_id"]) if r["id"]==state["privacy_session_id"])
                navigate("/history")
                require("history date filters render","document.querySelector('main').innerText.includes('Ngày vào từ')")
                fill_label("Tìm đúng biển số",stay["license_plate"])
                fill_label("Ngày vào từ",stay["check_in_time"][:10]);fill_label("Ngày vào đến",stay["check_in_time"][:10])
                click("Tìm lượt gửi")
                require("history exact plate date result","document.querySelectorAll('main tbody tr').length===1&&document.querySelector('main tbody')?.textContent.includes("+json.dumps(stay["license_plate"])+")")
                record("history matching server completed record",stay["status"]=="completed" and stay["check_out_time"] is not None)
                click("Chi tiết","document.querySelector('main tbody')")
                require("history detail opens","!!document.querySelector('[role=dialog]')")
                screenshot("history-completed-detail")
                click("Đóng","document.querySelector('[role=dialog]')")
                fill_label("Ngày vào từ",(date.fromisoformat(stay["check_in_time"][:10])+timedelta(days=1)).isoformat())
                record("reversed history date range blocks submit",js("[...document.querySelectorAll('main button')].find(e=>e.textContent.trim()==='Tìm lượt gửi').disabled"))
            run_case("HISTORY completed stay plate date filter detail validation",history_followup)
            def prefix_followup():
                existing=next(r for r in rows("/api/v1/vehicle-types?limit=100") if r.get("code_prefix"))
                unique=uuid4().hex[:6].upper();name="UAT PREFIX "+unique
                navigate("/vehicle-types");click("Thêm loại xe")
                fill("name",name);fill("code_prefix",existing["code_prefix"]);click("Lưu thay đổi")
                require("create duplicate prefix specific validation","[...document.querySelectorAll('main [role=alert]')].some(e=>e.textContent.toLowerCase().includes('tiền tố'))")
                expected_http("/api/v1/vehicle-types",409,"Deliberate duplicate prefix; message must identify the prefix rather than an unrelated type name")
                fill("code_prefix","W"+unique);click("Lưu thay đổi")
                require("corrected unique prefix creates type","!document.querySelector('.core-editor')")
                created=next(r for r in rows("/api/v1/vehicle-types?limit=100") if r["name"]==name)
                search_table(name);row_action(name,"Sửa");fill("code_prefix",existing["code_prefix"]);click("Lưu thay đổi")
                require("edit duplicate prefix specific validation","[...document.querySelectorAll('main [role=alert]')].some(e=>e.textContent.toLowerCase().includes('tiền tố'))")
                expected_http("/api/v1/vehicle-types/"+str(created["id"]),409,"Deliberate duplicate prefix during update; original record must remain intact")
                screenshot("prefix-validation-specific")
                click("Hủy","document.querySelector('.core-editor')");row_action(name,"Xóa")
                require("scratch prefix test record removed","![...document.querySelectorAll('main tbody tr')].some(e=>e.textContent.includes("+json.dumps(name)+"))")
            run_case("PREFIX real duplicate identifier validation regression",prefix_followup)
            def account_delete_followup():
                login("admin");navigate("/users")
                target=next(r for r in rows("/api/v1/users?limit=100") if r["username"]==state["staff_user"])
                require("bound staff row available","!!document.querySelector('[aria-label=\"Xóa tài khoản "+state["staff_user"]+"\"]')")
                js("document.querySelector('[aria-label=\"Xóa tài khoản "+state["staff_user"]+"\"]').click()")
                click("Xác nhận Xóa","document.querySelector('[role=dialog]')")
                require("bound account delete is refused explicitly","document.body.innerText.includes('Tài khoản đang được sử dụng và không thể xóa')")
                expected_http("/api/v1/users/"+str(target["id"]),409,"Synthetic staff is linked to a site membership; relational guard must retain the account")
                click("Quay lại","document.querySelector('[role=dialog]')")
                unique=uuid4().hex[:6];username="uat_delete_"+unique
                click("Thêm tài khoản");fill("username",username);fill("full_name","SYNTHETIC DELETE "+unique);fill("password","Uat!"+uuid4().hex)
                role_value=js("[...document.querySelector('[name=role_id]').options].find(e=>e.textContent==='customer').value")
                fill("role_id",role_value);click("Tạo tài khoản")
                require("unassigned customer created by admin","!document.querySelector('.core-editor')")
                require("unassigned customer row available","!!document.querySelector('[aria-label=\"Xóa tài khoản "+username+"\"]')")
                js("document.querySelector('[aria-label=\"Xóa tài khoản "+username+"\"]').click()")
                click("Xác nhận Xóa","document.querySelector('[role=dialog]')")
                require("admin deletes unassigned unused account","!document.querySelector('[role=dialog]')&&!document.querySelector('[aria-label=\"Xóa tài khoản "+username+"\"]')")
                record("deleted account absent in actual API",all(r["username"]!=username for r in rows("/api/v1/users?limit=100")))
            run_case("ACCOUNT DELETE referenced refusal and unused account deletion",account_delete_followup)
        completed = True
finally:
    process.terminate()
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        process.kill(); process.wait(timeout=5)
    log.close()
    if PROFILE.resolve().parent == OUT.resolve() and OUT.resolve().is_relative_to((ROOT / "backend/artifacts/comprehensive-uat").resolve()):
        for _ in range(30):
            try:
                shutil.rmtree(PROFILE)
                break
            except FileNotFoundError:
                break
            except PermissionError:
                time.sleep(.1)
    report = {"completed": completed, "mode": args.mode, "status_counts":{status:sum(row["status"]==status for row in checks) for status in ("PASS","FAIL","BLOCKED","NOT_RUN")}, "checks": checks, "requests": requests, "errors": errors, "unexpected_errors":[row for row in errors if not row.get("expected")], "console_errors": console_errors, "unexpected_console_errors":[row for row in console_errors if not row.get("expected")], "blocked": blocked, "screenshots": screenshots, "private_browser_profile_removed": not PROFILE.exists()}
    (OUT / "result.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"completed": completed, "pass": sum(r["status"]=="PASS" for r in checks), "fail": sum(r["status"]=="FAIL" for r in checks), "artifacts": str(OUT)}, ensure_ascii=True), flush=True)
