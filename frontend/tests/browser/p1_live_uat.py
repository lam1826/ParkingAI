"""P1 browser acceptance against an explicitly isolated synthetic UAT database.

Requires root's running P1 server on 8767. No API fixtures or external provider.
Creates one labelled walk-in, corrects it, confirms loss, then cancels replacement.
Credentials are read in-process only; reports contain neither passwords nor tokens.
"""
import base64
import argparse
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
RUN = ROOT / "backend/artifacts/p1-browser" / uuid4().hex[:10]
RUN.mkdir(parents=True)
ORIGIN = "http://127.0.0.1:8767"
DATABASE = "upgraded-bc1d74add65e4fb2a829410e1cfa4ecf.db"
credentials = json.loads((ROOT / "backend/artifacts/demo" / (DATABASE + ".demo-credentials.json")).read_text(encoding="utf-8"))["accounts"]
PLATE = "P1UI" + uuid4().hex[:7].upper()
NEW_PLATE = PLATE + "R"
checks, requests, http_errors, runtime_errors = [], [], [], []
completed = False
business = {}
parser = argparse.ArgumentParser()
parser.add_argument("--resume-staff", type=Path)
parser.add_argument("--capture-existing", type=Path)
args = parser.parse_args()
if args.resume_staff or args.capture_existing:
    source = (args.resume_staff or args.capture_existing).resolve()
    if source.parent.parent != (ROOT / "backend/artifacts/p1-browser").resolve() or source.name != "result.json":
        raise RuntimeError("Resume must use a sanitized P1 browser result")
    previous = json.loads(source.read_text(encoding="utf-8"))
    business = previous["business"]
    PLATE, NEW_PLATE = previous["synthetic_plate"], previous["replacement_plate"]
    checks = [] if args.capture_existing else [row for row in previous["checks"] if not row["name"].startswith("staff ")]
    if not all(row["passed"] for row in checks) or "replacement_id" not in business:
        raise RuntimeError("Resume requires a completed manager workflow")
    requests = [] if args.capture_existing else previous["writes"]
profile = RUN / "chrome-profile"
log = (RUN / "process.log").open("w", encoding="utf-8")
chrome = subprocess.Popen([r"C:\Program Files\Google\Chrome\Application\chrome.exe", "--headless=new", "--disable-gpu", "--no-first-run", "--no-default-browser-check", "--disable-background-networking", "--disable-component-update", "--disable-sync", "--remote-debugging-port=18988", "--remote-debugging-address=127.0.0.1", "--window-size=1440,1050", "--user-data-dir=" + str(profile), "about:blank"], stdout=log, stderr=log, creationflags=subprocess.CREATE_NO_WINDOW)
try:
    for _ in range(50):
        try:
            targets = json.load(urllib.request.urlopen("http://127.0.0.1:18988/json", timeout=1))
            target = next(row for row in targets if row["type"] == "page")
            break
        except (OSError, StopIteration):
            if chrome.poll() is not None:
                raise RuntimeError("Private Chrome exited")
            time.sleep(.2)
    else:
        raise RuntimeError("Private Chrome did not start")
    with connect(target["webSocketDebuggerUrl"], max_size=20_000_000) as ws:
        sequence = 0

        def call(method, params):
            global sequence
            sequence += 1
            wanted = sequence
            ws.send(json.dumps({"id": wanted, "method": method, "params": params}))
            while True:
                response = json.loads(ws.recv(timeout=30))
                if response.get("method") == "Network.requestWillBeSent":
                    request = response["params"]["request"]
                    parsed = urllib.parse.urlsplit(request["url"])
                    if parsed.netloc == "127.0.0.1:8767":
                        requests.append({"method": request["method"], "path": parsed.path, "query": parsed.query})
                if response.get("method") == "Network.responseReceived":
                    item = response["params"]["response"]
                    if item["status"] >= 400:
                        http_errors.append({"status": item["status"], "path": urllib.parse.urlsplit(item["url"]).path})
                if response.get("method") == "Runtime.exceptionThrown":
                    runtime_errors.append({"text": response["params"]["exceptionDetails"]["text"]})
                if response.get("id") == wanted:
                    if "error" in response:
                        raise RuntimeError("Browser command failed")
                    return response.get("result", {})

        def evaluate(expression):
            result = call("Runtime.evaluate", {"expression": expression, "awaitPromise": True, "returnByValue": True})
            if "exceptionDetails" in result:
                raise RuntimeError("Browser evaluation failed")
            return result.get("result", {}).get("value")

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
                (RUN / "failed-view.json").write_text(json.dumps(evaluate("({text:document.body.innerText,dialog:window.dialogText?.(),basis:window.historyStay?.billing_basis,checks:window.historyStay?{id:dialogText().includes(historyStay.id),source:dialogText().includes('Giá ghi nhận lúc xe vào'),price:dialogText().includes(historyStay.billing_basis.unit_price.toLocaleString('vi-VN')+' VND'),blocks:dialogText().includes(historyStay.billing_basis.billable_blocks+' ×')}:null})"), ensure_ascii=False, indent=2), encoding="utf-8")
                raise AssertionError(name)

        def screenshot(name):
            # Wait for MUI's entry/exit fade before judging the visual surface.
            evaluate("new Promise(resolve=>setTimeout(resolve,350))")
            image = call("Page.captureScreenshot", {"format": "png", "captureBeyondViewport": False})
            (RUN / (name + ".png")).write_bytes(base64.b64decode(image["data"]))

        def metrics(mobile):
            call("Emulation.setDeviceMetricsOverride", {"width": 390 if mobile else 1440, "height": 844 if mobile else 1050, "deviceScaleFactor": 1, "mobile": mobile})

        def fill(selector, value):
            evaluate("(()=>{const el=document.querySelector(" + json.dumps(selector) + ");Object.getOwnPropertyDescriptor(HTMLInputElement.prototype,'value').set.call(el," + json.dumps(value) + ");el.dispatchEvent(new Event('input',{bubbles:true}));})()")

        def setup_helpers():
            evaluate(r"""(()=>{
              window.delay=()=>new Promise(r=>setTimeout(r,90));
              window.main=()=>document.querySelector('main');
              window.dialog=()=>document.querySelector('.MuiDialog-root [role=dialog]');
              window.dialogText=()=>dialog()?.innerText||'';
              window.button=(text,scope=document)=>[...scope.querySelectorAll('button')].find(el=>el.textContent.trim()===text);
              window.field=(label,scope=document)=>{const el=[...scope.querySelectorAll('label,[id$="-label"]')].find(el=>el.textContent.replace('*','').trim()===label);return el&&(document.getElementById(el.htmlFor)||[...scope.querySelectorAll('[role=combobox]')].find(input=>input.getAttribute('aria-labelledby')?.split(' ').includes(el.id)));};
              window.input=(label,value,scope=document)=>{const el=field(label,scope);const proto=el.tagName==='TEXTAREA'?HTMLTextAreaElement.prototype:HTMLInputElement.prototype;Object.getOwnPropertyDescriptor(proto,'value').set.call(el,value);el.dispatchEvent(new Event('input',{bubbles:true}));};
              window.choose=async(label,text)=>{field(label).dispatchEvent(new MouseEvent('mousedown',{bubbles:true}));await delay();[...document.querySelectorAll('[role=option]')].find(el=>el.textContent===text||el.textContent.startsWith(text+' ·')).click();await delay();};
              window.apiRead=async path=>{const r=await fetch('/api/v2'+path,{headers:{Authorization:'Bearer '+localStorage.getItem('token')}});if(!r.ok)throw Error('Read failed');return r.json();};
              window.rows=data=>Array.isArray(data)?data:data.items;
              window.searchStay=async(id,status)=>{input('Tìm đúng biển số','');input('Mã vé (mã lượt)',id);await choose('Trạng thái lượt gửi',status);button('Tìm lượt gửi',main()).click();await delay();};
              window.closeDialog=async()=>{button('Đóng',dialog()).click();await delay();};
            })()""")

        call("Network.enable", {})
        call("Runtime.enable", {})
        metrics(False)
        for role in (("staff",) if args.resume_staff else ("manager", "staff")):
            call("Storage.clearDataForOrigin", {"origin": ORIGIN, "storageTypes": "all"})
            call("Page.navigate", {"url": ORIGIN + "/login"})
            check(role + " login form", "!!document.querySelector('#username')&&!!document.querySelector('#password')")
            fill("#username", role + "_demo")
            fill("#password", credentials[role + "_demo"])
            evaluate("document.querySelector('button[type=submit]').click()")
            check(role + " authenticated scoped workspace", "location.pathname==='/sites'&&document.querySelector('main')?.innerText.includes('Tra cứu lượt gửi')")
            setup_helpers()
            check(role + " search form ready after async lists load", "!!field('Mã vé (mã lượt)')&&!!field('Trạng thái lượt gửi')&&button('Tìm lượt gửi',main())?.disabled===false")
            if args.capture_existing:
                evaluate("searchStay(" + json.dumps(business["history_id"]) + ",'Đã ra')")
                check(role + " historical ticket ready for capture", "main().querySelectorAll('tbody tr').length===1")
                evaluate("button('Chi tiết',main()).click()")
                check(role + " historical snapshot ready for capture", "dialogText().includes('Giá ghi nhận lúc xe vào')&&dialogText().includes('" + business["history_id"] + "')")
                metrics(False)
                screenshot(role + "-history-basis-desktop")
                evaluate("closeDialog()")
                evaluate("searchStay(" + json.dumps(business["replacement_id"]) + ",'Đã hủy')")
                check(role + " cancelled replacement ready for capture", "main().querySelectorAll('tbody tr').length===1&&main().innerText.includes('" + NEW_PLATE + "')")
                evaluate("button('Chi tiết',main()).click()")
                check(role + " correction history ready for capture", "dialogText().includes('UAT giao diện P1: kết thúc tình huống thử')")
                metrics(True)
                screenshot(role + "-cancelled-history-mobile")
                evaluate("button('Xem / in vé thay thế',dialog()).click()")
                check(role + " cancelled ticket ready for capture", "dialogText().includes('Vé gửi xe đã hủy')&&dialogText().includes('Vé không còn hiệu lực')")
                screenshot(role + "-cancelled-ticket-mobile")
                metrics(False)
                continue
            if role == "manager":
                check("server has UAT frozen-price history", "(async()=>{window.p1Rows=rows(await apiRead('/sites/1/sessions?limit=100&status=completed'));window.historyStay=p1Rows.find(r=>r.license_plate.startsWith('UAT')&&r.billing_basis);window.oldStay=p1Rows.find(r=>!r.billing_basis);return !!historyStay&&!!oldStay;})()")
                business["history_id"] = evaluate("historyStay.id")
                evaluate("searchStay(historyStay.id,'Đã ra')")
                check("exact ticket lookup returns one historical stay", "main().querySelectorAll('tbody tr').length===1&&main().innerText.includes(historyStay.license_plate)")
                evaluate("button('Chi tiết',main()).click()")
                check("manager history displays saved rate and blocks", "dialogText().includes(historyStay.id)&&dialogText().includes('Giá ghi nhận lúc xe vào')&&dialogText().includes(historyStay.billing_basis.unit_price.toLocaleString('vi-VN')+' VND')&&dialogText().includes(historyStay.billing_basis.billable_blocks+' ×')")
                screenshot("manager-history-basis-desktop")
                evaluate("closeDialog()")
                evaluate("searchStay(oldStay.id,'Đã ra')")
                check("old stay exact lookup", "main().querySelectorAll('tbody tr').length===1&&main().innerText.includes(oldStay.license_plate)")
                evaluate("button('Chi tiết',main()).click()")
                check("old history does not invent a price snapshot", "dialogText().includes(oldStay.id)&&dialogText().includes('chưa có căn cứ giá được lưu')")
                evaluate("closeDialog()")
                check("available active slot for labelled UI admission", "(async()=>{window.initialAvailability=await apiRead('/sites/1/availability');window.slot=initialAvailability.slots.find(s=>s.available_now);window.type=rows(await apiRead('/catalog/vehicle-types')).find(t=>t.id===slot.vehicle_type_id);return !!slot&&!!type;})()")
                business["available_before"] = evaluate("initialAvailability.available_now")
                evaluate("input('Biển số xe'," + json.dumps(PLATE) + ");choose('Loại xe',type.name)")
                evaluate("choose('Vị trí nhận xe',slot.slot_name)")
                check("admission form ready", "!button('Xác nhận xe vào',main()).disabled")
                evaluate("button('Xác nhận xe vào',main()).click()")
                check("labelled UI admission succeeds", "main().innerText.includes('Đã ghi nhận xe vào.')")
                check("admitted stay exists once", "(async()=>{window.newRows=rows(await apiRead('/sites/1/sessions?status=active&license_plate=" + PLATE + "'));window.newStay=newRows[0];return newRows.length===1;})()")
                business["source_id"] = evaluate("newStay.id")
                evaluate("searchStay(newStay.id,'Đang đỗ')")
                check("new exact ticket lookup", "main().querySelectorAll('tbody tr').length===1&&main().innerText.includes('" + PLATE + "')")
                evaluate("button('Chi tiết',main()).click()")
                check("manager exception controls enabled", "['Hủy lượt vào nhầm','Xác nhận mất vé','Sửa biển số'].every(t=>button(t,dialog())&&!button(t,dialog()).disabled)")
                evaluate("button('Sửa biển số',dialog()).click()")
                check("correction asks for plate and reason", "!!field('Biển số đúng',dialog())&&!!field('Lý do xử lý',dialog())")
                evaluate("input('Biển số đúng'," + json.dumps(NEW_PLATE) + ",dialog());input('Lý do xử lý','UAT giao diện P1: đối chiếu biển số tại làn.',dialog())")
                check("correction confirmation ready", "!button('Xác nhận và lưu lý do',dialog()).disabled")
                evaluate("button('Xác nhận và lưu lý do',dialog()).click()")
                check("correction keeps old cancellation and linked history", "dialogText().includes('Đã sửa biển số bằng lượt thay thế')&&dialogText().includes('Đã hủy')&&dialogText().includes('" + PLATE + " → " + NEW_PLATE + "')")
                business["replacement_id"] = evaluate("(async()=>{const h=await apiRead('/sites/1/sessions/'+newStay.id+'/exceptions');return h.events.find(e=>e.action==='plate_corrected').replacement_session_id;})()")
                metrics(True)
                check("correction mobile dialog stays within viewport", "dialog().getBoundingClientRect().width<=innerWidth&&dialog().scrollWidth<=dialog().clientWidth+1")
                screenshot("manager-correction-mobile")
                evaluate("button('Xem / in vé thay thế',dialog()).click()")
                check("replacement ticket shows correct plate and active label", "dialogText().includes('" + NEW_PLATE + "')&&dialogText().includes('Xe đang trong bãi')&&!!dialog().querySelector('img[alt=\"Mã QR tra cứu lượt gửi xe\"]')")
                screenshot("manager-replacement-ticket-mobile")
                call("Emulation.setEmulatedMedia", {"media": "print"})
                check("print isolates the replacement ticket", "getComputedStyle(document.querySelector('#root')).display==='none'&&!!document.querySelector('.parking-ticket-print').getClientRects().length")
                pdf = call("Page.printToPDF", {"printBackground": True, "paperWidth": 3.15, "paperHeight": 7, "marginTop": .15, "marginBottom": .15, "marginLeft": .1, "marginRight": .1})
                (RUN / "replacement-ticket.pdf").write_bytes(base64.b64decode(pdf["data"]))
                call("Emulation.setEmulatedMedia", {"media": "screen"})
                evaluate("closeDialog()")
                metrics(False)
                evaluate("searchStay(" + json.dumps(business["replacement_id"]) + ",'Đang đỗ')")
                check("replacement found by its own ticket id", "main().querySelectorAll('tbody tr').length===1&&main().innerText.includes('" + NEW_PLATE + "')")
                evaluate("button('Chi tiết',main()).click()")
                check("replacement carries source correction audit", "dialogText().includes('" + PLATE + " → " + NEW_PLATE + "')&&dialogText().includes('UAT giao diện P1')")
                evaluate("button('Xác nhận mất vé',dialog()).click()")
                check("lost ticket reason form", "!!field('Lý do xử lý',dialog())")
                evaluate("input('Lý do xử lý','UAT giao diện P1: đã kiểm tra giấy tờ xe.',dialog())")
                evaluate("button('Xác nhận và lưu lý do',dialog()).click()")
                check("lost-ticket approval has auditable reason", "dialogText().includes('Đã lưu xác nhận mất vé')&&dialogText().includes('UAT giao diện P1: đã kiểm tra giấy tờ xe.')")
                evaluate("button('Xem phí và cho xe ra',dialog()).click()")
                check("checkout shows server basis before money confirmation", "dialogText().includes('Xem phí và xác nhận xe ra')&&dialogText().includes('Giá ghi nhận lúc xe vào')&&dialogText().includes('Số đơn vị tính phí')")
                check("paid checkout still requires confirmation", "button('Đã thu tiền — cho xe ra',dialog())?.disabled===true&&!!dialog().querySelector('input[type=checkbox]')")
                metrics(True)
                screenshot("manager-checkout-basis-mobile")
                evaluate("button('Hủy',dialog()).click()")
                metrics(False)
                evaluate("button('Chi tiết',main()).click()")
                check("replacement can be cancelled after preview only", "button('Hủy lượt vào nhầm',dialog())?.disabled===false")
                evaluate("button('Hủy lượt vào nhầm',dialog()).click()")
                evaluate("input('Lý do xử lý','UAT giao diện P1: kết thúc tình huống thử, trả vị trí.',dialog())")
                evaluate("button('Xác nhận và lưu lý do',dialog()).click()")
                check("cancellation records reason and removes checkout action", "dialogText().includes('Đã hủy lượt và trả chỗ trống')&&!button('Xem phí và cho xe ra',dialog())")
                evaluate("closeDialog()")
                check("cancelled UI stay releases its slot", "(async()=>{const a=await apiRead('/sites/1/availability');return a.available_now===initialAvailability.available_now;})()")
                call("Page.navigate", {"url": ORIGIN + "/audit-logs"})
                check("manager operational audit labels", "document.querySelector('main')?.innerText.includes('Nhật ký hoạt động')&&document.querySelector('main')?.innerText.includes('Sửa biển số')&&document.querySelector('main')?.innerText.includes('Xác nhận mất vé')")
            else:
                evaluate("searchStay(" + json.dumps(business["history_id"]) + ",'Đã ra')")
                check("staff can find exact historical ticket", "main().querySelectorAll('tbody tr').length===1")
                evaluate("button('Chi tiết',main()).click()")
                check("staff sees operational billing basis without manager actions", "dialogText().includes('Giá ghi nhận lúc xe vào')&&!dialogText().includes('Xử lý của quản lý')&&['Hủy lượt vào nhầm','Xác nhận mất vé','Sửa biển số'].every(t=>!button(t,dialog()))")
                evaluate("closeDialog()")
                evaluate("searchStay(" + json.dumps(business["replacement_id"]) + ",'Đã hủy')")
                check("staff cancelled ticket lookup", "main().querySelectorAll('tbody tr').length===1&&main().innerText.includes('" + NEW_PLATE + "')&&main().innerText.includes('Đã hủy')")
                evaluate("button('Chi tiết',main()).click()")
                check("staff reads correction loss and cancellation audit", "dialogText().includes('UAT giao diện P1: đối chiếu biển số')&&dialogText().includes('UAT giao diện P1: đã kiểm tra giấy tờ xe.')&&dialogText().includes('UAT giao diện P1: kết thúc tình huống thử')&&!dialogText().includes('Xử lý của quản lý')&&!button('Xem phí và cho xe ra',dialog())")
                metrics(True)
                check("staff history mobile has no horizontal overflow", "dialog().getBoundingClientRect().width<=innerWidth&&dialog().scrollWidth<=dialog().clientWidth+1")
                screenshot("staff-cancelled-history-mobile")
                evaluate("button('Xem / in vé thay thế',dialog()).click()")
                check("cancelled replacement prints an invalid ticket label", "dialogText().includes('Vé gửi xe đã hủy')&&dialogText().includes('Vé không còn hiệu lực')&&!button('Xem phí và cho xe ra',dialog())")
                screenshot("staff-cancelled-ticket-mobile")
        call("Storage.clearDataForOrigin", {"origin": ORIGIN, "storageTypes": "all"})
        completed = True
finally:
    chrome.terminate()
    try:
        chrome.wait(timeout=5)
    except subprocess.TimeoutExpired:
        chrome.kill()
        chrome.wait(timeout=5)
    log.close()
    # Only the disposable profile made by this script; never another browser.
    if profile.resolve().parent == RUN.resolve():
        for _ in range(20):
            try:
                shutil.rmtree(profile)
                break
            except FileNotFoundError:
                break
            except PermissionError:
                time.sleep(.1)
    writes = [row for row in requests if row["method"] not in ("GET", "HEAD", "OPTIONS")]
    allowed = {"/api/auth/login", "/api/v2/sites/1/check-in"}
    writes_allowed = all(row["path"] in allowed or row["path"].endswith(("/correct-plate", "/lost-ticket", "/cancel")) for row in writes)
    report = {"passed": completed and writes_allowed and not http_errors and not runtime_errors,
              "scope": "Real backend P1 UAT clone; labelled synthetic admission/correction/loss/cancellation; no AI, payment, external provider, or canonical DB writes",
              "checks": checks, "business": business, "synthetic_plate": PLATE, "replacement_plate": NEW_PLATE,
              "writes": writes, "writes_within_authorized_scope": writes_allowed,
              "http_errors": http_errors, "runtime_errors": runtime_errors, "private_browser_profile_removed": not profile.exists()}
    if args.resume_staff:
        report["resumed_from"] = str(args.resume_staff)
    if args.capture_existing:
        report["scope"] = "Read-only P1 visual capture of existing synthetic stays after dialog transitions settle; only login audit writes"
        report["captured_from"] = str(args.capture_existing)
    (RUN / "result.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"passed": report["passed"], "checks": len(checks), "artifact_directory": str(RUN)}, ensure_ascii=True))
    if completed and not report["passed"]:
        raise AssertionError("Post-run verification failed; inspect sanitized report")
