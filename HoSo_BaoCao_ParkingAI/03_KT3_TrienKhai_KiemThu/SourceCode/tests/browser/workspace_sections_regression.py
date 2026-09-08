"""Real workspace components with failures injected at the browser HTTP boundary.

Uses an isolated Vite server/private Chrome; never connects to a real backend.
"""
import base64
import json
from pathlib import Path
import subprocess
import sys
import time
import urllib.parse
import urllib.request
from uuid import uuid4

from websockets.sync.client import connect

sys.stdout.reconfigure(encoding="utf-8")
ROOT = Path(__file__).resolve().parents[2]
RUN = ROOT / "backend/artifacts/workspace-sections" / uuid4().hex[:10]
RUN.mkdir(parents=True)
output = (RUN / "process.log").open("w", encoding="utf-8")
children, requests, scenarios, console_errors = [], [], [], []
failures = set()
paged_bookings = False
delay_site_a = False
delayed_requests = []
BOOKING = {"id": "reservation-1", "site_id": 1, "vehicle_id": 1, "slot_id": 1,
           "start_at": "2026-09-08T08:00:00+07:00", "end_at": "2026-09-08T09:00:00+07:00",
           "arrival_deadline": "2026-09-08T08:15:00+07:00", "status": "confirmed"}
SLOT = {"id": 1, "slot_name": "A-01", "zone_id": 1, "zone_name": "Khu A", "vehicle_type_id": 1,
        "available_now": True, "is_occupied": False, "reserved": False}
ORG = {"id": 1, "site_id": 1, "name": "Đội xe kiểm thử"}
DATA = {
    "/api/v2/sites": [{"id": 1, "name": "Bãi kiểm thử A", "role": "admin"}],
    "/api/v2/catalog/vehicle-types": [{"id": 1, "name": "Ô tô", "is_active": True}],
    "/api/v2/sites/1/zones": [{"id": 1, "name": "Khu A", "capacity": 10, "is_active": True}],
    "/api/v2/sites/1/members": [{"id": 1, "user_id": 7, "role": "staff"}],
    "/api/v2/sites/1/organizations": [ORG],
    "/api/v2/sites/1/availability": {"site_id": 1, "total": 1, "occupied": 0, "available_now": 1, "reserved_slots": 0, "slots": [SLOT]},
    "/api/v2/sites/1/sessions": [{"id": "session-1", "license_plate": "51A12345", "slot_name": "A-01", "check_in_time": "2026-09-08T08:00:00+07:00", "status": "active", "parking_fee": None}],
    "/api/v2/sites/1/reservations": [BOOKING],
    "/api/v2/sites/1/allocations": [{**BOOKING, "id": "allocation-1", "status": "active"}],
    "/api/v2/sites/1/waitlist": [{**BOOKING, "id": "waitlist-1", "status": "waiting"}],
    "/api/v2/sites/1/vehicles": [{"id": 1, "license_plate": "51A12345", "vehicle_type_id": 1}],
    "/api/v2/me/organizations": [ORG],
    "/api/v2/me/profile": {"linked": True},
    "/api/v2/me/vehicles": [{"id": 1, "license_plate": "51A12345", "vehicle_type_id": 1}],
    "/api/v2/me/reservations": [BOOKING],
    "/api/v2/me/waitlist": [{**BOOKING, "id": "waitlist-1", "status": "waiting"}],
    "/api/v2/organizations/1/fleet": {"organization": ORG, "vehicles": [], "sessions": [], "total_sessions": 125, "active_sessions": 0, "completed_sessions": 125, "parking_fees": 125000, "fee_note": "Phí lượt gửi thử nghiệm."},
}


def counts():
    return {path: sum(row["path"] == path and row["method"] == "GET" for row in requests) for path in DATA}


try:
    children.append(subprocess.Popen(["node", "node_modules/vite/bin/vite.js", "--host", "127.0.0.1", "--port", "18974", "--strictPort"], cwd=ROOT / "frontend", stdout=output, stderr=output, creationflags=subprocess.CREATE_NO_WINDOW))
    children.append(subprocess.Popen([r"C:\Program Files\Google\Chrome\Application\chrome.exe", "--headless=new", "--disable-gpu", "--no-first-run", "--no-default-browser-check", "--disable-background-networking", "--disable-component-update", "--disable-sync", "--remote-debugging-port=18976", "--remote-debugging-address=127.0.0.1", "--user-data-dir=" + str(RUN / "chrome-profile"), "about:blank"], stdout=output, stderr=output, creationflags=subprocess.CREATE_NO_WINDOW))
    for attempt in range(100):
        try:
            urllib.request.urlopen("http://127.0.0.1:18974", timeout=1).close()
            pages = json.load(urllib.request.urlopen("http://127.0.0.1:18976/json", timeout=1))
            target = next(page for page in pages if page["type"] == "page")
            break
        except Exception:
            time.sleep(.2)
    else:
        raise RuntimeError("Private frontend/browser did not start")
    with connect(target["webSocketDebuggerUrl"], max_size=20_000_000) as ws:
        seq = 0

        def dispatch(method, params):
            global seq
            seq += 1
            ws.send(json.dumps({"id": seq, "method": method, "params": params}))
            return seq

        def call(method, params):
            wanted = dispatch(method, params)
            while True:
                response = json.loads(ws.recv(timeout=40))
                if response.get("method") == "Fetch.requestPaused":
                    paused = response["params"]
                    request = paused["request"]
                    path = urllib.parse.urlsplit(request["url"]).path
                    query = urllib.parse.parse_qs(urllib.parse.urlsplit(request["url"]).query)
                    requests.append({"method": request["method"], "path": path, "url": request["url"]})
                    status = 503 if path in failures else 200
                    payload = {"detail": "Tạm lỗi " + path} if status == 503 else DATA.get(path, {})
                    if paged_bookings and path == "/api/v2/me/reservations" and status == 200:
                        site_id = int(query.get("site_id", ["1"])[0])
                        payload = [{**BOOKING, "id": f"paged-{site_id}-{index:03}", "vehicle_id": index + 1 + (900 if site_id == 2 else 0),
                                    "status": "confirmed" if index % 2 == 0 else "cancelled"} for index in range(125)]
                        selected_status = query.get("status", [None])[0]
                        if selected_status:
                            payload = [row for row in payload if row["status"] == selected_status]
                        offset, limit = int(query.get("offset", ["0"])[0]), int(query.get("limit", ["50"])[0])
                        payload = payload[offset:offset + limit]
                        if delay_site_a and site_id == 1:
                            delayed_requests.append((paused["requestId"], payload))
                            continue
                    if request["method"] != "GET" and status == 200:
                        payload = {"id": "saved", "status": "arrived" if path.endswith("/arrive") else "cancelled"}
                    dispatch("Fetch.fulfillRequest", {"requestId": paused["requestId"], "responseCode": status,
                            "responseHeaders": [{"name": "Content-Type", "value": "application/json; charset=utf-8"}],
                            "body": base64.b64encode(json.dumps(payload, ensure_ascii=False).encode()).decode()})
                if response.get("method") == "Runtime.exceptionThrown":
                    console_errors.append(response["params"])
                if response.get("id") == wanted:
                    if "error" in response:
                        raise RuntimeError(response["error"])
                    return response.get("result", {})

        def evaluate(expression):
            result = call("Runtime.evaluate", {"expression": expression, "awaitPromise": True, "returnByValue": True})
            if "exceptionDetails" in result:
                raise RuntimeError(result["exceptionDetails"])
            return result.get("result", {}).get("value")

        def screenshot(name, mobile=False):
            call("Emulation.setDeviceMetricsOverride", {"width": 390 if mobile else 1440, "height": 844 if mobile else 1000, "deviceScaleFactor": 1, "mobile": mobile})
            evaluate("new Promise(resolve => setTimeout(resolve, 100))")
            data = call("Page.captureScreenshot", {"format": "png", "captureBeyondViewport": True})
            (RUN / f"{name}.png").write_bytes(base64.b64decode(data["data"]))

        def scenario(name, checks):
            scenarios.append({"scenario": name, "checks": checks, "passed": all(checks.values())})

        call("Runtime.enable", {})
        call("Fetch.enable", {"patterns": [{"urlPattern": "*/api/*"}]})
        call("Page.addScriptToEvaluateOnNewDocument", {"source": "window.__PARKINGAI_CONFIG__={API_URL:'http://127.0.0.1:18974'};"})
        call("Page.navigate", {"url": "http://127.0.0.1:18974"})
        for attempt in range(100):
            if evaluate("document.readyState === 'complete' && !!window.$RefreshReg$"):
                break
            time.sleep(.2)
        evaluate(r"""(async () => {
          const source = await (await fetch('/src/pages/Expansion/SitesWorkspace.jsx')).text();
          const main = await (await fetch('/src/main.jsx')).text();
          const dependency = (text, name) => text.match(new RegExp('["\\\']([^"\\\']*/deps/' + name + '\\.js[^"\\\']*)["\\\']'))[1];
          const react = await import(dependency(source,'react')); const React = react.default || react;
          const dom = await import(dependency(main,'react-dom_client')); const {createRoot} = dom.default || dom;
          const routing = await import(dependency(source,'react-router-dom')); const {MemoryRouter} = routing.default || routing;
          const mui = await import(dependency(source,'@mui_material')); const {ThemeProvider} = mui.default || mui;
          const {default: theme} = await import('/src/theme/index.js');
          const {default: api} = await import('/src/services/api.js');
          api.defaults.baseURL = location.origin;
          const {AuthContext} = await import('/src/context/AuthContext.jsx');
          const {default: Sites} = await import('/src/pages/Expansion/SitesWorkspace.jsx');
          const {default: Reservations} = await import('/src/pages/Expansion/ReservationsPage.jsx');
          const {default: Fleet} = await import('/src/pages/Expansion/FleetSection.jsx');
          document.getElementById('root').style.display = 'none';
          let root, host;
          window.pause = () => new Promise(resolve => setTimeout(resolve, 40));
          window.until = async (predicate) => { for(let n=0;n<100;n++){ if(predicate()) return true; await pause(); } return false; };
          window.visibleText = () => host?.innerText || '';
          window.control = (label) => {
            const found=[...host.querySelectorAll('label,[id$="-label"]')].find(el=>el.textContent.replace('*','').trim()===label);
            return found && (document.getElementById(found.htmlFor) || [...host.querySelectorAll('[role=combobox]')].find(el=>el.getAttribute('aria-labelledby')?.split(' ').includes(found.id)));
          };
          window.button = (text) => [...host.querySelectorAll('button')].find(el=>el.textContent.trim()===text);
          window.clickTab = async (text) => {const tab=[...host.querySelectorAll('[role=tab]')].find(el=>el.textContent===text);if(!tab)return false;tab.click();await pause();return true;};
          window.setInput = (label,value) => {const input=control(label);Object.getOwnPropertyDescriptor(HTMLInputElement.prototype,'value').set.call(input,value);input.dispatchEvent(new Event('input',{bubbles:true}));};
          window.select = async (label, text) => {const el=control(label);el.dispatchEvent(new MouseEvent('mousedown',{bubbles:true}));await pause();const option=[...document.querySelectorAll('[role=option]')].find(el=>el.textContent.includes(text));if(!option)throw Error('Missing option '+text);option.click();await pause();};
          window.mountCase = async (kind) => {
            if(root){root.unmount();host.remove();} host=document.createElement('div');host.style.padding='24px';document.body.appendChild(host);root=createRoot(host);
            const component = kind==='sites' ? React.createElement(Sites) : kind==='reservations' ? React.createElement(Reservations) : React.createElement(Fleet,{organizations:[{id:1,site_id:1,name:'Đội xe kiểm thử'}]});
            root.render(React.createElement(ThemeProvider,{theme},React.createElement(MemoryRouter,null,React.createElement(AuthContext.Provider,{value:{user:{id:1,role:kind==='sites'?'admin':'customer'},loading:false}},component))));
            await until(()=>!visibleText().includes('Đang tải')&&visibleText().length>20);
            for(let n=0;n<5;n++) await pause();
          };
        })()""")

        for path in ("/api/v2/sites/1/members", "/api/v2/sites/1/organizations"):
            failures.clear()
            failures.add(path)
            evaluate("mountCase('sites')")
            state = evaluate("({typeEnabled:!!control('Loại xe')&&control('Loại xe').getAttribute('aria-disabled')!=='true',history:visibleText().includes('51A12345')})")
            (RUN / (path.rsplit('/', 1)[-1] + '-controls.json')).write_text(json.dumps(evaluate("({labels:[...document.querySelectorAll('label')].map(el=>({text:el.textContent,for:el.htmlFor,id:el.id})),combos:[...document.querySelectorAll('[role=combobox]')].map(el=>({id:el.id,disabled:el.getAttribute('aria-disabled'),label:el.getAttribute('aria-labelledby')}))})"),ensure_ascii=False,indent=2),encoding='utf-8')
            if path.endswith('/members'):
                screenshot('staff-members-error-desktop')
            before = counts()
            failures.clear()
            clicked = evaluate("(async()=>{const retry=[...document.querySelectorAll('[role=alert]')].find(el=>el.innerText.includes(" + json.dumps(path) + "));const button=retry?.querySelector('button');button?.click();await until(()=>!visibleText().includes(" + json.dumps(path) + "));return !!button;})()")
            after = counts()
            state["retryOnlyFailedSource"] = clicked and after[path] == before[path] + 1 and all(after[key] == before[key] for key in DATA if key != path)
            scenario(f"{path} failure leaves check-in and history usable; retry is isolated", state)

        failures.clear()
        failures.add("/api/v2/sites/1/availability")
        evaluate("mountCase('reservations')")
        before = counts()
        state = evaluate("({historyVisible:visibleText().includes('Lịch đặt chỗ của tôi')&&!!document.querySelector('[aria-label=\"Hủy giữ chỗ xe 1\"]')})")
        cancelled = evaluate("(async()=>{const cancel=document.querySelector('[aria-label=\"Hủy giữ chỗ xe 1\"]');cancel?.click();for(let n=0;n<15;n++)await pause();return !!cancel;})()")
        after = counts()
        state["cancelRefreshesBookingAndAvailability"] = cancelled and after["/api/v2/me/reservations"] == before["/api/v2/me/reservations"] + 1 and after["/api/v2/sites/1/availability"] == before["/api/v2/sites/1/availability"] + 1
        state["cancelDoesNotReloadProfile"] = cancelled and after["/api/v2/me/profile"] == before["/api/v2/me/profile"]
        scenario("availability failure keeps customer history and cancellation operational", state)
        screenshot("customer-availability-error-mobile", mobile=True)

        failures.clear()
        failures.add("/api/v2/organizations/1/fleet")
        evaluate("mountCase('fleet')")
        before = counts()
        state = evaluate("({retryPresent:!!button('Thử lại')})")
        failures.clear()
        recovered = evaluate("(async()=>{button('Thử lại')?.click();return await until(()=>visibleText().includes('Tổng lượt: 125'));})()")
        state["retryRecoversReport"] = recovered and counts()["/api/v2/organizations/1/fleet"] == before["/api/v2/organizations/1/fleet"] + 1
        scenario("fleet failure has a working section retry", state)

        failures.clear()
        evaluate("mountCase('sites')")
        evaluate("clickTab('Đặt chỗ')")
        before = counts()
        arrived = evaluate("(async()=>{const arrive=button('Xe đã đến');arrive?.click();for(let n=0;n<15;n++)await pause();return !!arrive;})()")
        after = counts()
        scenario("arrive refreshes reservations, availability and sessions only", {
            "clicked": arrived,
            "allDependentListsRefreshed": all(after[path] == before[path] + 1 for path in ("/api/v2/sites/1/reservations", "/api/v2/sites/1/availability", "/api/v2/sites/1/sessions")),
            "metadataNotReloaded": all(after[path] == before[path] for path in ("/api/v2/catalog/vehicle-types", "/api/v2/sites/1/members", "/api/v2/sites/1/organizations")),
        })
        screenshot("staff-reservation-desktop")

        # Exercise the actual customer page after the first 100 rows. The fake
        # HTTP server follows the already separately tested backend contract.
        paged_bookings = True
        DATA["/api/v2/sites"] = [DATA["/api/v2/sites"][0], {"id": 2, "name": "Bãi kiểm thử B", "role": "admin"}]
        DATA["/api/v2/sites/2/availability"] = {**DATA["/api/v2/sites/1/availability"], "site_id": 2}
        evaluate("mountCase('reservations')")
        beyond_100 = evaluate("""(async()=>{
          for(let page=2;page<=5;page++){
            button('Trang sau')?.click();
            await until(()=>visibleText().includes('Trang '+page)&&!visibleText().includes('Đang tải'));
          }
          return visibleText().includes('Trang 5')&&visibleText().includes('Xe #101');
        })()""")
        before = counts()
        filter_reset = evaluate("""(async()=>{
          await select('Trạng thái','Đã hủy');
          return await until(()=>visibleText().includes('Trang 1')&&visibleText().includes('Xe #2')&&!visibleText().includes('Đang tải'));
        })()""")
        after = counts()
        filter_isolated = all(before[path] == after[path] for path in ("/api/v2/me/profile", "/api/v2/me/vehicles", "/api/v2/sites/1/availability", "/api/v2/me/waitlist"))
        evaluate("(async()=>{button('Trang sau')?.click();await until(()=>visibleText().includes('Trang 2')&&!visibleText().includes('Đang tải'));})()")
        site_reset = evaluate("""(async()=>{
          await select('Bãi đỗ xe','Bãi kiểm thử B');
          return await until(()=>visibleText().includes('Đặt chỗ tại Bãi kiểm thử B')&&visibleText().includes('Trang 1')&&visibleText().includes('Xe #901')&&!visibleText().includes('Đang tải'));
        })()""")
        delay_site_a = True
        evaluate("select('Bãi đỗ xe','Bãi kiểm thử A')")
        evaluate("new Promise(resolve=>setTimeout(resolve,100))")
        latest_b = evaluate("""(async()=>{
          await select('Bãi đỗ xe','Bãi kiểm thử B');
          return await until(()=>visibleText().includes('Xe #901')&&!visibleText().includes('Đang tải'));
        })()""")
        delayed_count = len(delayed_requests)
        for request_id, payload in delayed_requests:
            call("Fetch.fulfillRequest", {"requestId": request_id, "responseCode": 200,
                 "responseHeaders": [{"name": "Content-Type", "value": "application/json"}],
                 "body": base64.b64encode(json.dumps(payload).encode()).decode()})
        delay_site_a = False
        stale_ignored = evaluate("(async()=>{for(let n=0;n<5;n++)await pause();return visibleText().includes('Đặt chỗ tại Bãi kiểm thử B')&&visibleText().includes('Xe #901')&&!visibleText().includes('Đang tải');})()")
        scenario("customer pagination beyond 100; filter/site reset; late previous-site result", {
            "pageFiveContainsRow101": beyond_100, "filterResetsToFirstPage": filter_reset,
            "filterRefreshesOnlyBookings": filter_isolated, "siteResetsPageAndFilter": site_reset,
            "previousSiteActuallyDelayed": delayed_count > 0, "latestSiteLoadedBeforeOldResult": latest_b,
            "oldSiteResultIgnored": stale_ignored,
        })
        screenshot("customer-site-switch-mobile", mobile=True)
        result = {"scenarios": scenarios, "requests": requests, "runtimeExceptions": console_errors,
                  "passed": all(row["passed"] for row in scenarios) and not console_errors}
        (RUN / "result.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps({"artifact": str(RUN / "result.json"), "passed": result["passed"], "scenarios": scenarios, "runtimeExceptions": console_errors}, ensure_ascii=False))
        if not result["passed"]:
            raise SystemExit(1)
finally:
    for process in reversed(children):
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
    output.close()
