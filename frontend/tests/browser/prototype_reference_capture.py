"""Read-only visual references from the user's approved prototype on local8790."""
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
OUT = ROOT / "backend/artifacts/prototype-reference" / uuid4().hex[:10]
OUT.mkdir(parents=True)
PROFILE = OUT / "chrome-profile"
print(json.dumps({"references": str(OUT)}, ensure_ascii=True), flush=True)
with socket.socket() as channel:
    channel.bind(("127.0.0.1", 0))
    port = channel.getsockname()[1]
log = (OUT / "browser.log").open("w", encoding="utf-8")
process = subprocess.Popen([r"C:\Program Files\Google\Chrome\Application\chrome.exe", "--headless=new", "--disable-gpu", "--no-first-run", "--no-default-browser-check", "--disable-background-networking", "--disable-component-update", "--disable-sync", "--remote-debugging-address=127.0.0.1", f"--remote-debugging-port={port}", "--user-data-dir=" + str(PROFILE), "about:blank"], stdout=log, stderr=log, creationflags=subprocess.CREATE_NO_WINDOW)
measurements = []
try:
    for _ in range(100):
        try:
            page = next(row for row in json.load(urllib.request.urlopen(f"http://127.0.0.1:{port}/json", timeout=1)) if row["type"] == "page")
            break
        except (OSError, StopIteration):
            time.sleep(.1)
    with connect(page["webSocketDebuggerUrl"], max_size=20_000_000) as ws:
        seq = 0
        def call(method, params=None):
            global seq
            seq += 1
            wanted = seq
            ws.send(json.dumps({"id": wanted, "method": method, "params": params or {}}))
            while True:
                result = json.loads(ws.recv(timeout=30))
                if result.get("method") == "Fetch.requestPaused":
                    paused = result["params"]
                    parsed = urllib.parse.urlsplit(paused["request"]["url"])
                    allowed = parsed.netloc == "127.0.0.1:8790" or parsed.scheme in {"data", "blob", "about"}
                    seq += 1
                    ws.send(json.dumps({"id": seq, "method": "Fetch.continueRequest" if allowed else "Fetch.failRequest", "params": {"requestId": paused["requestId"], **({} if allowed else {"errorReason": "BlockedByClient"})}}))
                if result.get("id") == wanted:
                    if "error" in result:
                        raise RuntimeError(method)
                    return result.get("result", {})
        def js(source):
            result = call("Runtime.evaluate", {"expression": source, "returnByValue": True, "awaitPromise": True})
            if "exceptionDetails" in result:
                raise RuntimeError("Reference evaluation failed")
            return result.get("result", {}).get("value")
        def click(selector):
            js("document.querySelector(" + json.dumps(selector) + ").click()")
        def shot(name, mobile=False):
            call("Emulation.setDeviceMetricsOverride", {"width": 390 if mobile else 1440, "height": 844 if mobile else 1000, "deviceScaleFactor": 1, "mobile": mobile})
            js("window.scrollTo(0,0)")
            time.sleep(.3)
            measurements.append({"image": name, "layout": js("({innerWidth,scrollWidth:document.documentElement.scrollWidth,scale:visualViewport.scale})")})
            (OUT / (name + ".png")).write_bytes(base64.b64decode(call("Page.captureScreenshot", {"format": "png", "captureBeyondViewport": False})["data"]))
        call("Runtime.enable")
        call("Fetch.enable", {"patterns": [{"urlPattern": "*"}]})
        call("Page.navigate", {"url": "http://127.0.0.1:8790/?v=full-demo#customer"})
        for _ in range(100):
            if js("!!window.ParkingDemo&&!!document.querySelector('.customer-nav')"):
                break
            time.sleep(.1)
        for tab in ("fees", "booking", "tickets", "support"):
            click('[data-action="nav"][data-tab="' + tab + '"]')
            shot("customer-" + tab + "-desktop")
            shot("customer-" + tab + "-mobile", True)
        click('[data-action="nav"][data-tab="fees"]')
        click('[data-action="sample-owned"]')
        shot("customer-fee-result-desktop")
        shot("customer-fee-result-mobile", True)
        click('[data-action="chat-open"]')
        shot("customer-chat-desktop")
        shot("customer-chat-mobile", True)
        click('[data-action="chat-close"]')
        for role in ("manager", "admin"):
            click('[data-action="role"][data-role="' + role + '"]')
            for tab in (("overview", "operations") if role == "manager" else ("overview",)):
                click('[data-action="nav"][data-tab="' + tab + '"]')
                shot(role + "-" + tab + "-desktop")
                shot(role + "-" + tab + "-mobile", True)
finally:
    process.terminate()
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        process.kill(); process.wait(timeout=5)
    log.close()
    if PROFILE.resolve().parent == OUT.resolve() and OUT.resolve().is_relative_to((ROOT / "backend/artifacts/prototype-reference").resolve()):
        for _ in range(30):
            try:
                shutil.rmtree(PROFILE); break
            except FileNotFoundError:
                break
            except PermissionError:
                time.sleep(.1)
    (OUT / "capture.json").write_text(json.dumps({"url": "http://127.0.0.1:8790/?v=full-demo", "measurements": measurements, "private_profile_removed": not PROFILE.exists()}, indent=2), encoding="utf-8")
    print(json.dumps({"references": str(OUT), "images": len(measurements)}, ensure_ascii=True))
