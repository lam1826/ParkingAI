"""Academic expansion UAT, isolated database and private headless browser only."""
import base64
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import traceback
import urllib.request
import uuid

from websockets.sync.client import connect

sys.stdout.reconfigure(encoding="utf-8")
ROOT = Path(__file__).resolve().parents[2]
RUN = ROOT / "backend" / "artifacts" / "uat" / uuid.uuid4().hex[:10]
RUN.mkdir(parents=True)
PASSWORD = "DemoParkingAI!2026"
URL = "http://127.0.0.1:18960"
summary = {"run": str(RUN), "database": str(RUN / "scratch.db"), "production_untouched": True, "checks": [], "screenshots": []}


class CDP:
    def __init__(self, ws):
        self.ws, self.seq, self.events = ws, 0, []

    def call(self, method, params=None):
        self.seq += 1
        self.ws.send(json.dumps({"id": self.seq, "method": method, "params": params or {}}))
        while True:
            value = json.loads(self.ws.recv(timeout=40))
            if value.get("id") == self.seq:
                if "error" in value:
                    raise RuntimeError(value["error"])
                return value.get("result", {})
            self.events.append(value)

    def evaluate(self, expression):
        result = self.call("Runtime.evaluate", {"expression": expression, "awaitPromise": True, "returnByValue": True})
        if "exceptionDetails" in result:
            raise RuntimeError(result["exceptionDetails"])
        return result.get("result", {}).get("value")

    def wait(self, expression, timeout=25):
        until = time.monotonic() + timeout
        while time.monotonic() < until:
            # Navigation briefly has no body; wait for the document before DOM assertions.
            if self.evaluate("Boolean(document.body) && (" + expression + ")"):
                return
            time.sleep(0.12)
        raise RuntimeError("Browser condition not met: " + expression + "\n" + self.evaluate("document.body.innerText")[:5000])

    def capture(self, name):
        self.evaluate("window.scrollTo(0,0)")
        time.sleep(0.2)
        size = self.call("Page.getLayoutMetrics")["cssContentSize"]
        shot = self.call("Page.captureScreenshot", {"format": "png", "captureBeyondViewport": True,
            "clip": {"x": 0, "y": 0, "width": size["width"], "height": size["height"], "scale": 1}})
        path = RUN / (name + ".png")
        path.write_bytes(base64.b64decode(shot["data"]))
        (RUN / (name + ".txt")).write_text(self.evaluate("document.body.innerText"), encoding="utf-8")
        overflow = self.evaluate("({width:innerWidth,scroll:document.documentElement.scrollWidth})")
        summary["screenshots"].append({"name": name, "path": str(path), "url": self.evaluate("location.href"), "overflow": overflow})
        return str(path)


def fill(selector, value):
    cdp.evaluate("(() => { const el=document.querySelector(" + json.dumps(selector) + "); if(!el) throw new Error('No field '+" + json.dumps(selector) + "); const proto=el.tagName==='TEXTAREA'?HTMLTextAreaElement.prototype:HTMLInputElement.prototype; Object.getOwnPropertyDescriptor(proto,'value').set.call(el," + json.dumps(value) + "); el.dispatchEvent(new Event('input',{bubbles:true})); el.dispatchEvent(new Event('change',{bubbles:true})); })()")


def field(label, value):
    cdp.wait("[...document.querySelectorAll('.MuiInputLabel-root,label')].some(e=>e.textContent.replace('*','').trim()===" + json.dumps(label) + ")")
    selector = cdp.evaluate("(() => {const l=[...document.querySelectorAll('.MuiInputLabel-root,label')].find(e=>e.textContent.replace('*','').trim()===" + json.dumps(label) + "); if(!l) throw new Error('No label '+" + json.dumps(label) + "); return '#'+CSS.escape(l.getAttribute('for') || l.id.replace(/-label$/,''))})()")
    fill(selector, value)


def click(text, selector="button", contains=False):
    if selector == "button":
        selector = "button:not([role=tab])"
    match = "e.textContent.trim().includes(" + json.dumps(text) + ")" if contains else "e.textContent.trim()===" + json.dumps(text)
    expression = "[...document.querySelectorAll(" + json.dumps(selector) + ")].find(e=>" + match + ")"
    cdp.wait("Boolean(" + expression + ") && !(" + expression + ").disabled")
    cdp.evaluate(expression + ".click()")


def select(label, text, contains=False):
    cdp.wait("[...document.querySelectorAll('.MuiInputLabel-root,label')].some(e=>e.textContent.replace('*','').trim()===" + json.dumps(label) + ")")
    cdp.evaluate("(() => {const l=[...document.querySelectorAll('.MuiInputLabel-root,label')].find(e=>e.textContent.replace('*','').trim()===" + json.dumps(label) + "); const el=document.getElementById(l.getAttribute('for') || l.id.replace(/-label$/,'')); el.dispatchEvent(new MouseEvent('mousedown',{bubbles:true})); })()")
    click(text, "[role=option]", contains)


def navigate(path, text):
    cdp.call("Page.navigate", {"url": URL + path})
    cdp.wait("document.body.innerText.includes(" + json.dumps(text) + ")")
    cdp.wait("!document.body.innerText.includes('Đang tải dữ liệu…')")
    time.sleep(0.35)


def login(name):
    cdp.call("Page.navigate", {"url": URL + "/login"})
    cdp.wait("!!document.querySelector('#username')")
    cdp.evaluate("localStorage.clear()")
    fill("#username", name); fill("#password", PASSWORD)
    click("Đăng Nhập")
    cdp.wait("location.pathname!='/login' && Boolean(localStorage.getItem('token'))")
    time.sleep(0.3)


def request(method, path, data=None):
    token = cdp.evaluate("localStorage.getItem('token')")
    req = urllib.request.Request(URL + path, method=method, headers={"Authorization": "Bearer " + token, "Content-Type": "application/json"}, data=json.dumps(data).encode() if data is not None else None)
    with urllib.request.urlopen(req, timeout=30) as response:
        body = response.read()
        return json.loads(body) if body else None


def step(name, fn):
    try:
        result = fn()
        summary["checks"].append({"name": name, "passed": True, "result": result})
        print("PASS", name, flush=True)
    except Exception as exc:
        summary["checks"].append({"name": name, "passed": False, "error": str(exc)})
        print("FAIL", name, str(exc)[:2000], flush=True)
        cdp.capture("failure-" + str(len(summary["checks"])))
    (RUN / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")


server = chrome = None
try:
    seeded = subprocess.run([sys.executable, "-m", "expansion.demo_seed", "--database", str(RUN / "scratch.db"), "--password", PASSWORD], cwd=ROOT / "backend", capture_output=True, text=True, encoding="utf-8")
    (RUN / "seed.log").write_text(seeded.stdout + seeded.stderr, encoding="utf-8")
    if seeded.returncode:
        raise RuntimeError("Demo seed failed: " + seeded.stderr[-4000:])
    log = (RUN / "server.log").open("w", encoding="utf-8")
    server = subprocess.Popen([sys.executable, str(ROOT / "scripts" / "demo_server.py"), "--database", str(RUN / "scratch.db"), "--port", "18960"], cwd=ROOT, stdout=log, stderr=log, creationflags=subprocess.CREATE_NO_WINDOW)
    for _ in range(150):
        try:
            with urllib.request.urlopen(URL + "/config.js", timeout=1) as response:
                if response.status == 200: break
        except Exception:
            if server.poll() is not None:
                raise RuntimeError((RUN / "server.log").read_text(encoding="utf-8")[-5000:])
            time.sleep(0.2)
    chrome_log = (RUN / "chrome.log").open("w", encoding="utf-8")
    chrome = subprocess.Popen([r"C:\Program Files\Google\Chrome\Application\chrome.exe", "--headless=new", "--disable-gpu", "--no-first-run", "--no-default-browser-check", "--disable-background-networking", "--disable-component-update", "--disable-sync", "--remote-debugging-port=18962", "--remote-debugging-address=127.0.0.1", "--user-data-dir=" + str(RUN / "chrome-profile"), "--window-size=1440,1050", "about:blank"], stdout=chrome_log, stderr=chrome_log, creationflags=subprocess.CREATE_NO_WINDOW)
    for _ in range(80):
        try:
            targets = json.load(urllib.request.urlopen("http://127.0.0.1:18962/json/list", timeout=1))
            if targets: break
        except Exception: time.sleep(0.1)
    target = next(row for row in targets if row["type"] == "page")
    with connect(target["webSocketDebuggerUrl"], max_size=40_000_000) as ws:
        cdp = CDP(ws)
        for method in ("Page.enable", "Runtime.enable", "Log.enable"):
            cdp.call(method)
        cdp.call("Browser.setDownloadBehavior", {"behavior": "allow", "downloadPath": str(RUN)})
        cdp.call("Emulation.setDeviceMetricsOverride", {"width": 1440, "height": 1050, "deviceScaleFactor": 1, "mobile": False})

        def customer_payment():
            login("customer_demo")
            navigate("/portal", "Bãi xe của tôi")
            click("Đăng ký & QR", "[role=tab]")
            select("Xe sử dụng", "30A-123.45")
            select("Gói vé tháng", "DEMO A - Ô tô DEMO", contains=True)
            click("Tạo đơn và mã QR")
            cdp.wait("!!document.querySelector('img[alt*=\"Mã QR thanh toán\"]')?.complete")
            cdp.capture("desktop-qr-pending")
            click("Giả lập thanh toán thành công")
            cdp.wait("document.body.innerText.includes('Đã cấp vé')")
            orders = request("GET", "/api/v2/me/orders")["items"]
            assert len(orders) == 1 and orders[0]["status"] == "fulfilled", orders
            summary["order_id"] = orders[0]["id"]
            click("Vé tháng", "[role=tab]")
            cdp.wait("document.body.innerText.includes('30A-123.45') && document.body.innerText.includes('Vé tháng của tôi')")
            click("Đăng ký & QR", "[role=tab]")
            # Completed orders intentionally remove payment credentials/QR.
            cdp.wait("document.body.innerText.includes('Đã cấp vé') && !document.querySelector('img[alt*=\"Mã QR thanh toán\"]')")
            field("Lý do yêu cầu hoàn mô phỏng", "Kiểm tra hoàn mô phỏng trên dữ liệu UAT")
            click("Gửi yêu cầu hoàn mô phỏng")
            cdp.wait("document.body.innerText.includes('Đã gửi yêu cầu hoàn tiền mô phỏng')")
            click("Lịch sử & chứng từ", "[role=tab]")
            click("Tải PDF")
            cdp.wait("document.body.innerText.includes('Đã tải chứng từ PDF')")
            for _ in range(40):
                pdfs = list(RUN.glob("ParkingAI-*.pdf"))
                if pdfs: break
                time.sleep(.1)
            assert pdfs and pdfs[0].read_bytes().startswith(b"%PDF")
            summary["receipt_pdf"] = str(pdfs[0])
            return {"order_status": "fulfilled", "pdf_bytes": pdfs[0].stat().st_size, "refund_requested": True, "pass_receipt_updated_without_page_refresh": True}
        step("Customer creates random QR, simulates payment, downloads PDF and requests refund", customer_payment)

        def customer_bookings():
            navigate("/reservations", "Đặt chỗ tại")
            select("Xe của tôi", "30A-123.45")
            click("Đặt chỗ")
            cdp.wait("document.body.innerText.includes('Đã giữ chỗ')")
            reservations = request("GET", "/api/v2/me/reservations")
            assert reservations[0]["status"] == "confirmed"
            click("Hủy")
            cdp.wait("document.body.innerText.includes('Đã hủy đặt chỗ')")
            click("Danh sách chờ", "[role=tab]")
            select("Xe của tôi", "30A-123.45")
            now = datetime.now(timezone(timedelta(hours=7)))
            field("Bắt đầu (giờ Việt Nam)", (now + timedelta(minutes=1)).strftime("%Y-%m-%dT%H:%M"))
            field("Kết thúc (giờ Việt Nam)", (now + timedelta(hours=2)).strftime("%Y-%m-%dT%H:%M"))
            click("Tham gia danh sách chờ")
            cdp.wait("document.body.innerText.includes('Đã tham gia danh sách chờ')")
            assert request("GET", "/api/v2/me/waitlist")[0]["status"] == "waiting"
            cdp.capture("desktop-customer-waitlist")
            return {"reservation_cancelled": True, "waitlist_created": True}
        step("Customer reserves, cancels and joins waitlist", customer_bookings)

        def admin_refund():
            login("admin_demo")
            navigate("/portal-admin", "Khách & đơn vé")
            click("Yêu cầu hoàn", "[role=tab]")
            click("Duyệt")
            field("Ghi chú xác minh / lý do xử lý", "Đã xác minh yêu cầu thử nghiệm")
            cdp.evaluate("document.querySelector('[role=dialog] input[type=checkbox]').click()")
            click("Xác nhận")
            cdp.wait("![...document.querySelectorAll('[role=dialog]')].some(el=>el.getClientRects().length && getComputedStyle(el).visibility!=='hidden') && document.body.innerText.includes('Đã duyệt')")
            cdp.capture("desktop-admin-refund")
            order = next(row for row in request("GET", "/api/v2/portal/admin/orders")["items"] if row["id"] == summary["order_id"])
            assert order["status"] == "refunded", order
            return {"order_status": order["status"]}
        step("Admin reviews and approves demo refund", admin_refund)

        def site_operations():
            login("staff_demo")
            navigate("/sites?site=1", "Ghi nhận xe vào")
            click("Danh sách chờ", "[role=tab]")
            click("Cấp chỗ trống")
            cdp.wait("document.body.innerText.includes('Đã cấp chỗ')")
            click("Đặt chỗ", "[role=tab]")
            booked = request("GET", "/api/v2/sites/1/reservations")
            starts = datetime.fromisoformat(next(row for row in booked if row["status"] == "confirmed")["start_at"])
            wait_seconds = max(0, (starts - datetime.now(timezone.utc)).total_seconds())
            if wait_seconds:
                time.sleep(min(wait_seconds + .2, 60))
            click("Xe đã đến")
            cdp.wait("document.body.innerText.includes('Đã xác nhận khách đến')")
            click("Xe vào / ra", "[role=tab]")
            field("Tìm đúng biển số", "30A-123.45")
            click("Tìm lượt gửi")
            cdp.wait("!document.body.innerText.includes('Đang tải dữ liệu…')")
            click("Xem phí / xe ra")
            cdp.wait("!!document.querySelector('[role=dialog]') && document.body.innerText.includes('Số tiền cần thu')")
            cdp.capture("desktop-signed-checkout")
            cdp.evaluate("document.querySelector('[role=dialog] input[value=cash]').click()")
            cdp.evaluate("document.querySelector('[role=dialog] input[type=checkbox]').click()")
            click("Đã thu tiền — cho xe ra")
            cdp.wait("!document.querySelector('[role=dialog][aria-labelledby=checkout-title]')")
            cdp.wait("document.body.innerText.includes('Đã ghi nhận xe ra.')")
            done = request("GET", "/api/v2/sites/1/sessions?license_plate=30A-123.45&status=completed")
            assert len(done) == 1 and done[0]["status"] == "completed" and done[0]["parking_fee"] > 0
            field("Biển số xe", "UAT-43210")
            select("Loại xe", "Ô tô DEMO")
            availability = request("GET", "/api/v2/sites/1/availability")
            free_slot = next(row for row in availability["slots"] if row["available_now"] and row["vehicle_type_id"] == 1)
            select("Vị trí nhận xe", free_slot["slot_name"], contains=True)
            click("Xác nhận xe vào")
            cdp.wait("document.body.innerText.includes('Đã ghi nhận xe vào')")
            assert len(request("GET", "/api/v2/sites/1/sessions?license_plate=UAT-43210&status=active")) == 1
            return {"waitlist_offered": True, "reservation_arrived": True, "signed_checkout_fee": done[0]["parking_fee"], "walkin_admitted": True}
        step("Staff offers waitlist, confirms arrival, performs signed checkout and walk-in", site_operations)

        def camera():
            navigate("/vision", "Chụp và nhận diện")
            cdp.wait("document.querySelectorAll('input[type=file]').length===2")
            doc = cdp.call("DOM.getDocument")
            file_node = cdp.call("DOM.querySelector", {"nodeId": doc["root"]["nodeId"], "selector": "input[type=file]"})["nodeId"]
            cdp.call("DOM.setFileInputFiles", {"nodeId": file_node, "files": [str(ROOT / "backend" / "artifacts" / "vision" / "rolls-royce-cc0.jpg")]})
            cdp.wait("document.body.innerText.includes('Kiểm tra kết quả')", timeout=140)
            cdp.wait("!!document.querySelector('img[alt=\"Ảnh phương tiện để kiểm tra biển số\"]')?.complete")
            observations = request("GET", "/api/v2/vision/observations?site_id=1")
            assert observations and observations[0]["ocr_status"] == "recognized", observations
            cdp.capture("desktop-camera-yolo-ocr")
            field("Biển số đã kiểm tra", "UAT-56789")
            click("Xác nhận và xử lý xe")
            cdp.wait("location.pathname==='/sites' && document.body.innerText.includes('Ghi nhận xe vào')")
            cdp.wait("[...document.querySelectorAll('input')].some(el=>el.value==='UAT-56789')")
            assert request("GET", "/api/v2/sites/1/sessions?license_plate=UAT-56789") == []
            return {"ocr_status": observations[0]["ocr_status"], "suggested_plate": observations[0]["suggested_plate"], "review_prefill_only": True}
        step("Phone photo path runs actual YOLO and OCR with manual review before operations", camera)

        def forecast():
            navigate("/insights", "Dự báo & điều hành")
            cdp.wait("Boolean(document.querySelector('.recharts-surface'))")
            click("Tính phương án")
            cdp.wait("document.body.innerText.includes('Nhân viên đề xuất')")
            forecast_data = request("GET", "/api/v2/insights/forecast?site_id=1&horizon_hours=24")
            assert forecast_data["status"] == "ready" and len(forecast_data["predictions"]) == 24
            coverage = forecast_data["coverage"]
            assert coverage["observation_completeness"] == "unknown"
            assert coverage["hours_with_arrivals"] > 0 and coverage["hours_zero_filled"] > 0
            assert coverage["hours_with_arrivals"] + coverage["hours_zero_filled"] == coverage["hours_in_window"]
            assert cdp.evaluate("document.body.innerText.includes('Giờ được điền 0') && document.body.innerText.includes('Chưa xác định')")
            cdp.capture("desktop-forecast-staff")
            return {"backtest": forecast_data["backtest"], "predictions": len(forecast_data["predictions"]), "coverage": coverage}
        step("Forecast chart and staffing scenario from synthetic 56-day history", forecast)

        def scope_switching():
            login("admin_demo")
            navigate("/vision", "Chụp và nhận diện")
            click("Xem ảnh")
            cdp.wait("document.body.innerText.includes('Kiểm tra kết quả')")
            cdp.evaluate("(() => { const open=XMLHttpRequest.prototype.open,send=XMLHttpRequest.prototype.send; XMLHttpRequest.prototype.open=function(method,url,...rest){this.uatUrl=String(url);return open.call(this,method,url,...rest)}; XMLHttpRequest.prototype.send=function(body){if(this.uatUrl?.includes('site_id=2')){setTimeout(()=>send.call(this,body),1200);return}return send.call(this,body)}; })()")
            select("Bãi xe", "DEMO - Bãi B")
            cdp.wait("document.body.innerText.includes('Đang tải dữ liệu…')")
            assert not cdp.evaluate("document.body.innerText.includes('Kiểm tra kết quả') || document.body.innerText.includes('UAT-56789')")
            assert cdp.evaluate("[...document.querySelectorAll('[role=combobox]')].every(el=>!el.textContent.includes('Điện thoại A'))")
            select("Bãi xe", "DEMO - Bãi A")
            cdp.wait("document.body.innerText.includes('Điện thoại A - Cổng vào')")
            time.sleep(1.5)
            assert not cdp.evaluate("[...document.querySelectorAll('[role=combobox]')].some(el=>el.textContent.includes('Điện thoại B'))")
            cdp.capture("desktop-camera-fast-site-switch")
            navigate("/insights", "Dự báo & điều hành")
            cdp.wait("Boolean(document.querySelector('.recharts-surface'))")
            click("Tính phương án")
            cdp.wait("document.body.innerText.includes('Nhân viên đề xuất')")
            field("Thời gian xử lý mỗi xe (giây)", "60")
            cdp.wait("!document.body.innerText.includes('Nhân viên đề xuất')")
            click("Tính phương án")
            cdp.wait("document.body.innerText.includes('Nhân viên đề xuất')")
            select("Bãi xe", "DEMO - Bãi B")
            cdp.wait("!document.body.innerText.includes('Nhân viên đề xuất')")
            cdp.wait("Boolean(document.querySelector('.recharts-surface'))")
            select("Khoảng dự báo", "6 giờ tới")
            cdp.wait("!document.body.innerText.includes('Đang tải dữ liệu…')")
            cdp.capture("desktop-forecast-site-b")
            return {"fast_a_b_a_camera_stale_data_hidden": True, "staff_input_and_site_change_invalidates_plan": True}
        step("Fast site changes hide stale camera data and staff plans expire when assumptions change", scope_switching)

        def account_switching():
            # Register only in this run's scratch DB. Keep the same browser document
            # through logout/login so a full navigation cannot hide stale-state bugs.
            request("POST", "/api/auth/register", {"username": "uat_second_customer", "full_name": "UAT second customer", "password": PASSWORD, "role": "customer"})
            login("customer_demo")
            navigate("/portal", "Bãi xe của tôi")
            cdp.wait("document.body.innerText.includes('30A-123.45')")
            cdp.evaluate("(() => { const oldToken=localStorage.getItem('token'),open=XMLHttpRequest.prototype.open,send=XMLHttpRequest.prototype.send; XMLHttpRequest.prototype.open=function(method,url,...rest){this.uatAccountUrl=String(url);return open.call(this,method,url,...rest)}; XMLHttpRequest.prototype.send=function(body){if(this.uatAccountUrl?.endsWith('/me/vehicles') && !window.uatDelayedAccountRequest){window.uatDelayedAccountRequest=true;this.addEventListener('loadend',()=>{window.uatAccountResponseAfterLogin=Boolean(localStorage.getItem('token')) && localStorage.getItem('token')!==oldToken;window.uatAccountRequestComplete=true;});setTimeout(()=>send.call(this,body),3000);return}return send.call(this,body)}; })()")
            click("Làm mới")
            cdp.wait("window.uatDelayedAccountRequest === true")
            cdp.evaluate("[...document.querySelectorAll('header .MuiToolbar-root button')].at(-1).click()")
            click("Đăng xuất", "[role=menuitem]")
            cdp.wait("!!document.querySelector('#username') && !localStorage.getItem('token')")
            fill("#username", "uat_second_customer"); fill("#password", PASSWORD)
            click("Đăng Nhập")
            cdp.wait("location.pathname === '/portal' && document.body.innerText.includes('Tạo hồ sơ khách hàng')")
            cdp.wait("window.uatAccountRequestComplete === true")
            assert cdp.evaluate("window.uatAccountResponseAfterLogin === true")
            assert not cdp.evaluate("document.body.innerText.includes('30A-123.45') || document.body.innerText.includes('59A1-123.45') || document.body.innerText.includes('Khách hàng DEMO')")
            assert request("GET", "/api/v2/me/profile")["linked"] is False
            cdp.capture("desktop-account-switch-isolation")
            return {"same_document_logout_login": True, "late_previous_customer_response_hidden": True, "new_customer_unlinked": True}
        step("Logout and login another customer while the previous vehicle request is delayed", account_switching)

        def mobile():
            cdp.call("Emulation.setDeviceMetricsOverride", {"width": 390, "height": 844, "deviceScaleFactor": 1, "mobile": True})
            login("staff_demo")
            navigate("/sites", "Ghi nhận xe vào")
            cdp.capture("mobile-site-operations")
            login("customer_demo")
            navigate("/portal", "Bãi xe của tôi")
            click("Đăng ký & QR", "[role=tab]")
            select("Xe sử dụng", "30A-123.45")
            select("Gói vé tháng", "DEMO A - Ô tô DEMO", contains=True)
            click("Tạo đơn và mã QR")
            cdp.wait("!!document.querySelector('img[alt*=\"Mã QR thanh toán\"]')?.complete")
            cdp.capture("mobile-customer-qr")
            navigate("/reservations", "Đặt chỗ tại")
            cdp.capture("mobile-reservations")
            overflow_free = all(row["overflow"]["scroll"] <= row["overflow"]["width"] + 1 for row in summary["screenshots"])
            assert overflow_free, summary["screenshots"]
            return {"viewport": "390x844", "overflow_free": overflow_free}
        step("Mobile portal, reservations and site operations layout", mobile)

        summary["runtime_exceptions"] = [row["params"] for row in cdp.events if row.get("method") == "Runtime.exceptionThrown"]
        summary["console_errors"] = [row["params"] for row in cdp.events if row.get("method") == "Runtime.consoleAPICalled" and row.get("params", {}).get("type") == "error"]
        summary["browser_warnings"] = [row["params"] for row in cdp.events if row.get("method") == "Log.entryAdded" and row.get("params", {}).get("entry", {}).get("level") in {"error", "warning"}]
        (RUN / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
        print("RESULT", json.dumps({"run": str(RUN), "passed": sum(row["passed"] for row in summary["checks"]), "total": len(summary["checks"]), "runtime_exceptions": len(summary["runtime_exceptions"]), "console_errors": len(summary["console_errors"])}, ensure_ascii=False), flush=True)
        if any(not row["passed"] for row in summary["checks"]) or summary["runtime_exceptions"] or summary["console_errors"]:
            raise SystemExit(1)
finally:
    if chrome is not None and chrome.poll() is None:
        chrome.terminate(); chrome.wait(timeout=10)
    if server is not None and server.poll() is None:
        server.terminate(); server.wait(timeout=10)
