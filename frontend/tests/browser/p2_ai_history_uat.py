"""Read real saved Gemini results in the P1 frontend using both roles.
No provider call or business mutation; two login audits are permitted.
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
RUN = ROOT / "backend/artifacts/p2-ai-browser" / uuid4().hex[:10]
RUN.mkdir(parents=True)
ORIGIN = "http://127.0.0.1:8766"
DATABASE = "single-lot-live.db"
credentials = json.loads((ROOT / "backend/artifacts/demo" / (DATABASE + ".demo-credentials.json")).read_text(encoding="utf-8"))["accounts"]
evidence = json.loads((ROOT / "backend/artifacts/demo/p2-live-ai-acceptance.json").read_text(encoding="utf-8"))
checks, requests, http_errors, runtime_errors = [], [], [], []
completed = False
business = {}
profile = RUN / "chrome-profile"
log = (RUN / "process.log").open("w", encoding="utf-8")
chrome = subprocess.Popen([r"C:\Program Files\Google\Chrome\Application\chrome.exe", "--headless=new", "--disable-gpu", "--no-first-run", "--no-default-browser-check", "--disable-background-networking", "--disable-component-update", "--disable-sync", "--remote-debugging-port=18989", "--remote-debugging-address=127.0.0.1", "--window-size=1440,1050", "--user-data-dir=" + str(profile), "about:blank"], stdout=log, stderr=log, creationflags=subprocess.CREATE_NO_WINDOW)
try:
    for _ in range(50):
        try:
            targets = json.load(urllib.request.urlopen("http://127.0.0.1:18989/json", timeout=1))
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
                    if parsed.netloc == "127.0.0.1:8766":
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
        for role in ("manager", "staff"):
            metrics(role == "staff")
            call("Storage.clearDataForOrigin", {"origin": ORIGIN, "storageTypes": "all"})
            call("Page.navigate", {"url": ORIGIN + "/login"})
            check(role + " login form", "!!document.querySelector('#username')&&!!document.querySelector('#password')")
            fill("#username", role + "_demo")
            fill("#password", credentials[role + "_demo"])
            evaluate("document.querySelector('button[type=submit]').click()")
            check(role + " signed in", "location.pathname==='/sites'&&!!document.querySelector('main')")
            call("Page.navigate", {"url": ORIGIN + "/ai"})
            check(role + " AI screen loaded", "document.querySelector('main')?.innerText.includes('Lịch sử phân tích')&&document.querySelector('main')?.innerText.includes('Gemini')")
            setup_helpers()
            check(role + " own history ready", "(async()=>{window.savedAI=rows(await apiRead('/sites/1/ai/analyses?limit=20'));return savedAI.length>0&&[...main().querySelectorAll('button')].filter(el=>el.textContent==='Xem kết quả').length===savedAI.length;})()")
            selected = [row for row in evidence["analyses"] if row["role"] == role]
            for row in selected:
                expected = row["response"]
                index = evaluate("savedAI.findIndex(row=>row.id===" + json.dumps(expected["id"]) + ")")
                if index < 0: raise AssertionError("Live analysis missing from permitted history")
                evaluate("[...main().querySelectorAll('button')].filter(el=>el.textContent==='Xem kết quả')[" + str(index) + "].click()")
                check(row["name"] + " exact provider content shown", "main().textContent.includes(" + json.dumps(expected["content"]) + ")")
                check(row["name"] + " stored period shown", "main().innerText.includes(" + json.dumps(expected["start_date"] + " — " + expected["end_date"]) + ")")
                check(row["name"] + " fits viewport", "document.documentElement.scrollWidth<=innerWidth+1")
                if row["name"] in ("weekly_report", "staffing"):
                    evaluate("[...main().querySelectorAll('h6')].find(el=>el.textContent.startsWith('Kết quả'))?.scrollIntoView()")
                    screenshot(role + "-saved-" + row["name"])
            if role == "staff":
                check("staff cannot see management totals", "!main().innerText.includes('1.640.000')&&!main().innerText.includes('290.000')")
            evaluate("input('Ngày báo cáo','2026-09-14')")
            check(role + " period change clears old displayed result", "![...main().querySelectorAll('h6')].some(el=>el.textContent.startsWith('Kết quả'))")
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
    only_logins = len(writes) == 2 and all(row["path"] == "/api/auth/login" for row in writes)
    report = {"passed": completed and only_logins and not http_errors and not runtime_errors,
              "scope": "Real saved Gemini responses in current P1 UI; no new provider call; only login audit writes",
              "checks": checks, "writes": writes, "writes_are_only_two_logins": only_logins,
              "http_errors": http_errors, "runtime_errors": runtime_errors,
              "private_browser_profile_removed": not profile.exists()}
    (RUN / "result.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"passed": report["passed"], "checks": len(checks), "artifact_directory": str(RUN)}, ensure_ascii=True))
    if completed and not report["passed"]: raise AssertionError("Post-run verification failed")
