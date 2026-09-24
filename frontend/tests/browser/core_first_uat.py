"""Render core React screens with isolated HTTP fixtures; no real backend or account.

Run from the repository: .venv/Scripts/python.exe frontend/tests/browser/core_first_uat.py
Requires the existing Windows Chrome and Python websockets dependency.
"""
import base64
import json
from pathlib import Path
import subprocess
import shutil
import time
import urllib.parse
import urllib.request
from uuid import uuid4

from websockets.sync.client import connect

ROOT = Path(__file__).resolve().parents[3]
RUN = ROOT / "backend/artifacts/core-first-ui" / uuid4().hex[:10]
RUN.mkdir(parents=True)
ORIGIN = "http://127.0.0.1:18984"
children, checks, errors, requests = [], [], [], []
completed = False
role, legacy = "manager", True
kind = {"id": 1, "name": "Ô tô", "description": "Xe thử nghiệm", "is_active": True}
inactive_kind = {"id": 2, "name": "Loại xe đã ngừng", "is_active": False}
customer = {"id": 1, "full_name": "Khách thử nghiệm", "phone_number": "0900000000", "email": "demo@example.invalid"}
vehicle = {"id": 1, "license_plate": "DEMO01", "vehicle_type": kind, "vehicle_type_id": 1, "customer": customer}
DATA = {
    "/api/v1/zones": [{"id": 1, "name": "Khu A", "is_active": True, "capacity": 10}],
    "/api/v1/parking-slots": [{"id": 1, "slot_name": "A-01", "zone_id": 1, "vehicle_type_id": 1, "is_active": True, "is_occupied": False},
        {"id": 2, "slot_name": "A-02", "zone_id": 1, "vehicle_type_id": 2, "is_active": True, "is_occupied": False}],
    "/api/v1/roles": [{"id": 1, "name": "staff"}, {"id": 2, "name": "manager"}, {"id": 3, "name": "admin"}],
    "/api/v1/users": [{"id": 1, "username": "manager", "role": {"id": 2, "name": "manager"}, "is_active": True}, {"id": 2, "username": "staff", "role": {"id": 1, "name": "staff"}, "is_active": True}],
    "/api/v1/vehicle-types": [kind, inactive_kind],
    "/api/v2/catalog/vehicle-types": [kind, inactive_kind],
    "/api/v2/sites/1/availability": {"total": 1, "slots": [{"id": 1, "slot_name": "A-01", "zone_name": "Khu A", "zone_id": 1, "vehicle_type_id": 1, "available_now": True}]},
    "/api/v1/customers": [customer],
    "/api/v1/vehicles": [vehicle],
    "/api/v1/price-configs": [{"id": 1, "vehicle_type_id": 1, "ticket_type": "HOURLY", "price": 10000, "effective_date": "2026-09-15", "is_active": True}],
    "/api/v1/monthly-passes": [{"id": 1, "card_code": "TEST-PASS", "price": 100000, "vehicle": vehicle, "customer": customer, "start_date": "2026-09-01", "end_date": "2099-09-30", "is_active": True}],
    "/api/v2/sites/1/ai/status": {"enabled": False},
    "/api/v2/sites/1/ai/analyses": [],
}


def payload(path):
    if path == "/api/v2/system/capabilities":
        return {"legacy_workspace_allowed": legacy, "site_analytics_enabled": True, "site_finance_enabled": True, "showcase_mode": True}
    if path == "/api/v2/sites":
        return [{"id": 1, "name": "Bãi kiểm thử", "role": role, "is_active": True}]
    if path == "/api/v2/sites/1/reports/summary":
        return {"period": "day", "start_date": "2026-09-15", "end_date": "2026-09-15", "demo_mode": True,
                "data_scope": "operations" if role == "staff" else "management",
                "total_arrivals": 0, "total_departures": 3, "total_movements": 3,
                "peak_hours": [], "peak_movement_hours": ["08:00"],
                "daily_traffic": [{"date": "2026-09-15", "arrivals": 0, "departures": 3}],
                "hourly_traffic": [{"hour": "08:00", "arrivals": 0, "departures": 3}],
                "revenue": None if role == "staff" else {"parking_revenue": 25000, "monthly_pass_revenue": 100000, "refunds": 0, "total_revenue": 125000, "demo_receipts": 0, "demo_refunds": 0},
                "current_availability": {"as_of": "2026-09-15T08:00:00+07:00", "zones": []}}
    return DATA.get(path, [])


try:
    with (RUN / "process.log").open("w", encoding="utf-8") as output:
        flags = subprocess.CREATE_NO_WINDOW
        children.append(subprocess.Popen(["node", "node_modules/vite/bin/vite.js", "--host", "127.0.0.1", "--port", "18984", "--strictPort"], cwd=ROOT / "frontend", stdout=output, stderr=output, creationflags=flags))
        children.append(subprocess.Popen([r"C:\Program Files\Google\Chrome\Application\chrome.exe", "--headless=new", "--disable-gpu", "--no-first-run", "--no-default-browser-check", "--disable-background-networking", "--disable-component-update", "--disable-sync", "--remote-debugging-port=18986", "--remote-debugging-address=127.0.0.1", "--user-data-dir=" + str(RUN / "chrome-profile"), "about:blank"], stdout=output, stderr=output, creationflags=flags))
        for attempt in range(100):
            try:
                urllib.request.urlopen(ORIGIN, timeout=1).close()
                pages = json.load(urllib.request.urlopen("http://127.0.0.1:18986/json", timeout=1))
                target = next(page for page in pages if page["type"] == "page")
                break
            except (OSError, StopIteration):
                if any(process.poll() is not None for process in children):
                    raise RuntimeError("Private frontend/browser exited; inspect process.log")
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
                        requests.append({"path": path, "method": request["method"], "query": urllib.parse.parse_qs(urllib.parse.urlsplit(request["url"]).query)})
                        dispatch("Fetch.fulfillRequest", {"requestId": paused["requestId"], "responseCode": 200,
                                 "responseHeaders": [{"name": "Content-Type", "value": "application/json; charset=utf-8"}],
                                 "body": base64.b64encode(json.dumps(payload(path), ensure_ascii=False).encode()).decode()})
                    if response.get("method") == "Runtime.exceptionThrown":
                        errors.append(response["params"])
                    if response.get("id") == wanted:
                        if "error" in response:
                            raise RuntimeError(response["error"])
                        return response.get("result", {})

            def evaluate(expression):
                result = call("Runtime.evaluate", {"expression": expression, "awaitPromise": True, "returnByValue": True})
                if "exceptionDetails" in result:
                    raise RuntimeError(result["exceptionDetails"])
                return result.get("result", {}).get("value")

            def check(name, expression):
                try:
                    passed = evaluate(expression)
                except RuntimeError:
                    (RUN / "failed-state.json").write_text(json.dumps(evaluate("({main:mainText(),labels:[...document.querySelectorAll('main label,[id$=\"-label\"]')].map(el=>({text:el.textContent,id:el.id,for:el.htmlFor})),combos:[...document.querySelectorAll('main [role=combobox]')].map(el=>({id:el.id,label:el.getAttribute('aria-labelledby')}))})"), ensure_ascii=False, indent=2), encoding="utf-8")
                    raise
                checks.append({"name": name, "passed": passed is True})
                if passed is not True:
                    (RUN / "failed-state.json").write_text(json.dumps(evaluate("({main:mainText(),menu:menuText(),body:document.body.innerText})"), ensure_ascii=False, indent=2), encoding="utf-8")
                    raise AssertionError(name)

            def screenshot(name, mobile=False):
                call("Emulation.setDeviceMetricsOverride", {"width": 390 if mobile else 1440, "height": 844 if mobile else 1000, "deviceScaleFactor": 1, "mobile": mobile})
                evaluate("new Promise(resolve => setTimeout(resolve, 150))")
                image = call("Page.captureScreenshot", {"format": "png", "captureBeyondViewport": False})
                (RUN / f"{name}.png").write_bytes(base64.b64decode(image["data"]))

            call("Runtime.enable", {})
            call("Emulation.setFocusEmulationEnabled", {"enabled": True})
            call("Fetch.enable", {"patterns": [{"urlPattern": "*/api/*"}]})
            call("Page.addScriptToEvaluateOnNewDocument", {"source": "window.__PARKINGAI_CONFIG__={API_URL:'" + ORIGIN + "',SINGLE_SITE_ID:1,DEMO:true};"})
            call("Page.navigate", {"url": ORIGIN})
            for attempt in range(100):
                if evaluate("document.readyState === 'complete' && !!window.$RefreshReg$"):
                    break
                time.sleep(.2)
            evaluate(r"""(async () => {
              window.__PARKINGAI_CONFIG__={API_URL:location.origin,SINGLE_SITE_ID:1,DEMO:true};
              const source = await (await fetch('/src/layouts/MainLayout.jsx')).text();
              const main = await (await fetch('/src/main.jsx')).text();
              const dependency = (text, name) => text.match(new RegExp('["\\\']([^"\\\']*/deps/' + name + '\\.js[^"\\\']*)["\\\']'))[1];
              const react = await import(dependency(source,'react')); const React = react.default || react;
              const dom = await import(dependency(main,'react-dom_client')); const {createRoot} = dom.default || dom;
              const routing = await import(dependency(source,'react-router-dom')); const {MemoryRouter, Routes, Route} = routing.default || routing;
              const mui = await import(dependency(source,'@mui_material')); const {ThemeProvider} = mui.default || mui;
              const {default: theme} = await import('/src/theme/index.js');
              const {default: api} = await import('/src/services/api.js'); api.defaults.baseURL = location.origin;
              const {AuthContext} = await import('/src/context/AuthContext.jsx');
              const {ExpansionProvider} = await import('/src/context/ExpansionContext.jsx');
              const {default: Layout} = await import('/src/layouts/MainLayout.jsx');
              const {default: PermissionRoute} = await import('/src/routes/PermissionRoute.jsx');
              const pages = Object.fromEntries(await Promise.all([
                ['/vehicle-types','VehicleType/VehicleTypePage'], ['/parking-slots','ParkingSlot/ParkingSlotPage'], ['/price-configs','PriceConfig/PriceConfigPage'],
                ['/monthly-passes','MonthlyPass/MonthlyPassPage'], ['/customers','Customer/CustomerPage'],
                ['/vehicles','Vehicle/VehiclePage'], ['/reports','Expansion/CoreAnalyticsPage'], ['/users','User/UserPage'], ['/admission-scoped','Expansion/SitesWorkspace'],
              ].map(async ([path,file]) => [path,(await import('/src/pages/'+file+'.jsx')).default])));
              const {default:CheckInCard}=await import('/src/pages/ParkingSession/components/CheckInCard.jsx');
              pages['/admission-legacy']=function AdmissionProbe(){
                const [types,setTypes]=React.useState([{id:1,name:'Ô tô',is_active:true},{id:2,name:'Loại xe đã ngừng',is_active:false}]);
                const [typeId,setTypeId]=React.useState(1); window.refreshAdmissionTypes=setTypes;
                return React.createElement(CheckInCard,{licensePlate:'DEMO01',onChangePlate:()=>{},vehicleTypeId:typeId,onChangeVehicleType:setTypeId,vehicleTypes:types,zoneId:'',onChangeZone:()=>{},slotId:'',onChangeSlot:()=>{},onSubmit:event=>event.preventDefault()});
              };
              const {Availability}=await import('/src/pages/Expansion/siteComponents.jsx');
              pages['/availability-preview']=()=>React.createElement(Availability,{vehicleTypes:[{id:1,name:'Ô tô'}],data:{capacity_total:3,total:3,occupied:1,available_now:1,reserved_slots:1,slots:[
                {id:1,slot_name:'A-01',zone_id:1,zone_name:'Khu A',vehicle_type_id:1,is_occupied:true,available_now:false,reserved:false},
                {id:2,slot_name:'A-02',zone_id:1,zone_name:'Khu A',vehicle_type_id:1,is_occupied:false,available_now:false,reserved:true},
                {id:3,slot_name:'B-01',zone_id:2,zone_name:'Khu B',vehicle_type_id:1,is_occupied:false,available_now:true,reserved:false},
              ]}});
              document.getElementById('root').style.display='none'; let root, host;
              window.pause=()=>new Promise(resolve=>setTimeout(resolve,50));
              window.until=async predicate=>{for(let n=0;n<100;n++){if(predicate())return true;await pause();}return false;};
              window.buttons=()=>[...host.querySelectorAll('main button')].map(el=>el.textContent.trim());
              window.mainText=()=>host?.querySelector('main')?.innerText||'';
              window.menuText=()=>[...host.querySelectorAll('.MuiDrawer-root')].map(el=>el.innerText).join(' ');
              window.field=label=>{const el=[...host.querySelectorAll('main label,main [id$="-label"]')].find(el=>el.textContent.replace('*','').trim()===label);return el&&(document.getElementById(el.htmlFor)||[...host.querySelectorAll('main [role=combobox]')].find(input=>input.getAttribute('aria-labelledby')?.split(' ').includes(el.id)));};
              window.choose=async(label,text)=>{field(label).dispatchEvent(new MouseEvent('mousedown',{bubbles:true}));await pause();const options=[...document.querySelectorAll('[role=option]')];if(!text)return options.map(el=>el.textContent);options.find(el=>el.textContent.includes(text)).click();await pause();};
              window.downloads=[]; const originalClick=HTMLAnchorElement.prototype.click;
              HTMLAnchorElement.prototype.click=function(){if(this.download){downloads.push(this.download);return;}return originalClick.call(this);};
              window.mount=async (path,role)=>{
                if(root){root.unmount();host.remove();}host=document.createElement('div');document.body.appendChild(host);root=createRoot(host);
                const e=React.createElement;
                const routes=e(Routes,null,e(Route,{element:e(Layout)},
                  e(Route,{path,element:e(PermissionRoute,{legacy:path!='/reports'},e(pages[path]))}),
                  e(Route,{path:'/sites',element:e('p',null,'SCOPED WORKSPACE')})));
                root.render(e(ThemeProvider,{theme},e(AuthContext.Provider,{value:{user:{id:1,username:role,role},logout:()=>{}}},e(MemoryRouter,{initialEntries:[path]},e(ExpansionProvider,null,routes)))));
                await until(()=>mainText().length>20);for(let n=0;n<8;n++)await pause();
              };
            })()""")

            role="manager"
            evaluate("mount('/vehicle-types','manager')")
            check("core operation link leads navigation", "document.querySelector('nav a')?.getAttribute('href')==='/sites'")
            check("extensions are collapsed until requested", "!document.querySelector('nav a[href=\"/vision\"]')&&!!document.querySelector('nav [aria-expanded=false]')")
            check("extension routes remain reachable", "(async()=>{document.querySelector('nav [aria-expanded=false]').click();return await until(()=>!!document.querySelector('nav a[href=\"/vision\"]')&&!!document.querySelector('nav a[href=\"/occupancy\"]'));})()")
            check("extension disclosure closes", "(async()=>{document.querySelector('nav [aria-expanded=true]').click();return await until(()=>!document.querySelector('nav a[href=\"/vision\"]'));})()")
            check("current route is announced as page", "document.querySelector('nav a[href=\"/vehicle-types\"]')?.getAttribute('aria-current')==='page'")
            focus = evaluate("(async()=>{const links=[...document.querySelectorAll('a[href=\"#main-content\"]')];const link=links.at(-1);link.focus();await pause();return {count:links.length,top:link.getBoundingClientRect().top,styleTop:getComputedStyle(link).top,focus:link.matches(':focus'),active:document.activeElement===link,hasFocus:document.hasFocus(),hidden:document.hidden};})()")
            checks.append({"name":"skip link becomes visible on keyboard focus","passed":focus['top']>=0,"probe":focus})
            evaluate("document.activeElement.blur()")
            screenshot("manager-core-navigation-desktop")
            evaluate("mount('/parking-slots','manager')")
            check("inactive vehicle type slot is not in free inventory count", "mainText().includes('Trống vật lý: 1')&&mainText().includes('Bảo trì / ngừng dùng: 1')")
            check("manager can discover manual slot editing from map", "buttons().includes('Thêm / sửa vị trí đỗ')")
            screenshot("manager-slots-desktop")
            evaluate("mount('/availability-preview','manager')")
            check("availability groups by zone and preserves held states", "mainText().includes('Chỗ trống theo khu vực')&&mainText().includes('Khu A')&&mainText().includes('Khu B')&&mainText().includes('Đã dành chỗ')&&mainText().includes('Ô tô')&&!mainText().includes('Mã loại xe')")
            screenshot("manager-availability-desktop")
            screenshot("manager-availability-mobile",mobile=True)
            check("availability mobile bounds", "document.documentElement.scrollWidth<=window.innerWidth")
            call("Emulation.setDeviceMetricsOverride",{"width":1440,"height":1000,"deviceScaleFactor":1,"mobile":False})
            for role in ("manager", "staff"):
                for path in ("/vehicle-types", "/price-configs"):
                    evaluate(f"mount({json.dumps(path)},{json.dumps(role)})")
                    expected = "true" if role == "manager" else "false"
                    check(f"{role} {path} create/edit/delete controls", f"buttons().includes('Thêm mới')==={expected}&&buttons().includes('Sửa')==={expected}&&buttons().includes('Xóa')==={expected}")
                    check(f"{role} complete single-site catalogs", "['Khách hàng','Vé tháng','Phương tiện','Khu vực','Vị trí đỗ','Loại xe','Bảng giá'].every(text=>menuText().includes(text))")
                evaluate(f"mount('/monthly-passes',{json.dumps(role)})")
                expected = "true" if role == "manager" else "false"
                check(f"{role} monthly issuance and cancellation", f"buttons().includes('Đăng ký vé tháng')==={expected}&&!!document.querySelector('[aria-label=\"Ngừng hoạt động kỳ vé\"]')==={expected}")
                if role == "staff":
                    screenshot("staff-monthly-desktop")
                    screenshot("staff-monthly-mobile", mobile=True)
                    check("mobile shell does not overflow viewport", "document.documentElement.scrollWidth<=window.innerWidth")
                    check("mobile navigation opens core catalogs", "(async()=>{document.querySelector('[aria-label=\"Mở menu điều hướng\"]').click();await pause();return menuText().includes('Vé tháng');})()")
                for path in ("/customers", "/vehicles"):
                    evaluate(f"mount({json.dumps(path)},{json.dumps(role)})")
                    check(f"{role} {path} delete controls", f"(buttons().includes('Xóa')||!!document.querySelector('[aria-label=\"Xóa xe DEMO01\"]'))==={expected}")
                evaluate(f"mount('/reports',{json.dumps(role)})")
                check(f"{role} departure-only traffic visible", "mainText().includes('08:00')&&mainText().includes('Lượt ra trong kỳ')")
                check(f"{role} revenue visibility", f"mainText().includes('Thu gửi xe')==={expected}")
                check(f"{role} report export downloads CSV", "(async()=>{const before=downloads.length;[...document.querySelectorAll('main button')].find(el=>el.textContent==='Xuất CSV').click();return await until(()=>downloads.length===before+1&&downloads.at(-1)==='parking-report-1-day-2026-09-15.csv');})()")

            role = "manager"
            evaluate("mount('/vehicle-types','manager')")
            check("disabled vehicle type remains in management catalog", "mainText().includes('Loại xe đã ngừng')&&mainText().includes('Ngừng dùng')")
            evaluate("mount('/admission-legacy','manager')")
            check("legacy admission offers active types only", "(async()=>{const names=await choose('Loại xe');document.querySelector('[role=option]').click();return names.includes('Ô tô')&&!names.includes('Loại xe đã ngừng');})()")
            check("legacy admission blocks a type disabled by refreshed metadata", "(async()=>{refreshAdmissionTypes([{id:1,name:'Ô tô',is_active:false}]);await pause();return [...document.querySelectorAll('main button')].find(el=>el.textContent==='Check In').disabled&&mainText().includes('Hãy chọn lại');})()")
            evaluate("mount('/admission-scoped','manager')")
            check("scoped admission offers active types only", "(async()=>{const names=await choose('Loại xe');document.querySelector('[role=option]').click();await pause();return names.includes('Ô tô')&&!names.includes('Loại xe đã ngừng');})()")
            check("scoped admission can choose an active slot", "(async()=>{await choose('Vị trí nhận xe','A-01');const el=field('Biển số xe');Object.getOwnPropertyDescriptor(HTMLInputElement.prototype,'value').set.call(el,'DEMO01');el.dispatchEvent(new Event('input',{bubbles:true}));await pause();return ![...document.querySelectorAll('main button')].find(el=>el.textContent==='Xác nhận xe vào').disabled;})()")
            DATA['/api/v2/catalog/vehicle-types'] = [{**kind, 'is_active': False}, inactive_kind]
            check("scoped refresh clears stale type and prevents admission", "(async()=>{[...document.querySelectorAll('main button')].find(el=>el.textContent==='Làm mới').click();return await until(()=>mainText().includes('Hãy chọn lại')&&[...document.querySelectorAll('main button')].find(el=>el.textContent==='Xác nhận xe vào').disabled);})()")
            evaluate("mount('/users','manager')")
            check("manager can edit staff but not self", "!!document.querySelector('[aria-label=\"Sửa tài khoản staff\"]')&&!document.querySelector('[aria-label=\"Sửa tài khoản manager\"]')&&!document.querySelector('[aria-label^=\"Xóa tài khoản\"]')")
            check("manager can create only staff role", "(async()=>{[...document.querySelectorAll('main button')].find(el=>el.textContent==='Thêm người dùng').click();await pause();const role=document.querySelector('[role=dialog] [role=combobox]');return role?.textContent==='staff'&&role?.getAttribute('aria-disabled')==='true';})()")

            role, legacy = "manager", False
            evaluate("mount('/monthly-passes','manager')")
            check("capability denial keeps core routes scoped", "mainText().includes('SCOPED WORKSPACE')&&!menuText().includes('Vé tháng')")
            check("unknown role has no management controls", "(async()=>{await mount('/vehicle-types','unknown');return mainText().includes('Bạn không có quyền')&&!buttons().includes('Thêm mới');})()")
            check("read-only review issued no writes", "true")
            checks[-1]["passed"] = all(row["method"] == "GET" for row in requests)
            exports = [row for row in requests if row["path"].endswith("/reports/export")]
            checks.append({"name": "CSV request uses displayed report period and anchor", "passed": len(exports) == 2 and all(row["query"] == {"period": ["day"], "anchor_date": ["2026-09-15"]} for row in exports)})
            if errors:
                raise AssertionError("Browser reported runtime exceptions")
            if not all(row["passed"] for row in checks):
                raise AssertionError("Request contract checks failed")
            completed = True
finally:
    for process in reversed(children):
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
    profile = (RUN / 'chrome-profile').resolve()
    if profile.parent == RUN.resolve():
        for attempt in range(20):
            try:
                shutil.rmtree(profile)
                break
            except FileNotFoundError:
                break
            except PermissionError:
                time.sleep(.1)
    report = {"checks": checks, "requests": requests, "runtime_exceptions": errors, "passed": completed and bool(checks) and all(row["passed"] for row in checks) and not errors, "scope": "Actual React screens, mocked API, isolated headless Chrome", "artifact_directory": str(RUN)}
    (RUN / "result.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"passed": report["passed"], "checks": len(checks), "artifact_directory": str(RUN)}, ensure_ascii=True))
