"""Native Chrome media regression using the deployed document header config.

Run with a locally installed Chrome/Chromium (CHROME_BIN may override it).
Only the browser's fake device/permission flags are used, never a JS media mock.
Negative control proves policy denial before checking the repository header.
"""
import json
import os
from pathlib import Path
import shutil
import subprocess
import threading
import time
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from uuid import uuid4

from websockets.sync.client import connect

ROOT = Path(__file__).resolve().parents[2]


def main():
    run = ROOT / "backend/artifacts/camera-native-policy" / uuid4().hex[:8]
    run.mkdir(parents=True)
    header = next(line.strip().partition(": ")[2]
        for line in (ROOT / "frontend/public/_headers").read_text().splitlines()
        if "Permissions-Policy:" in line)

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.send_header("Permissions-Policy", "camera=(), microphone=(), geolocation=()" if self.path == "/denied" else header)
            self.end_headers()
            self.wfile.write(b"<!doctype html><html><title>Native media policy regression</title></html>")

        def log_message(self, *_args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    profile = run / "profile"
    chrome = os.getenv("CHROME_BIN") or shutil.which("google-chrome") or shutil.which("chromium") or r"C:\Program Files\Google\Chrome\Application\chrome.exe"
    results = []
    with (run / "chrome.log").open("w") as log:
        proc = subprocess.Popen([chrome, "--headless=new", "--no-first-run", "--no-default-browser-check",
            "--disable-background-networking", "--disable-component-update", "--disable-sync",
            "--use-fake-device-for-media-stream", "--use-fake-ui-for-media-stream",
            "--remote-debugging-address=127.0.0.1", "--remote-debugging-port=0",
            "--user-data-dir=" + str(profile), "about:blank"], stdout=log, stderr=log,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
        try:
            for _ in range(100):
                portfile = profile / "DevToolsActivePort"
                if portfile.exists():
                    port = portfile.read_text().splitlines()[0]
                    break
                time.sleep(.1)
            else:
                raise RuntimeError("Chrome failed to start")
            targets = json.load(urllib.request.urlopen("http://127.0.0.1:" + port + "/json"))
            with connect(next(t["webSocketDebuggerUrl"] for t in targets if t["type"] == "page")) as ws:
                seq = 0

                def call(method, params):
                    nonlocal seq
                    seq += 1
                    ws.send(json.dumps({"id": seq, "method": method, "params": params}))
                    while True:
                        reply = json.loads(ws.recv(timeout=35))
                        if reply.get("id") == seq:
                            if "error" in reply:
                                raise RuntimeError("CDP failed: " + method)
                            return reply["result"]

                def evaluate(expression):
                    result = call("Runtime.evaluate", {"expression": expression, "awaitPromise": True, "returnByValue": True})
                    if "exceptionDetails" in result:
                        raise RuntimeError("Native browser evaluation failed")
                    return result["result"].get("value")

                for path in ("denied", "configured"):
                    url = f"http://127.0.0.1:{server.server_port}/{path}"
                    call("Page.navigate", {"url": url})
                    for _ in range(100):
                        if evaluate("location.href === " + json.dumps(url) + " && document.readyState === 'complete'"):
                            break
                        time.sleep(.1)
                    results.append({"case": path, **evaluate("""(async () => {
                        const result = {native: String(navigator.mediaDevices.getUserMedia).includes('[native code]'),
                          policyAllowsCamera: document.featurePolicy.allowsFeature('camera'),
                          policyAllowsMicrophone: document.featurePolicy.allowsFeature('microphone'),
                          policyAllowsGeolocation: document.featurePolicy.allowsFeature('geolocation')};
                        let stream;
                        try {stream = await navigator.mediaDevices.getUserMedia({video: true, audio: false});
                          const video = document.createElement('video'); video.muted = true; video.srcObject = stream;
                          document.body.append(video); await video.play();
                          result.opened = true; result.videoWidth = video.videoWidth;
                        } catch (error) {result.opened = false; result.errorName = error.name;}
                        finally {stream?.getTracks().forEach(track => track.stop());}
                        return result;
                    })()""")})
        finally:
            proc.terminate()
            try:
                proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait()
            server.shutdown()
            server.server_close()
            (run / "results.json").write_text(json.dumps(results, indent=2), encoding="utf-8")
            if profile.exists() and profile.resolve().is_relative_to(run.resolve()):
                shutil.rmtree(profile, ignore_errors=True)
    print(json.dumps({"artifact": str(run), "results": results}, ensure_ascii=True))
    assert results[0]["native"] and not results[0]["opened"] and results[0]["errorName"] == "NotAllowedError"
    assert results[1]["native"] and results[1]["policyAllowsCamera"] and results[1]["opened"] and results[1]["videoWidth"] > 0
    assert not results[1]["policyAllowsMicrophone"] and not results[1]["policyAllowsGeolocation"]


if __name__ == "__main__":
    main()
