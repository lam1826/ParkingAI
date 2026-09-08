"""Run the actual React useRemote hook in a private browser, without a backend."""
import json
from pathlib import Path
import subprocess
import sys
import time
import urllib.request
from uuid import uuid4
from websockets.sync.client import connect

sys.stdout.reconfigure(encoding="utf-8")
ROOT = Path(__file__).resolve().parents[2]
RUN = ROOT / "backend/artifacts/review-remote" / uuid4().hex[:10]
RUN.mkdir(parents=True)
output = (RUN / "process.log").open("w", encoding="utf-8")
children = []
try:
    children.append(subprocess.Popen(["node", "node_modules/vite/bin/vite.js", "--host", "127.0.0.1", "--port", "18970", "--strictPort"], cwd=ROOT / "frontend", stdout=output, stderr=output, creationflags=subprocess.CREATE_NO_WINDOW))
    children.append(subprocess.Popen([r"C:\Program Files\Google\Chrome\Application\chrome.exe", "--headless=new", "--disable-gpu", "--no-first-run", "--no-default-browser-check", "--disable-background-networking", "--disable-component-update", "--disable-sync", "--remote-debugging-port=18972", "--remote-debugging-address=127.0.0.1", "--user-data-dir=" + str(RUN / "chrome-profile"), "about:blank"], stdout=output, stderr=output, creationflags=subprocess.CREATE_NO_WINDOW))
    for attempt in range(100):
        try:
            urllib.request.urlopen("http://127.0.0.1:18970", timeout=1).close()
            pages = json.load(urllib.request.urlopen("http://127.0.0.1:18972/json", timeout=1))
            target = next(page for page in pages if page["type"] == "page")
            break
        except Exception:
            time.sleep(.2)
    else:
        raise RuntimeError("Private frontend/browser did not start")
    with connect(target["webSocketDebuggerUrl"], max_size=10_000_000) as ws:
        seq = 0
        def call(method, params):
            global seq
            seq += 1
            ws.send(json.dumps({"id": seq, "method": method, "params": params}))
            while True:
                response = json.loads(ws.recv(timeout=40))
                if response.get("id") == seq:
                    if "error" in response:
                        raise RuntimeError(response["error"])
                    return response.get("result", {})
        def evaluate(expression):
            response = call("Runtime.evaluate", {"expression": expression, "awaitPromise": True, "returnByValue": True})
            if "exceptionDetails" in response:
                raise RuntimeError(response["exceptionDetails"])
            return response.get("result", {}).get("value")
        call("Page.navigate", {"url": "http://127.0.0.1:18970"})
        for attempt in range(100):
            if evaluate("document.readyState === 'complete' && !!window.$RefreshReg$"):
                break
            time.sleep(.2)
        result = evaluate(r"""(async () => {
          const hookSource = await (await fetch('/src/pages/Expansion/shared.jsx')).text();
          const mainSource = await (await fetch('/src/main.jsx')).text();
          const reactUrl = hookSource.match(/["']([^"']*\/deps\/react\.js[^"']*)["']/)[1];
          const domUrl = mainSource.match(/["']([^"']*\/deps\/react-dom_client\.js[^"']*)["']/)[1];
          const ReactModule = await import(reactUrl);
          const React = ReactModule.default || ReactModule;
          const DomModule = await import(domUrl);
          const {createRoot} = DomModule.default || DomModule;
          const {useRemote, refreshAll} = await import('/src/pages/Expansion/shared.jsx');
          const delay = () => new Promise(resolve => setTimeout(resolve, 20));
          const scenarios = [];
          {
            const loaders = { A: async () => 'A', B: async () => 'B' };
            let latest, choose;
            function Harness() {
              const [filter, setFilter] = React.useState('A');
              const remote = useRemote(loaders[filter]);
              choose = setFilter; latest = remote;
              return React.createElement('output', null, JSON.stringify({filter, data: remote.data, loading: remote.loading}));
            }
            const host = document.createElement('div'); document.body.appendChild(host);
            const root = createRoot(host); root.render(React.createElement(Harness));
            for(let n=0;n<100 && latest?.data !== 'A';n++) await delay();
            if(latest?.data !== 'A') throw Error('Initial A did not load');
            const reloadCapturedBeforeMutation = latest.reload;
            choose('B');
            for(let n=0;n<100 && latest?.data !== 'B';n++) await delay();
            if(latest?.data !== 'B') throw Error('New B did not load');
            await reloadCapturedBeforeMutation();
            for(let n=0;n<10;n++) await delay();
            const state = {data: latest.data, loading: latest.loading};
            root.unmount(); host.remove();
            scenarios.push({scenario:'late mutation refresh after switching filter A to B', expected:{data:'B',loading:false}, actual:state, passed:state.data === 'B' && !state.loading});
          }
          {
            // Two independent sections: one fails, the other keeps its data; the failed one retries alone;
            // a mutation refresh (refreshAll) reloads both exactly once.
            const calls = {good: 0, bad: 0};
            let failBad = true;
            const loaders = {
              good: async () => { calls.good++; await delay(); return 'GOOD'; },
              bad: async () => { calls.bad++; await delay(); if (failBad) throw new Error('section down'); return 'FIXED'; },
            };
            let latest;
            function Harness() {
              const good = useRemote(loaders.good);
              const bad = useRemote(loaders.bad);
              latest = {good, bad};
              return React.createElement('output', null, JSON.stringify({g: good.data, b: bad.data, be: bad.error}));
            }
            const host = document.createElement('div'); document.body.appendChild(host);
            const root = createRoot(host); root.render(React.createElement(Harness));
            for(let n=0;n<100 && !(latest?.good.data === 'GOOD' && latest?.bad.error && !latest?.bad.loading);n++) await delay();
            const isolated = latest.good.data === 'GOOD' && !latest.good.error && latest.bad.data === null && !!latest.bad.error && !latest.bad.loading;
            failBad = false;
            await latest.bad.reload();
            for(let n=0;n<100 && latest?.bad.data !== 'FIXED';n++) await delay();
            const retried = latest.bad.data === 'FIXED' && !latest.bad.error && latest.good.data === 'GOOD' && calls.good === 1 && calls.bad === 2;
            await refreshAll(latest.good, latest.bad)();
            for(let n=0;n<10;n++) await delay();
            const refreshed = calls.good === 2 && calls.bad === 3 && latest.good.data === 'GOOD' && latest.bad.data === 'FIXED';
            root.unmount(); host.remove();
            scenarios.push({scenario:'one section fails while the other keeps data; retry alone; refreshAll reloads both', expected:{isolated:true, retried:true, refreshed:true}, actual:{isolated, retried, refreshed, calls}, passed: isolated && retried && refreshed});
          }
          for (const failedPath of ['/api/v2/plans', '/api/v2/catalog/vehicle-types', '/api/v2/me/vehicle-requests']) {
            // Mount the real portal: auxiliary API failures must not hide the customer's cars.
            const {default: CustomerPortal} = await import('/src/pages/Expansion/CustomerPortal.jsx');
            const {default: api} = await import('/src/services/api.js');
            const previousAdapter = api.defaults.adapter;
            const calls = {};
            let failPlans = true;
            const responses = {
              '/api/v2/me/profile': {linked:true, customer:{id:1, full_name:'Customer fixture', phone_number:'0900000000'}},
              '/api/v2/catalog/vehicle-types': [{id:1, name:'Car fixture'}],
              '/api/v2/plans': [{id:'plan-test', site_name:'Site fixture', name:'Monthly fixture', type_name:'Car', price:100000, duration_days:30}],
              '/api/v2/me/vehicles': [{id:1, license_plate:'CAR-FIXTURE', vehicle_type_id:1, type_name:'Car fixture'}],
            };
            api.defaults.adapter = async (config) => {
              calls[config.url] = (calls[config.url] || 0) + 1;
              await delay();
              if (config.url === failedPath && failPlans) {
                throw Object.assign(new Error('Plan catalog unavailable'), {config, response:{status:503, data:{detail:'Plan catalog unavailable'}}});
              }
              return {data:responses[config.url] || [], status:200, statusText:'OK', headers:{}, config};
            };
            const host = document.createElement('div'); document.body.appendChild(host);
            const root = createRoot(host);
            try {
              root.render(React.createElement(CustomerPortal));
              for(let n=0;n<100 && !host.innerText.includes('CAR-FIXTURE');n++) await delay();
              const isolated = host.innerText.includes('Customer fixture') && host.innerText.includes('CAR-FIXTURE');
              const profileCalls = calls['/api/v2/me/profile'];
              const carsCalls = calls['/api/v2/me/vehicles'];
              const tab = [...host.querySelectorAll('[role=tab]')].find(item => item.innerText.includes('QR'));
              if (failedPath === '/api/v2/plans') tab?.click();
              await delay(); await delay();
              const retry = [...host.querySelectorAll('[role=alert] button')].find(item => item.textContent.includes('Thử lại'));
              failPlans = false;
              retry?.click();
              for(let n=0;n<100 && (calls[failedPath] !== 2 || host.innerText.includes('Plan catalog unavailable'));n++) await delay();
              await delay();
              const retried = !!retry && calls[failedPath] === 2 && calls['/api/v2/me/profile'] === profileCalls
                && calls['/api/v2/me/vehicles'] === carsCalls && !host.innerText.includes('Plan catalog unavailable');
              scenarios.push({scenario:`portal ${failedPath} failure preserves identity and vehicles; retries only the failed section`,
                expected:{isolated:true,retried:true},actual:{isolated,retried,calls},passed:isolated && retried});
            } finally {
              root.unmount(); host.remove(); api.defaults.adapter = previousAdapter;
            }
          }
          return {scenarios, passed: scenarios.every(item => item.passed)};
        })()""")
        (RUN / "result.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps({"artifact":str(RUN / 'result.json'), **result}, ensure_ascii=False))
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
