"""Read-only admin/catalog fidelity capture against the unchanged local prototype.

Uses only the marked synthetic account; allows local GET/HEAD and login POST.
Never records credentials, authentication headers, bodies, or private ticket data.
"""
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
parser.add_argument("--pages", nargs="+", choices=["users", "audit", "configuration", "reports", "monthly", "types", "prices"], help="Bound confirmation to pages changed after the full capture")
args = parser.parse_args()
credentials = json.loads(args.credentials.read_text(encoding="utf-8"))
marker = json.loads(Path(credentials["database"] + ".demo.json").read_text(encoding="utf-8"))
if credentials.get("profile") != "single-lot-academic-v1" or marker.get("synthetic_history") is not True:
    raise ValueError("Prepared synthetic database is required")
BASE = ROOT / "backend/artifacts/prototype-admin-comparison"
OUT = BASE / uuid4().hex[:10]
OUT.mkdir(parents=True)
PROFILE = OUT / "chrome-profile"
REAL = "http://127.0.0.1:8793"
REFERENCE = "http://127.0.0.1:8790"
checks, screenshots, errors, blocked, failures = [], [], [], [], []
complete = False
print(json.dumps({"artifacts": str(OUT)}, ensure_ascii=True), flush=True)
with socket.socket() as channel:
    channel.bind(("127.0.0.1", 0))
    port = channel.getsockname()[1]
log = (OUT / "browser.log").open("w", encoding="utf-8")
process = subprocess.Popen([
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    "--headless=new", "--disable-gpu", "--no-first-run", "--no-default-browser-check",
    "--disable-background-networking", "--disable-component-update", "--disable-sync",
    "--remote-debugging-address=127.0.0.1", f"--remote-debugging-port={port}",
    "--user-data-dir=" + str(PROFILE), "about:blank",
], stdout=log, stderr=log, creationflags=subprocess.CREATE_NO_WINDOW)
try:
    for _ in range(100):
        try:
            page = next(row for row in json.load(urllib.request.urlopen(f"http://127.0.0.1:{port}/json", timeout=1)) if row["type"] == "page")
            break
        except (OSError, StopIteration):
            time.sleep(.1)
    else:
        raise RuntimeError("Chrome did not become ready")
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
                    local = parsed.netloc in {"127.0.0.1:8790", "127.0.0.1:8793"}
                    login = parsed.netloc == "127.0.0.1:8793" and parsed.path == "/api/auth/login" and req["method"] == "POST"
                    forbidden = any(word in parsed.path for word in ("payment-link", "webhook", "reconcile", "simulate"))
                    allowed = not forbidden and ((local and req["method"] in {"GET", "HEAD"}) or login or parsed.scheme in {"data", "blob", "about"})
                    if not allowed:
                        blocked.append({"method": req["method"], "local": local, "path": parsed.path if local else "external"})
                    seq += 1
                    ws.send(json.dumps({"id": seq, "method": "Fetch.continueRequest" if allowed else "Fetch.failRequest", "params": {"requestId": paused["requestId"], **({} if allowed else {"errorReason": "BlockedByClient"})}}))
                if result.get("method") == "Runtime.exceptionThrown":
                    errors.append({"kind": "browser_runtime", "text": result["params"]["exceptionDetails"]["text"]})
                if result.get("method") == "Network.responseReceived":
                    response = result["params"]["response"]
                    parsed = urllib.parse.urlsplit(response["url"])
                    if response["status"] >= 400 and parsed.path.startswith("/api/"):
                        failures.append({"path": parsed.path, "status": response["status"]})
                if result.get("id") == wanted:
                    if "error" in result:
                        raise RuntimeError(method)
                    return result.get("result", {})

        def js(source):
            result = call("Runtime.evaluate", {"expression": source, "returnByValue": True, "awaitPromise": True})
            if "exceptionDetails" in result:
                raise RuntimeError("Browser expression failed; private values withheld")
            return result.get("result", {}).get("value")

        def check(label, source, required=True):
            for _ in range(150):
                if js(source):
                    checks.append({"check": label, "passed": True})
                    return True
                time.sleep(.1)
            checks.append({"check": label, "passed": False})
            if required:
                raise AssertionError(label)
            return False

        def click(selector):
            js("document.querySelector(" + json.dumps(selector) + ").click()")

        def set_value(selector, value):
            js("(()=>{const e=document.querySelector(" + json.dumps(selector) + ");const p=e.tagName==='SELECT'?HTMLSelectElement.prototype:HTMLInputElement.prototype;Object.getOwnPropertyDescriptor(p,'value').set.call(e," + json.dumps(value) + ");e.dispatchEvent(new Event(e.tagName==='SELECT'?'change':'input',{bubbles:true}));})()")

        def settle(label, selector):
            check(label + " content ready", "document.readyState==='complete'&&!!document.querySelector(" + json.dumps(selector) + ")&&!document.querySelector('main')?.innerText.includes('Đang tải')")
            js("new Promise(resolve=>setTimeout(resolve,350))")

        def shot(name, mobile):
            width, height = (390, 844) if mobile else (1440, 1000)
            call("Emulation.setDeviceMetricsOverride", {"width": width, "height": height, "deviceScaleFactor": 1, "mobile": mobile})
            call("Emulation.resetPageScaleFactor")
            js("window.scrollTo(0,0);new Promise(resolve=>setTimeout(resolve,300))")
            if js("location.pathname==='/login'||[...document.querySelectorAll('input[type=password]')].some(e=>e.value)||!!document.querySelector('.parking-ticket-dialog')||document.body.innerText.includes('PAP1.')"):
                raise RuntimeError("Private screenshot prevented")
            metrics = js("""(()=>{const box=e=>{const r=e.getBoundingClientRect(),s=getComputedStyle(e);return {tag:e.tagName,cls:String(e.className),x:r.x,y:r.y,width:r.width,height:r.height,right:r.right,font:s.fontFamily,fontSize:s.fontSize,padding:s.padding,overflowX:s.overflowX,scrollWidth:e.scrollWidth,clientWidth:e.clientWidth}};return {innerWidth,scrollWidth:document.documentElement.scrollWidth,scale:visualViewport.scale,heading:document.querySelector('main h1')?.textContent,shell:[...document.querySelectorAll('.topbar,.demo-banner,.sidebar,main,.page-head')].map(box),surfaces:[...document.querySelectorAll('main .surface')].map(box),tables:[...document.querySelectorAll('main .table-wrap')].map(box),inputs:[...document.querySelectorAll('main input,main select,main textarea')].map(e=>({type:e.type,label:e.labels?.[0]?.textContent,box:box(e)})),overflow:[...document.querySelectorAll('main *')].filter(e=>{const r=e.getBoundingClientRect();return !e.closest('.table-wrap')&&r.width>0&&r.right>document.documentElement.clientWidth+1}).slice(0,20).map(box)}})()""")
            checks.append({"check": name + " viewport", "passed": metrics["scrollWidth"] <= width + 1 and abs(metrics["scale"] - 1) < .02})
            checks.append({"check": name + " no main overflow outside table scrollers", "passed": not metrics["overflow"]})
            screenshots.append({"file": name + ".png", "metrics": metrics})
            (OUT / (name + ".png")).write_bytes(base64.b64decode(call("Page.captureScreenshot", {"format": "png", "captureBeyondViewport": False})["data"]))

        def pair(name):
            shot(name + "-desktop", False)
            shot(name + "-mobile", True)

        for method in ("Runtime.enable", "Network.enable"):
            call(method)
        call("Fetch.enable", {"patterns": [{"urlPattern": "*"}]})
        call("Page.navigate", {"url": REAL + "/login"})
        check("admin login form", "!!document.querySelector('#username')&&!!document.querySelector('#password')")
        set_value("#username", "admin_demo")
        set_value("#password", credentials["accounts"]["admin_demo"])
        click("button[type=submit]")
        check("admin authenticated", "location.pathname!=='/login'&&!!document.querySelector('main h1')")
        paths = [
            ("users", "/users", "#accounts-title", "Tài khoản & phân quyền"),
            ("audit", "/audit-logs", "#audit-title", "Nhật ký hoạt động"),
            ("configuration", "/site-settings", "main textarea", "Cấu hình bãi"),
            ("reports", "/reports", "main .chart-bars", "Báo cáo & AI"),
            ("monthly", "/monthly-passes", "main .data-table tbody tr", "Khách & vé"),
            ("types", "/vehicle-types", "main .data-table tbody tr", "Loại xe & bảng giá"),
            ("prices", "/price-configs", "main .data-table tbody tr", "Loại xe & bảng giá"),
        ]
        for label, path, ready, heading in paths:
            if args.pages and label not in args.pages:
                continue
            call("Page.navigate", {"url": REAL + path})
            settle(label, ready)
            check(label + " expected heading", "document.querySelector('main h1')?.textContent===" + json.dumps(heading))
            pair("real-" + label)
            if label in {"users", "monthly", "types", "prices"}:
                click("main .page-head .button.primary")
                check(label + " inline editor opens", "!!document.querySelector('main .core-editor form')")
                check(label + " inline editor is labelled", "[...document.querySelectorAll('main .core-editor input,main .core-editor select,main .core-editor [role=combobox]')].every(e=>e.type==='hidden'||e.getAttribute('aria-hidden')==='true'||e.labels?.length>0||e.getAttribute('aria-label')||e.getAttribute('aria-labelledby')?.split(' ').some(id=>document.getElementById(id)?.textContent.trim()))")
                js("[...document.querySelectorAll('main .core-editor button')].find(e=>e.textContent.trim()==='Hủy').click()")
                check(label + " editor cancel closes", "!document.querySelector('main .core-editor')")
            if label == "audit" and js("!!document.querySelector('main tbody details')"):
                click("main tbody details summary")
                check("audit details opens read-only", "!!document.querySelector('main tbody details[open] dl')")
                click("main tbody details summary")
        call("Page.navigate", {"url": REFERENCE + "/?v=full-demo#admin"})
        check("reference admin ready", "!!window.ParkingDemo&&!!document.querySelector('[data-tab=accounts]')")
        for label, tab in [("users", "accounts"), ("audit", "audit"), ("configuration", "configuration"), ("reports", "finance"), ("monthly", "customers"), ("types", "catalog"), ("prices", "catalog")]:
            if args.pages and label not in args.pages:
                continue
            click('[data-action="nav"][data-tab="' + tab + '"]')
            if label == "monthly":
                click('[data-action="core-tab"][data-value="passes"]')
            if label == "reports":
                click('[data-action="report-tab"][data-tab="flow"]')
            settle("reference " + label, "main h1")
            pair("reference-" + label)
        complete = all(row["passed"] for row in checks) and not errors and not failures and not blocked
except Exception as error:
    errors.append({"kind": "harness", "text": str(error)})
finally:
    process.terminate()
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=5)
    log.close()
    if PROFILE.resolve().parent == OUT.resolve() and OUT.resolve().is_relative_to(BASE.resolve()):
        for _ in range(30):
            try:
                shutil.rmtree(PROFILE)
                break
            except FileNotFoundError:
                break
            except PermissionError:
                time.sleep(.1)
    result = {"complete": complete, "checks": checks, "screenshots": screenshots, "runtime_errors": errors, "api_failures": failures, "blocked_requests": blocked, "private_profile_removed": not PROFILE.exists()}
    (OUT / "result.json").write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps({"artifacts": str(OUT), "screenshots": len(screenshots), "passed": sum(row["passed"] for row in checks), "checks": len(checks), "complete": complete}, ensure_ascii=True), flush=True)
raise SystemExit(0 if complete else 1)
