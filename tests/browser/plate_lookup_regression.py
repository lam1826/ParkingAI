"""Actual React forms with fixture API responses; no production data or mutations."""
import base64
import json
from pathlib import Path
import subprocess
import sys
import time
import urllib.request
from uuid import uuid4

from websockets.sync.client import connect

ROOT = Path(__file__).resolve().parents[2]


class Browser:
    def __init__(self, socket):
        self.socket, self.seq = socket, 0

    def call(self, method, params):
        self.seq += 1
        self.socket.send(json.dumps({'id': self.seq, 'method': method, 'params': params}))
        while True:
            result = json.loads(self.socket.recv(timeout=50))
            if result.get('id') == self.seq:
                if 'error' in result:
                    raise RuntimeError('Browser command failed: ' + method)
                return result.get('result', {})

    def evaluate(self, expression):
        result = self.call('Runtime.evaluate', {'expression': expression, 'awaitPromise': True, 'returnByValue': True})
        if 'exceptionDetails' in result:
            self.last_error = result['exceptionDetails']
            raise RuntimeError('Browser evaluation failed; inspect the fixture locally.')
        return result.get('result', {}).get('value')

    def wait(self, expression):
        for _ in range(100):
            if self.evaluate(expression):
                return
            time.sleep(.2)
        raise RuntimeError('Browser condition timed out.')


def main(script=None, artifact_root=None):
    sys.stdout.reconfigure(encoding='utf-8')
    run = (artifact_root or ROOT / 'backend/artifacts/plate-lookup-20260927') / ('browser-' + uuid4().hex[:8])
    run.mkdir(parents=True)
    log = (run / 'process.log').open('w', encoding='utf8')
    children = []
    try:
        children.append(subprocess.Popen(['node', 'node_modules/vite/bin/vite.js', '--host', '127.0.0.1', '--port', '18980', '--strictPort'], cwd=ROOT / 'frontend', stdout=log, stderr=log, creationflags=subprocess.CREATE_NO_WINDOW))
        children.append(subprocess.Popen([r'C:\Program Files\Google\Chrome\Application\chrome.exe', '--headless=new', '--disable-gpu', '--no-first-run', '--no-default-browser-check', '--disable-background-networking', '--disable-sync', '--remote-debugging-port=18982', '--remote-debugging-address=127.0.0.1', '--user-data-dir=' + str(run / 'profile'), 'about:blank'], stdout=log, stderr=log, creationflags=subprocess.CREATE_NO_WINDOW))
        for _ in range(100):
            try:
                urllib.request.urlopen('http://127.0.0.1:18980', timeout=1).close()
                pages = json.load(urllib.request.urlopen('http://127.0.0.1:18982/json', timeout=1))
                target = next(p for p in pages if p['type'] == 'page')
                break
            except Exception:
                time.sleep(.2)
        else:
            raise RuntimeError('Private browser/frontend did not start.')
        with connect(target['webSocketDebuggerUrl'], max_size=15_000_000) as socket:
            browser = Browser(socket)
            browser.call('Page.navigate', {'url': 'http://127.0.0.1:18980/login'})
            browser.wait("document.readyState === 'complete' && !!window.$RefreshReg$")
            try:
                result = browser.evaluate((script or Path(__file__).with_suffix('.js')).read_text(encoding='utf8'))
            except RuntimeError:
                (run / 'browser-error.json').write_text(json.dumps(getattr(browser, 'last_error', {}), ensure_ascii=False), encoding='utf8')
                print('Local fixture diagnostic: ' + str(run / 'browser-error.json'))
                raise
            for width, height, name in [(1440, 1000, 'desktop'), (390, 844, 'mobile')]:
                browser.call('Emulation.setDeviceMetricsOverride', {'width': width, 'height': height, 'deviceScaleFactor': 1, 'mobile': False})
                time.sleep(.3)
                result['checks'].append({'name': name + ' no horizontal overflow', 'passed': browser.evaluate('document.documentElement.scrollWidth <= innerWidth + 1')})
                png = browser.call('Page.captureScreenshot', {'format': 'png'})['data']
                (run / (name + '.png')).write_bytes(base64.b64decode(png))
            result['passed'] = all(c['passed'] for c in result['checks'])
            (run / 'result.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf8')
            print(json.dumps({'artifact': str(run), **result}, ensure_ascii=False))
            return 0 if result['passed'] else 1
    finally:
        for child in reversed(children):
            if child.poll() is None:
                child.terminate()
                try:
                    child.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    child.kill()
        log.close()


if __name__ == '__main__':
    raise SystemExit(main())
