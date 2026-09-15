"""Real UI acceptance on an explicitly marked isolated demo; no API fixtures.

Creates synthetic camera/calibration observations and one demo prepaid order.
Never uses real money, AI providers, external URLs, physical cameras or live DB.
Credentials stay in process; artifacts contain only sanitized checks and images.
"""
import argparse
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
parser.add_argument("--origin", default="http://127.0.0.1:8768")
parser.add_argument("--credentials", type=Path, required=True)
parser.add_argument("--preflight", type=Path)
parser.add_argument("--resume-customer", type=Path)
args = parser.parse_args()
if args.origin != "http://127.0.0.1:8768":
    raise ValueError("This mutation harness only targets the dedicated 8768 UAT origin")
credentials = json.loads(args.credentials.read_text(encoding="utf-8"))
marker = json.loads((args.preflight or Path(credentials["database"] + ".demo.json")).resolve().read_text(encoding="utf-8"))
if args.preflight and Path(marker["database"]).resolve() != Path(credentials["database"]).resolve():
    raise ValueError("Preflight and credentials identify different synthetic databases")
if credentials.get("profile") != "single-lot-academic-v1" or not marker.get("synthetic_history"):
    raise ValueError("Requires explicitly marked single-lot synthetic demo credentials")
SITE = marker["single_site_id"]
RUN = ROOT / "backend/artifacts/extensions-browser" / uuid4().hex[:10]
RUN.mkdir(parents=True)
PROFILE = RUN / "chrome-profile"
NAME = "UI CV " + uuid4().hex[:8]
checks, requests, http_errors, runtime_errors, blocked_external, ids = [], [], [], [], [], {}
completed = False
if args.resume_customer:
    previous_path = args.resume_customer.resolve()
    if previous_path.parent.parent != (ROOT / "backend/artifacts/extensions-browser").resolve() or previous_path.name != "result.json":
        raise ValueError("Resume requires this harness's sanitized result")
    previous = json.loads(previous_path.read_text(encoding="utf-8"))
    if previous.get("http_errors") or previous.get("runtime_errors") or "order" in previous.get("synthetic_ids", {}):
        raise ValueError("Resume only before any customer order was created and after clean camera checks")
    checks = [row for row in previous["checks"] if not row["name"].startswith("customer ")]
    if not all(row["passed"] for row in checks):
        raise ValueError("Camera/staff checks must all have passed")
    requests = previous["writes"]
    ids = previous["synthetic_ids"]


def picture(vehicle=False):
    yy, xx = np.indices((160, 160))
    pixels = np.where((xx // 4 + yy // 4) % 2, 100, 125).astype(np.uint8)
    if vehicle:
        pixels[30:115, 22:64] = 190
    output = io.BytesIO()
    Image.fromarray(pixels).save(output, "PNG")
    return base64.b64encode(output.getvalue()).decode("ascii")


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
                    allowed = parsed.netloc == "127.0.0.1:8768" or parsed.scheme in {"data", "blob", "about"}
                    if not allowed:
                        blocked_external.append({"host": parsed.hostname, "scheme": parsed.scheme})
                    sequence += 1
                    ws.send(json.dumps({"id": sequence, "method": "Fetch.continueRequest" if allowed else "Fetch.failRequest",
                        "params": {"requestId": paused["requestId"], **({} if allowed else {"errorReason": "BlockedByClient"})}}))
                if event == "Network.requestWillBeSent":
                    request = response["params"]["request"]
                    parsed = urllib.parse.urlsplit(request["url"])
                    if parsed.netloc == "127.0.0.1:8768":
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
            for selector, value in (("#username", role + "_demo"), ("#password", credentials["accounts"][role + "_demo"])):
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
        if not args.resume_customer:
            login("manager")
            check("server advertises isolated single-lot demo", "(async()=>{const text=await(await fetch('/config.js')).text();return text.includes('DEMO: true')&&text.includes('SINGLE_SITE_ID: " + str(SITE) + "');})()")
            ids["camera"] = evaluate("(async()=>{window.camera=await api('/cameras',{site_id:" + str(SITE) + ",name:" + json.dumps(NAME) + ",retention_hours:1});return camera.id;})()")
            evaluate("go('/vision')")
            check("manager camera administration loads", "!!field('Tên camera')&&main().innerText.includes(" + json.dumps(NAME) + ")")
            evaluate("(()=>{const row=[...main().querySelectorAll('tr')].find(r=>r.innerText.includes(" + json.dumps(NAME) + "));button('Sửa',row).click();})()")
            evaluate("input('Tên camera'," + json.dumps(NAME + " fixed") + ");input('Thời gian lưu ảnh (giờ)',2)")
            evaluate("button('Lưu camera').click()")
            check("manager updates camera name and retention", "main().innerText.includes('Đã cập nhật camera.')&&(()=>{const row=[...main().querySelectorAll('tr')].find(r=>r.innerText.includes(" + json.dumps(NAME + " fixed") + "));return row&&button('Cấp khóa gửi ảnh',row)?.disabled===false;})()")
            evaluate("(()=>{const row=[...main().querySelectorAll('tr')].find(r=>r.innerText.includes(" + json.dumps(NAME + " fixed") + "));button('Cấp khóa gửi ảnh',row).click();})()")
            check("token rotation requires explicit dialog action", "dialog()?.innerText.includes('Khóa mới chỉ được trả về lần này')")
            evaluate("button('Cấp khóa mới',dialog()).click()")
            check("one-time key remains masked", "field('Khóa camera mới')?.type==='password'&&field('Khóa camera mới')?.value.length>=32")
            evaluate("button('Đóng và xóa khóa khỏi màn hình',dialog()).click()")
            check("token disappears after closing", "!field('Khóa camera mới')&&!dialog()")
            evaluate("scrollTitle('Camera tại bãi')")
            screenshot("manager-camera-desktop")
            ids["reference"] = evaluate("(async()=>{window.reference=await uploadPattern(" + str(ids["camera"]) + "," + json.dumps(picture()) + ");return reference.id;})()")
            evaluate("go('/occupancy')")
            check("occupancy camera picker ready", "!!field('Camera quan sát')")
            evaluate("pickValue('Camera quan sát'," + str(ids["camera"]) + ")")
            check("manager can configure normalized regions", "!!field('Ảnh nền trống')&&!!field('Chỗ cần khoanh')")
            evaluate("pickValue('Ảnh nền trống'," + json.dumps(ids["reference"]) + ")")
            check("private reference image is visible", "!!main().querySelector('img[src^=\"blob:\"]')")
            ids["slot"] = evaluate("(async()=>{const a=await api('/sites/" + str(SITE) + "/availability');return a.slots.find(s=>!s.is_occupied).id;})()")
            evaluate("pickValue('Chỗ cần khoanh'," + str(ids["slot"]) + ")")
            for x, y in ((.1, .1), (.45, .1), (.45, .8), (.1, .8)):
                evaluate(f"input('Tọa độ X (0–1)',{x});input('Tọa độ Y (0–1)',{y})")
                evaluate("button('Thêm đỉnh').click()")
            evaluate("button('Thêm vùng (4 đỉnh)').click()")
            evaluate("input('Tuổi ảnh tối đa (giây)',300);input('Số ảnh cần thống nhất',1)")
            evaluate("[...document.querySelectorAll('label')].find(el=>el.textContent.includes('Tôi đã kiểm tra ảnh nền')).querySelector('input').click()")
            evaluate("button('Lưu phiên bản mới').click()")
            check("manager calibration saves version one", "main().innerText.includes('Đã lưu phiên bản cấu hình mới')&&main().innerText.includes('Phiên bản hiện tại 1')")
            ids["calibration"] = evaluate("(async()=>{const v=await api('/sites/" + str(SITE) + "/occupancy?camera_id=" + str(ids["camera"]) + "');return v.calibration.id;})()")
            ids["source"] = evaluate("(async()=>{const v=await uploadPattern(" + str(ids["camera"]) + "," + json.dumps(picture(True)) + ");return v.id;})()")
            evaluate("button('Làm mới',[...document.querySelectorAll('main button')].find(b=>b.textContent==='Phân tích ảnh')?.closest('main')||document)?.click()")
            # Full route re-entry reloads camera data while retaining only persisted calibration.
            evaluate("go('/vision')")
            evaluate("go('/occupancy')")
            check("saved calibration survives route change", "!!field('Camera quan sát')")
            evaluate("pickValue('Camera quan sát'," + str(ids["camera"]) + ")")
            check("source options loaded", "!!field('Ảnh cần phân tích')&&main().innerText.includes('Phiên bản hiện tại 1')")
            evaluate("pickValue('Ảnh cần phân tích'," + json.dumps(ids["source"]) + ")")
            evaluate("button('Phân tích ảnh').click()")
            check("synthetic changed region produces a discrepancy without changing inventory", "main().innerText.includes('Cần kiểm tra chênh lệch')&&main().innerText.includes('Có xe theo ảnh')")
            check("business slot remains empty", "(async()=>{const a=await api('/sites/" + str(SITE) + "/availability');return a.slots.find(s=>s.id===" + str(ids["slot"]) + ").is_occupied===false;})()")
            evaluate("scrollTitle('Quan sát mới nhất')")
            screenshot("manager-occupancy-desktop")
            metrics(True)
            check("occupancy mobile does not overflow document", "document.documentElement.scrollWidth<=innerWidth+1")
            screenshot("manager-occupancy-mobile")
            metrics(False)
            login("staff")
            evaluate("go('/vision')")
            check("staff camera page hides configuration and credential controls", "main().innerText.includes('Camera tại bãi')&&!field('Tên camera')&&!button('Cấp khóa gửi ảnh')&&!button('Ngừng camera và thu hồi khóa')")
            evaluate("go('/occupancy')")
            check("staff occupancy page ready", "!!field('Camera quan sát')")
            evaluate("pickValue('Camera quan sát'," + str(ids["camera"]) + ")")
            check("staff sees saved CV discrepancy but no calibration controls", "main().innerText.includes('Cần kiểm tra chênh lệch')&&!field('Ảnh nền trống')&&!button('Lưu phiên bản mới')")
            evaluate("scrollTitle('Quan sát mới nhất')")
            screenshot("staff-occupancy-desktop")
            metrics(True)
            screenshot("staff-occupancy-mobile")
            metrics(False)
        login("customer")
        check("customer has no operational camera menus", "!!document.querySelector('[role=tab]')&&main().textContent.includes('Xe của tôi')&&!document.querySelector('a[href=\"/occupancy\"]')")
        evaluate("go('/reservations')")
        check("customer enters hourly purchase through the paid-booking CTA", "!!document.querySelector('a[href=\"/portal?tab=purchase&kind=hourly\"]')")
        evaluate("document.querySelector('a[href=\"/portal?tab=purchase&kind=hourly\"]').click()")
        check("customer hourly purchase form loads", "!!field('Xe sử dụng')&&field('Loại vé')?.textContent==='Vé giờ'")
        check("customer has a compatible owned vehicle and hourly offer", "(async()=>{window.cars=rows(await api('/me/vehicles'));window.plans=rows(await api('/plans'));window.offer=plans.find(p=>p.product_kind==='hourly'&&p.is_active!==false&&p.eligible_zones.length&&cars.some(c=>c.vehicle_type_id===p.vehicle_type_id));window.car=cars.find(c=>c.vehicle_type_id===offer?.vehicle_type_id&&c.license_plate.startsWith('UAT'))||cars.find(c=>c.vehicle_type_id===offer?.vehicle_type_id);return !!offer&&!!car;})()")
        evaluate("pickValue('Xe sử dụng',car.id)")
        evaluate("pickValue('Gói vé',offer.id)")
        check("hourly purchase exposes fixed start and eligible zone", "!!field('Bắt đầu (giờ Việt Nam)')&&!!field('Khu vực đỗ')&&main().innerText.includes('Đến muộn không kéo dài giờ kết thúc')")
        evaluate("field('Hình thức thanh toán').dispatchEvent(new MouseEvent('mousedown',{bubbles:true}));delay()")
        check("payOS disabled catalog offers no online payment option", "![...document.querySelectorAll('[role=option]')].some(el=>el.getAttribute('data-value')==='payos')")
        evaluate("[...document.querySelectorAll('[role=option]')].find(el=>el.getAttribute('data-value')==='demo').click()")
        evaluate("(()=>{const t=new Date(Date.now()+2*3600000+7*3600000);input('Bắt đầu (giờ Việt Nam)',t.toISOString().slice(0,16));})()")
        screenshot("customer-hourly-purchase-desktop")
        evaluate("button('Tạo đơn giữ chỗ').click()")
        check("server-created order shows held slot and deadline", "main().innerText.includes('Đã tạo đơn.')&&main().innerText.includes('Hạn thanh toán giữ chỗ')&&main().innerText.includes('Chỗ được xếp')&&!!button('Giả lập thanh toán thành công')")
        ids["order"] = evaluate("(async()=>{const orders=rows(await api('/me/orders'));return orders.find(o=>o.status==='pending'&&o.plan_id===offer.id&&o.vehicle_id===car.id).id;})()")
        evaluate("scrollTitle('Chi tiết đơn vé')")
        screenshot("customer-held-order-desktop")
        evaluate("button('Giả lập thanh toán thành công').click()")
        check("demo payment grants ready timed entitlement without bank claim", "main().innerText.includes('Sẵn sàng trong khung giờ')&&!button('Giả lập thanh toán thành công')&&main().innerText.includes('DEMO — không chuyển tiền')")
        metrics(True)
        evaluate("scrollTitle('Chi tiết đơn vé')")
        check("paid order mobile does not overflow document", "document.documentElement.scrollWidth<=innerWidth+1")
        screenshot("customer-paid-hourly-mobile")
        metrics(False)
        evaluate("[...document.querySelectorAll('[role=tab]')].find(t=>t.textContent==='Vé của tôi').click()")
        check("owned timed ticket appears separately from monthly passes", "main().innerText.includes('Vé giờ / ngày')&&main().innerText.includes('Vé tháng')&&main().innerText.includes('Sẵn sàng trong khung giờ')")
        screenshot("customer-owned-passes-desktop")
        evaluate("go('/reservations')")
        check("paid booking mode points to package purchase instead of a free form", "!!document.querySelector('a[href=\"/portal?tab=purchase&kind=hourly\"]')&&!field('Bắt đầu (giờ Việt Nam)')")
        screenshot("customer-reservation-purchase-desktop")
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
    report = {"passed": completed and not http_errors and not runtime_errors and not blocked_external,
        "scope": "Dedicated8768 synthetic UAT; one demo prepaid order and camera/calibration/images; no bank, AI, real device or presentation writes",
        "checks": checks, "synthetic_ids": ids, "writes": writes, "http_errors": http_errors,
        "runtime_errors": runtime_errors, "blocked_external": blocked_external,
        "private_browser_profile_removed": not PROFILE.exists()}
    if args.resume_customer:
        report["resumed_from"] = str(args.resume_customer)
    (RUN / "result.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"passed": report["passed"], "checks": len(checks), "artifact_directory": str(RUN)}, ensure_ascii=True))
    if completed and not report["passed"]:
        raise AssertionError("Acceptance captured errors; inspect sanitized result")
