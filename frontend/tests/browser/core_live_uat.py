"""Read-only verification of core navigation, availability and reports on the local app.
Only login audit writes are allowed; real core APIs, no AI generation or external requests.
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
parser.add_argument("--origin", default="http://127.0.0.1:8792")
parser.add_argument("--credentials", type=Path, required=True)
parser.add_argument("--preflight", type=Path)
args = parser.parse_args()
if args.origin != "http://127.0.0.1:8792":
    raise ValueError("This read-only harness only targets the local presentation origin")
credentials = json.loads(args.credentials.read_text(encoding="utf-8"))
if credentials.get("profile") != "single-lot-academic-v1":
    raise ValueError("Unexpected credentials profile")
SITE = 1  # Explicit single-lot read-only presentation target authorized by root.
RUN = ROOT / "backend/artifacts/core-live-browser" / uuid4().hex[:10]
RUN.mkdir(parents=True)
PROFILE = RUN / "chrome-profile"
NAME = "UI CV " + uuid4().hex[:8]
checks, requests, http_errors, runtime_errors, blocked_external, ids = [], [], [], [], [], {}
completed = False


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
                    allowed = ((parsed.netloc == "127.0.0.1:8792" and (paused["request"]["method"] in {"GET", "HEAD", "OPTIONS"} or (parsed.path == "/api/auth/login" and paused["request"]["method"] == "POST"))) or parsed.scheme in {"data", "blob", "about"})
                    if not allowed:
                        blocked_external.append({"host": parsed.hostname, "scheme": parsed.scheme})
                    sequence += 1
                    ws.send(json.dumps({"id": sequence, "method": "Fetch.continueRequest" if allowed else "Fetch.failRequest",
                        "params": {"requestId": paused["requestId"], **({} if allowed else {"errorReason": "BlockedByClient"})}}))
                if event == "Network.requestWillBeSent":
                    request = response["params"]["request"]
                    parsed = urllib.parse.urlsplit(request["url"])
                    if parsed.netloc == "127.0.0.1:8792":
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
        call('Emulation.setFocusEmulationEnabled', {'enabled': True})
        for role in ('manager', 'staff'):
            metrics(False)
            login(role)
            check(role+' core operations page reachable', "!!button('Xác nhận xe vào',main())&&!!field('Mã vé (mã lượt)')")
            check(role+' primary navigation exposes core catalogs', "['/sites','/zones','/parking-slots','/vehicle-types','/price-configs','/vehicles','/customers','/monthly-passes','/reports','/ai'].every(path=>document.querySelector('nav a[href=\"'+path+'\"]'))")
            check(role+' extensions collapsed on core page', "!document.querySelector('nav a[href=\"/vision\"]')&&!!document.querySelector('nav [aria-expanded=false]')")
            if role=='staff':
                check('staff has no account-management menu', "!document.querySelector('nav a[href=\"/users\"]')")
            evaluate("[...main().querySelectorAll('[role=tab]')].find(el=>el.textContent==='Chỗ trống').click()")
            check(role+' actual zone availability loaded', "main().textContent.includes('Chỗ trống theo khu vực')&&main().textContent.includes('Có thể nhận xe')&&main().querySelectorAll('tbody tr').length>2")
            screenshot(role+'-availability-desktop')
            metrics(True)
            check(role+' availability fits mobile', 'document.documentElement.scrollWidth<=innerWidth+1')
            screenshot(role+'-availability-mobile')
            metrics(False)
            evaluate("go('/reports')")
            check(role+' actual traffic report loaded', "main().textContent.includes('Báo cáo bãi xe')&&main().textContent.includes('Giờ đông nhất theo lượt vào:')&&!!button('Xuất CSV',main())")
            if role=='manager':
                check('manager report includes revenue', "main().textContent.includes('Thu gửi xe')")
            else:
                check('staff report excludes revenue', "!main().textContent.includes('Thu gửi xe')&&main().textContent.includes('Báo cáo doanh thu dành cho quản lý')")
            screenshot(role+'-report-desktop')
            metrics(True)
            check(role+' report fits mobile', 'document.documentElement.scrollWidth<=innerWidth+1')
            screenshot(role+'-report-mobile')
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
    report = {"passed": completed and all(row["path"] == "/api/auth/login" for row in writes) and not http_errors and not runtime_errors and not blocked_external,
        "scope": "Real FastAPI/React core on isolated academic DB local8792; only login audit writes; no AI/provider/external access",
        "checks": checks, "synthetic_ids": ids, "writes": writes, "http_errors": http_errors,
        "runtime_errors": runtime_errors, "blocked_external": blocked_external,
        "private_browser_profile_removed": not PROFILE.exists()}
    (RUN / "result.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"passed": report["passed"], "checks": len(checks), "artifact_directory": str(RUN)}, ensure_ascii=True))
    if completed and not report["passed"]:
        raise AssertionError("Acceptance captured errors; inspect sanitized result")
