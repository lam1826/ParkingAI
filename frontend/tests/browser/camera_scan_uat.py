"""Camera UI with a simulated CC0-image feed and real local OCR, never hardware.

The only permitted writes are login, manual observations and their review. No admission,
checkout, automation policy, bank, or provider request is permitted.
"""
import argparse
import base64
import hashlib
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
parser.add_argument("--before-fix", action="store_true")
parser.add_argument("--positive-fixture", choices=("cc0", "vn-first"), default="cc0")
args = parser.parse_args()
credentials = json.loads(args.credentials.read_text(encoding="utf-8"))
marker = json.loads(Path(credentials["database"] + ".demo.json").read_text(encoding="utf-8"))
if credentials.get("profile") != "single-lot-academic-v1" or marker.get("synthetic_history") is not True:
    raise ValueError("Explicit synthetic database required")
BASE = ROOT / "backend/artifacts/camera-scan-uat"
OUT = BASE / uuid4().hex[:10]
OUT.mkdir(parents=True)
PROFILE = OUT / "chrome-profile"
ORIGIN = "http://127.0.0.1:8793"
checks, writes, failures, errors, scans, screenshots, accuracy_checks = [], [], [], [], [], [], []
complete = False
positive_fixture = {"file": "backend/artifacts/vision/rolls-royce-cc0.jpg", "name": "rolls-royce-cc0.jpg", "ground_truth": "LD-45-58-BI", "normalized": "LD4558BI", "human_reviewed": False}
if args.positive_fixture == "vn-first":
    manifest_path = ROOT / "backend/artifacts/phone-vn-acceptance/manifest-cctv.json"
    if hashlib.sha256(manifest_path.read_bytes()).hexdigest() != "cca84266dbb4c290c111ed18a186808a8aa9e5aebd667c14e023440aed497887":
        raise ValueError("Frozen VN manifest hash changed")
    first = json.loads(manifest_path.read_text(encoding="utf-8"))["samples"][0]
    path = manifest_path.parent / first["file"]
    if hashlib.sha256(path.read_bytes()).hexdigest() != first["sha256"]:
        raise ValueError("First frozen VN image hash changed")
    positive_fixture = {"file": str(path), "name": first["id"], "ground_truth": first["plates"][0]["text"], "normalized": first["plates"][0]["text"], "human_reviewed": first["human_reviewed"]}
image_data = base64.b64encode((ROOT / positive_fixture["file"]).read_bytes()).decode()
negative_image_data = base64.b64encode((ROOT / "backend/artifacts/vision/colorado-cc0.jpg").read_bytes()).decode()
with socket.socket() as channel:
    channel.bind(("127.0.0.1", 0))
    port = channel.getsockname()[1]
log = (OUT / "browser.log").open("w", encoding="utf-8")
process = subprocess.Popen([
    r"C:\Program Files\Google\Chrome\Application\chrome.exe", "--headless=new", "--disable-gpu",
    "--no-first-run", "--no-default-browser-check", "--disable-background-networking",
    "--disable-component-update", "--disable-sync", "--remote-debugging-address=127.0.0.1",
    f"--remote-debugging-port={port}", "--user-data-dir=" + str(PROFILE), "about:blank",
], stdout=log, stderr=log, creationflags=subprocess.CREATE_NO_WINDOW)
try:
    for _ in range(100):
        try:
            page = next(row for row in json.load(urllib.request.urlopen(f"http://127.0.0.1:{port}/json", timeout=1)) if row["type"] == "page")
            break
        except (OSError, StopIteration):
            time.sleep(.1)
    else:
        raise RuntimeError("Private Chrome did not become ready")
    with connect(page["webSocketDebuggerUrl"], max_size=20_000_000) as ws:
        sequence = 0

        def call(method, params=None):
            global sequence
            sequence += 1
            wanted = sequence
            ws.send(json.dumps({"id": wanted, "method": method, "params": params or {}}))
            while True:
                result = json.loads(ws.recv(timeout=150))
                if result.get("method") == "Fetch.requestPaused":
                    paused = result["params"]
                    req = paused["request"]
                    parsed = urllib.parse.urlsplit(req["url"])
                    local = parsed.netloc == "127.0.0.1:8793"
                    allowed = parsed.scheme in {"data", "blob", "about"} or (local and (
                        req["method"] in {"GET", "HEAD"} or (req["method"] == "POST" and (
                            parsed.path in {"/api/auth/login", "/api/v2/vision/observations"}
                            or (parsed.path.startswith("/api/v2/vision/observations/") and parsed.path.endswith("/review"))))))
                    if local and req["method"] not in {"GET", "HEAD"}:
                        writes.append({"path": parsed.path, "allowed": allowed})
                    sequence += 1
                    ws.send(json.dumps({"id": sequence, "method": "Fetch.continueRequest" if allowed else "Fetch.failRequest", "params": {
                        "requestId": paused["requestId"], **({} if allowed else {"errorReason": "BlockedByClient"})}}))
                if result.get("method") == "Runtime.exceptionThrown":
                    errors.append({"kind": "browser", "text": result["params"]["exceptionDetails"]["text"]})
                if result.get("method") == "Network.responseReceived":
                    response = result["params"]["response"]
                    path = urllib.parse.urlsplit(response["url"]).path
                    if response["status"] >= 400 and path.startswith("/api/"):
                        failures.append({"path": path, "status": response["status"]})
                    if path == "/api/v2/vision/observations" and response["status"] == 201:
                        scans.append(result["params"]["requestId"])
                if result.get("id") == wanted:
                    if "error" in result:
                        raise RuntimeError(method + " failed")
                    return result.get("result", {})

        def js(source):
            result = call("Runtime.evaluate", {"expression": source, "returnByValue": True, "awaitPromise": True})
            if "exceptionDetails" in result:
                raise RuntimeError("Browser expression failed; private values withheld")
            return result.get("result", {}).get("value")

        def check(label, source, wait=True):
            for _ in range(200 if wait else 1):
                if js(source):
                    checks.append({"check": label, "passed": True})
                    return
                time.sleep(.1)
            checks.append({"check": label, "passed": False})
            raise AssertionError(label)

        def button(label):
            return "[...document.querySelectorAll('main button')].find(e=>e.textContent.trim()===" + json.dumps(label) + ")"

        for method in ("Page.enable", "Runtime.enable", "Network.enable"):
            call(method)
        call("Fetch.enable", {"patterns": [{"urlPattern": "*"}]})
        call("Page.navigate", {"url": ORIGIN + "/login"})
        check("login form", "!!document.querySelector('#password')")
        for selector, value in (("#username", "manager_demo"), ("#password", credentials["accounts"]["manager_demo"])):
            js("(()=>{const e=document.querySelector(" + json.dumps(selector) + ");Object.getOwnPropertyDescriptor(HTMLInputElement.prototype,'value').set.call(e," + json.dumps(value) + ");e.dispatchEvent(new Event('input',{bubbles:true}));})()")
        js("document.querySelector('button[type=submit]').click()")
        check("authenticated", "location.pathname!=='/login'&&!!document.querySelector('main h1')")
        call("Page.navigate", {"url": ORIGIN + "/sites"})
        check("operations camera switch", "!!" + button("Camera"))
        js(button("Camera") + ".click()")
        check("camera loaded", "!!document.querySelector('video')&&!!" + button("Dùng webcam"))
        policy = js("fetch('/api/v2/cameras/1/automation',{headers:{Authorization:'Bearer '+localStorage.getItem('token')}}).then(r=>r.json())")
        checks.append({"check": "automation remains disabled", "passed": policy.get("enabled") is False})
        if policy.get("enabled") is not False:
            raise AssertionError("This bounded manual scan test requires disabled policy")
        # Deterministic simulated feed. Camera permission/hardware is not tested.
        js("""(async()=>{
            const img=new Image();img.src='data:image/jpeg;base64,""" + image_data + """';await img.decode();
            const canvas=document.createElement('canvas');canvas.width=img.width;canvas.height=img.height;
            const context=canvas.getContext('2d');context.drawImage(img,0,0);
            window.cameraUatCanvas=canvas;window.cameraUatStream=canvas.captureStream(5);
            window.cameraUatTimer=setInterval(()=>context.drawImage(img,0,0),200);
            navigator.mediaDevices.getUserMedia=async()=>window.cameraUatStream;
        })()""")
        js(button("Dùng webcam") + ".click()")
        check("simulated camera has video frames", "document.querySelector('video').readyState>=2&&document.querySelector('video').videoWidth>0")
        if args.before_fix:
            # A failing regression records the original missing operator action.
            check("manual plate scan exists while automation policy is off", "!!" + button("Quét biển số"), wait=False)
        else:
            check("manual plate scan enabled with policy off", "!!" + button("Quét biển số") + "&&!" + button("Quét biển số") + ".disabled")
            js(button("Quét biển số") + ".click()")
            check("scan shows busy feedback", "!!document.querySelector('[aria-busy=true]')||!!document.querySelector('#camera-confirmed-plate')")
            check("real OCR response visible for manual review", "!!document.querySelector('#camera-confirmed-plate')&&!!document.querySelector('[data-camera-ocr-status]')")
            check("real OCR matches frozen positive fixture text", "document.querySelector('#camera-confirmed-plate').value.replace(/[ .-]/g,'')===" + json.dumps(positive_fixture["normalized"]))
            check("manual result is not treated as automatic passage", "document.querySelector('[data-camera-ocr-status]').getAttribute('data-camera-ocr-status')==='recognized'&&!!" + button("Dùng biển số & kiểm tra thủ công"))
            check("scan preserves policy off", "fetch('/api/v2/cameras/1/automation',{headers:{Authorization:'Bearer '+localStorage.getItem('token')}}).then(r=>r.json()).then(r=>r.enabled===false)")
            response = json.loads(call("Network.getResponseBody", {"requestId": scans[-1]})["body"])
            checks.append({"check": "one-off webcam snapshot has manual provenance and pending review", "passed": response["capture_source"] == "manual_upload" and response["review_status"] == "pending"})
            accuracy_checks.append({"fixture": positive_fixture["name"], "ground_truth": positive_fixture["ground_truth"], "human_reviewed": positive_fixture["human_reviewed"], "suggested_plate": response["suggested_plate"], "exact_normalized_match": response["suggested_plate"].replace("-", "").replace(".", "") == positive_fixture["normalized"]})
            result = js("({status:document.querySelector('[data-camera-ocr-status]').getAttribute('data-camera-ocr-status'),plate:document.querySelector('#camera-confirmed-plate').value,text:document.querySelector('[data-camera-ocr-status]').textContent})")
            (OUT / "ocr-result.json").write_text(json.dumps({"simulated_feed": True, "physical_camera_tested": False, "fixture": positive_fixture["name"], "ground_truth": positive_fixture["ground_truth"], "human_reviewed": positive_fixture["human_reviewed"], "output": result, "server_confidence": response["confidence"], "detections": response["detections"], "exact_match": result["plate"].replace("-", "").replace(".", "") == positive_fixture["normalized"]}, ensure_ascii=False, indent=2), encoding="utf-8")
            for width, height in ((1440, 1000), (390, 844)):
                call("Emulation.setDeviceMetricsOverride", {"width": width, "height": height, "deviceScaleFactor": 1, "mobile": width < 500})
                js("window.scrollTo(0,0);new Promise(resolve=>setTimeout(resolve,200))")
                check(f"camera viewport {width}px does not overflow", "document.documentElement.scrollWidth<=innerWidth+1")
                name = f"camera-{width}.png"
                (OUT / name).write_bytes(base64.b64decode(call("Page.captureScreenshot", {"format": "png", "captureBeyondViewport": False})["data"]))
                screenshots.append(name)
                if width < 500:
                    js("document.querySelector('.camera-controls').scrollIntoView({block:'center'});new Promise(resolve=>setTimeout(resolve,100))")
                    name = "camera-390-controls.png"
                    (OUT / name).write_bytes(base64.b64decode(call("Page.captureScreenshot", {"format": "png", "captureBeyondViewport": False})["data"]))
                    screenshots.append(name)
            js(button("Tắt webcam") + ".click()")
            check("stop releases simulated camera track", "window.cameraUatStream.getVideoTracks().every(track=>track.readyState==='ended')")
            check("manual scan disabled without camera frames", button("Quét biển số") + ".disabled")
            js("document.querySelector('main .demo-help summary').click()")
            js("""(()=>{const data=Uint8Array.from(atob('""" + negative_image_data + """'),c=>c.charCodeAt(0));const transfer=new DataTransfer();transfer.items.add(new File([data],'colorado-cc0.jpg',{type:'image/jpeg'}));const input=document.querySelector('main input[type=file]');input.files=transfer.files;input.dispatchEvent(new Event('change',{bubbles:true}));})()""")
            check("real undetected plate image shows explicit no-plate feedback", "document.querySelector('[data-camera-ocr-status]')?.getAttribute('data-camera-ocr-status')==='no_plate'")
            response = json.loads(call("Network.getResponseBody", {"requestId": scans[-1]})["body"])
            accuracy_checks.append({"fixture": "colorado-cc0.jpg", "ground_truth": "AWY-U50", "suggested_plate": response["suggested_plate"], "exact_normalized_match": response["suggested_plate"] == "AWYU50"})
            check("failed recognition clears previous suggested plate", "document.querySelector('#camera-confirmed-plate').value===''")
            check("empty plate cannot be accepted", button("Dùng biển số & kiểm tra thủ công") + ".disabled")
            js("(()=>{const e=document.querySelector('#camera-confirmed-plate');Object.getOwnPropertyDescriptor(HTMLInputElement.prototype,'value').set.call(e,'AWY-U50');e.dispatchEvent(new Event('input',{bubbles:true}));})()")
            check("operator can correct missed plate", "!" + button("Dùng biển số & kiểm tra thủ công") + ".disabled")
            js(button("Dùng biển số & kiểm tra thủ công") + ".click()")
            check("confirmed plate is handed to manual entry without admitting vehicle", "document.querySelector('#operation-plate')?.value==='AWY-U50'&&!!" + button("Ghi nhận xe vào"))
            js(button("Camera") + ".click()")
            check("camera can reopen after review", "!!document.querySelector('#camera-recent-frame')")
            js("document.querySelector('main .demo-help summary').click()")
            js("(()=>{const e=document.querySelector('#camera-recent-frame');e.value=[...e.options].find(o=>o.textContent.startsWith('AWY-U50')).value;e.dispatchEvent(new Event('change',{bubbles:true}));})()")
            check("accepted snapshot can be inspected", "document.querySelector('#camera-confirmed-plate')?.value==='AWY-U50'")
            if not js("document.querySelector('#camera-confirmed-plate').readOnly"):
                js("(()=>{const e=document.querySelector('#camera-confirmed-plate');Object.getOwnPropertyDescriptor(HTMLInputElement.prototype,'value').set.call(e,'AWY-U51');e.dispatchEvent(new Event('input',{bubbles:true}));})()")
                check("old bug permits editing accepted plate", "document.querySelector('#camera-confirmed-plate').value==='AWY-U51'")
                js(button("Dùng biển số & kiểm tra thủ công") + ".click()")
                check("old bug silently hands off original instead of edited plate", "document.querySelector('#operation-plate')?.value==='AWY-U50'")
                checks.append({"check": "accepted snapshot must not silently discard a plate edit", "passed": False})
                raise AssertionError("Accepted snapshot accepted AWY-U51 in field but handed off AWY-U50")
            check("accepted snapshot field is read-only", "document.querySelector('#camera-confirmed-plate').readOnly")
            check("accepted snapshot explains that a new scan is needed for correction", "document.querySelector('main').innerText.includes('quét hoặc chọn ảnh mới')")
            checks.append({"check": "two real manual OCR uploads, one explicit review and no admission/process writes", "passed": len(scans) == 2 and sum(row["path"].endswith("/review") for row in writes) == 1 and all(row["path"] in {"/api/auth/login", "/api/v2/vision/observations"} or row["path"].endswith("/review") for row in writes)})
            complete = all(row["passed"] for row in checks) and not errors and not failures
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
    (OUT / "result.json").write_text(json.dumps({"complete": complete, "complete_scope": "Camera capture/review workflow; OCR accuracy measured separately below", "before_fix": args.before_fix, "checks": checks, "accuracy_checks": accuracy_checks, "ocr_accuracy_passed": len(accuracy_checks) == 2 and all(row["exact_normalized_match"] for row in accuracy_checks), "writes": writes, "api_failures": failures, "errors": errors, "screenshots": screenshots, "private_profile_removed": not PROFILE.exists()}, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps({"artifacts": str(OUT), "passed": sum(row["passed"] for row in checks), "checks": len(checks), "workflow_complete": complete, "ocr_exact_matches": sum(row["exact_normalized_match"] for row in accuracy_checks), "ocr_samples": len(accuracy_checks)}, ensure_ascii=True), flush=True)
raise SystemExit(0 if complete else 1)
