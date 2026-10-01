"""Actual CameraOperations with native fake camera and isolated fixture API.

The Vite document receives the current Pages Permissions-Policy. No production
requests, credentials, business writes, physical camera or getUserMedia override.
"""
import base64
import json
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import time
import urllib.request
from uuid import uuid4

from websockets.sync.client import connect
from plate_lookup_regression import Browser, ROOT


def free_port():
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def main():
    run = ROOT / "backend/artifacts/camera-source-regression" / uuid4().hex[:8]
    run.mkdir(parents=True)
    config = ROOT / "frontend/node_modules/.cache" / ("camera-" + uuid4().hex + ".mjs")
    config.parent.mkdir(exist_ok=True)
    policy = next(line.strip().partition(": ")[2] for line in (ROOT / "frontend/public/_headers").read_text().splitlines() if "Permissions-Policy:" in line)
    config.write_text("import base from '../../vite.config.js';\nexport default {...base, server: {headers: " + json.dumps({"Permissions-Policy": policy}) + "}};\n", encoding="utf-8")
    port, debug_port = free_port(), free_port()
    children = []
    with (run / "process.log").open("w", encoding="utf-8") as log:
        try:
            children.append(subprocess.Popen(["node", "node_modules/vite/bin/vite.js", "--config", str(config), "--host", "127.0.0.1", "--port", str(port), "--strictPort"], cwd=ROOT / "frontend", stdout=log, stderr=log, creationflags=subprocess.CREATE_NO_WINDOW))
            children.append(subprocess.Popen([r"C:\Program Files\Google\Chrome\Application\chrome.exe", "--headless=new", "--no-first-run", "--no-default-browser-check", "--disable-background-networking", "--disable-component-update", "--disable-sync", "--use-fake-device-for-media-stream", "--use-fake-ui-for-media-stream", "--remote-debugging-port=" + str(debug_port), "--remote-debugging-address=127.0.0.1", "--user-data-dir=" + str(run / "profile"), "about:blank"], stdout=log, stderr=log, creationflags=subprocess.CREATE_NO_WINDOW))
            for _ in range(100):
                try:
                    urllib.request.urlopen(f"http://127.0.0.1:{port}", timeout=1).close()
                    targets = json.load(urllib.request.urlopen(f"http://127.0.0.1:{debug_port}/json", timeout=1))
                    target = next(item for item in targets if item["type"] == "page")
                    break
                except (OSError, StopIteration):
                    time.sleep(.2)
            else:
                raise RuntimeError("Local browser/frontend failed to start")
            with connect(target["webSocketDebuggerUrl"], max_size=15_000_000) as ws:
                browser = Browser(ws)
                browser.call("Page.navigate", {"url": f"http://127.0.0.1:{port}/login"})
                browser.wait("document.readyState === 'complete' && !!window.$RefreshReg$")
                try:
                    result = browser.evaluate(Path(__file__).with_suffix(".js").read_text(encoding="utf-8"))
                except RuntimeError:
                    (run / "browser-error.json").write_text(json.dumps(getattr(browser, "last_error", {}), ensure_ascii=True), encoding="utf-8")
                    raise
                for width, height, name in [(1440, 1000, "desktop"), (390, 844, "mobile")]:
                    browser.call("Emulation.setDeviceMetricsOverride", {"width": width, "height": height, "deviceScaleFactor": 1, "mobile": False})
                    time.sleep(.3)
                    result["checks"].append({"name": name + " mounted camera no horizontal overflow", "passed": browser.evaluate("document.documentElement.scrollWidth <= innerWidth + 1")})
                    png = browser.call("Page.captureScreenshot", {"format": "png"})["data"]
                    (run / (name + ".png")).write_bytes(base64.b64decode(png))
                browser.evaluate("window.__cameraSourceCleanup()")
                result["passed"] = all(check["passed"] for check in result["checks"])
                (run / "result.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
                print(json.dumps({"artifact": str(run), **result}, ensure_ascii=True))
                return 0 if result["passed"] else 1
        finally:
            for child in reversed(children):
                if child.poll() is None:
                    child.terminate()
                    try:
                        child.wait(timeout=10)
                    except subprocess.TimeoutExpired:
                        child.kill()
                        child.wait()
            config.unlink(missing_ok=True)
            profile = run / "profile"
            if profile.exists() and profile.resolve().is_relative_to(run.resolve()):
                shutil.rmtree(profile, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
