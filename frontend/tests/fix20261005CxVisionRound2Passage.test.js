import test, { before, after } from "node:test";
import assert from "node:assert/strict";
import { spawn } from "node:child_process";
import { createServer as createHttpServer } from "node:http";
import { mkdtemp, readFile, rm } from "node:fs/promises";
import { existsSync } from "node:fs";
import { tmpdir } from "node:os";
import process from "node:process";
import { basename, join, relative, resolve } from "node:path";
import { createServer } from "vite";
import react from "@vitejs/plugin-react";


const frontend = resolve(import.meta.dirname, "..");
const delay = ms => new Promise(resolve => setTimeout(resolve, ms));
const chromePath = [process.env.CHROME_BINARY, process.env.CHROME_BIN, "C:/Program Files/Google/Chrome/Application/chrome.exe", "/usr/bin/google-chrome", "/usr/bin/chromium", "/usr/bin/chromium-browser", "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"].find(path => path && existsSync(path));
// The DevTools Protocol client needs a global WebSocket (Node >= 22); CI pins Node 20.
const uiSkip = !chromePath ? "Chrome unavailable; set CHROME_BINARY to run real UI regressions"
  : typeof WebSocket !== "function" ? "Node without a global WebSocket (needs Node >= 22); real-Chrome UI regression not run" : false;
const uiTest = (name, run) => test(name, { skip: uiSkip }, run);
let server, harnessServer, chrome, ws, scratch, evaluate;
const externalAttempts = [];
before(async () => {
  if (uiSkip) return;
  scratch = await mkdtemp(join(tmpdir(), "parkingai-cxvision-"));
  const blankHarness = { name: "isolated-camera-test", configureServer(vite) {
    vite.middlewares.use((request, response, next) => {
      if (request.url !== "/__cxvision_test") return next();
      response.setHeader("Content-Type", "text/html");
      response.end('<!doctype html><html><body><div id="root"></div></body></html>');
    });
  } };
  server = await createServer({ root: frontend, configFile: false, cacheDir: join(scratch, "vite"), plugins: [blankHarness, react()],
    server: { middlewareMode: true, hmr: false, ws: false }, logLevel: "error" });
  harnessServer = createHttpServer(server.middlewares);
  await new Promise(resolve => harnessServer.listen(0, "127.0.0.1", resolve));
  const vitePort = harnessServer.address().port;
  chrome = spawn(chromePath, ["--headless=new", "--no-sandbox", "--disable-gpu", "--no-first-run", "--disable-background-networking", "--disable-component-update", "--disable-sync", "--remote-debugging-port=0", `--user-data-dir=${join(scratch, "chrome")}`, "about:blank"], { stdio: "ignore" });
  let page;
  for (let i = 0; i < 100 && !page; i++) {
    try { const port = Number((await readFile(join(scratch, "chrome", "DevToolsActivePort"), "utf8")).split("\n")[0]); page = (await (await fetch(`http://127.0.0.1:${port}/json`)).json()).find(row => row.type === "page"); } catch { await delay(100); }
  }
  assert.ok(page, "local headless Chrome started");
  ws = new WebSocket(page.webSocketDebuggerUrl);
  await new Promise((resolve, reject) => { ws.onopen = resolve; ws.onerror = reject; });
  let sequence = 0;
  const pending = new Map();
  const viteOrigin = `http://127.0.0.1:${vitePort}`;
  ws.onmessage = event => {
    const result = JSON.parse(event.data);
    if (result.id) { pending.get(result.id)?.(result); pending.delete(result.id); }
    else if (result.method === "Fetch.requestPaused") {
      const { request, requestId } = result.params;
      const url = new URL(request.url);
      if (url.origin === viteOrigin || ["blob:", "data:"].includes(url.protocol)) void call("Fetch.continueRequest", { requestId });
      else { externalAttempts.push({ host: url.hostname, category: result.params.resourceType }); void call("Fetch.failRequest", { requestId, errorReason: "BlockedByClient" }); }
    }
  };
  const call = (method, params) => new Promise(resolve => { const id = ++sequence; pending.set(id, resolve); ws.send(JSON.stringify({ id, method, params })); });
  evaluate = async expression => {
    const response = await call("Runtime.evaluate", { expression, awaitPromise: true, returnByValue: true });
    if (response.result.exceptionDetails) throw new Error(JSON.stringify(response.result.exceptionDetails));
    return response.result.result.value;
  };
  await call("Fetch.enable", { patterns: [{ urlPattern: "*", requestStage: "Request" }] });
  await call("Page.navigate", { url: `${viteOrigin}/__cxvision_test` });
  for (let i = 0; i < 100; i++) { try { if (await evaluate("document.readyState === 'complete' && !!document.getElementById('root')")) break; } catch { /* navigation context */ } await delay(100); }
  await evaluate(`(async () => {
    const mainSource = await (await fetch('/src/main.jsx')).text();
    const sharedSource = await (await fetch('/src/pages/Expansion/shared.jsx')).text();
    const occupancySource = await (await fetch('/src/pages/Expansion/OccupancyPage.jsx')).text();
    const dependency = (source, name) => source.split('"').find(part => part.includes('/deps/' + name + '.js'));
    const reactModule = await import(dependency(sharedSource,'react'));
    const React = reactModule.default || reactModule;
    const domModule = await import(dependency(mainSource,'react-dom_client'));
    const {createRoot} = domModule.default || domModule;
    const routerModule = await import(dependency(occupancySource,'react-router-dom'));
    const {MemoryRouter} = routerModule.default || routerModule;
    const {AuthContext} = await import('/src/context/AuthContext.jsx');
    const {ExpansionProvider} = await import('/src/context/ExpansionContext.jsx');
    const {default:OccupancyPage} = await import('/src/pages/Expansion/OccupancyPage.jsx');
    const {default:VisionPage} = await import('/src/pages/Expansion/VisionPage.jsx');
    const {default:CameraOperations} = await import('/src/pages/Expansion/CameraOperations.jsx');
    const {default:api} = await import('/src/services/api.js');
    window.__PARKINGAI_CONFIG__ = {SINGLE_SITE_ID:null};
    window.__polls = new Map();window.__ticks=new Map();const setTimer=window.setTimeout.bind(window),clearTimer=window.clearTimeout.bind(window);window.setTimeout=(callback,ms,...args)=>{if(ms===4000){const id=Math.random();window.__ticks.set(id,callback);return id;}return setTimer(callback,ms,...args);};window.clearTimeout=id=>window.__ticks.delete(id)||clearTimer(id);
    const interval = window.setInterval.bind(window), clear = window.clearInterval.bind(window);
    let seq=100000;
    window.setInterval=(callback,ms,...args)=>{ if(ms===15000){const id=++seq; window.__polls.set(id,callback);return id;} return interval(callback,ms,...args); };
    window.clearInterval=id=>window.__polls.delete(id)||clear(id);
    document.getElementById('root').style.display='none';
    const host=document.createElement('main'); document.body.append(host); window.__host=host;
    window.__mode='ok'; window.__frames=[]; window.__posts=[]; window.__passages=[]; window.__requests=[];
    window.__retentionHours=24;window.__serverOffset=0;
    window.__reference={id:'reference-0001',site_id:10,camera_id:3,captured_at:new Date().toISOString(),observed_at:new Date(Date.now()-7200000).toISOString(),expires_at:new Date(Date.now()+3600000).toISOString()};
    api.defaults.adapter=async config=>{
      window.__requests.push({url:config.url,params:config.params});
      const ok=data=>({data,status:200,statusText:'OK',headers:{},config});
      const url=config.url;
      if(url.endsWith('/sites')) return ok([{id:10,name:'Site A',role:'manager'},{id:20,name:'Site B',role:'manager'}]);
      if(url.endsWith('/system/capabilities'))return ok({vision_enabled:true,occupancy_enabled:true});
      if(url.endsWith('/vision/status'))return ok({available:true});
      if(url.endsWith('/cameras')){const rows=[{id:1,site_id:10,name:'Retired entry',direction:'entry',is_active:false},{id:3,site_id:10,name:'Active entry',direction:'entry',is_active:true,edge_enabled:true,retention_hours:window.__retentionHours}];return ok(window.__kind==='occupancy'?rows.reverse():rows);}
      if(url.endsWith('/automation')) return ok({enabled:true,minimum_confidence:.99,max_age_seconds:15});
      if(url.endsWith('/image'))return ok(new Blob(['<svg xmlns="http://www.w3.org/2000/svg" width="100" height="100"/>'],{type:'image/svg+xml'}));
      if(url.endsWith('/occupancy/calibrations')){window.__posts.push(JSON.parse(config.data)); if(window.__mode==='post-fail')throw new Error('Network Error');return ok({version:1});}
      if(url.endsWith('/occupancy')) {if(window.__mode==='poll-fail')throw new Error('poll failed'); return ok({server_now:new Date(Date.now()+window.__serverOffset).toISOString(),readings:[],engine:{available:true}});}
      if(url.endsWith('/availability'))return ok({slots:[{id:11,slot_name:'A1',zone_name:'Zone'},{id:12,slot_name:'A2',zone_name:'Zone'}]});
      if(url.endsWith('/vision/observations'))return ok(window.__frames);
      if(url.endsWith('/process')){if(window.__deferProcess)return new Promise(resolve=>window.__resolveProcess=result=>resolve(ok(result)));const id=url.split('/').at(-2);return ok(window.__results?.[id]||{state:'already_entered',session_id:'other-car',license_plate:'51A99999'});}
      return ok([]);
    };
    window.__mount=async(kind,url='/occupancy')=>{
      window.__root?.unmount(); host.replaceChildren();window.__polls.clear();window.__ticks.clear();window.__kind=kind;
      const root=createRoot(host);window.__root=root;
      const component=kind==='occupancy'?React.createElement(OccupancyPage):kind==='vision'?React.createElement(VisionPage):React.createElement(CameraOperations,{site:{id:10,role:'manager'},onPassage:(result,options)=>window.__passages.push({result,options}),onCheckout:id=>window.__checkout=id});
      root.render(React.createElement(MemoryRouter,{initialEntries:[url]},React.createElement(AuthContext.Provider,{value:{user:{id:7,role:'manager'}}},React.createElement(ExpansionProvider,null,component))));
    };
    window.__wait=async predicate=>{for(let i=0;i<150;i++){if(predicate())return;await new Promise(r=>setTimeout(r,20));}throw new Error('UI condition timed out');};
    window.__section=()=>[...host.querySelectorAll('h2')].find(h=>h.textContent==='Cấu hình vùng chỗ đỗ')?.closest('section');
    window.__button=(text,scope=host)=>[...scope.querySelectorAll('button')].find(b=>b.textContent.startsWith(text));
    window.__select=async(label,prefix)=>{
      const control=[...host.querySelectorAll('[role="combobox"]')].find(el=>(el.getAttribute('aria-labelledby')||'').split(' ').some(id=>document.getElementById(id)?.textContent===label));
      control.dispatchEvent(new MouseEvent('mousedown',{bubbles:true,button:0}));
      await window.__wait(()=>[...document.querySelectorAll('[role="option"]')].some(o=>o.textContent.startsWith(prefix)));
      [...document.querySelectorAll('[role="option"]')].find(o=>o.textContent.startsWith(prefix)).click();
      await window.__wait(()=>!document.querySelector('[role="listbox"]'));
    };
    window.__input=async(label,value)=>{
      const lab=[...host.querySelectorAll('label')].find(el=>el.textContent===label);
      const input=document.getElementById(lab.htmlFor);
      Object.getOwnPropertyDescriptor(HTMLInputElement.prototype,'value').set.call(input,value);
      input.dispatchEvent(new Event('input',{bubbles:true}));await new Promise(r=>setTimeout(r,30));
    };
    window.__draw=async()=>{
      await window.__select('Ảnh nền trống','Chụp');await window.__select('Chỗ cần khoanh','A1');
      for(const [x,y] of [[.1,.1],[.3,.1],[.3,.3]]){await window.__input('Tọa độ X (0–1)',String(x));await window.__input('Tọa độ Y (0–1)',String(y));window.__button('Thêm đỉnh').click();await new Promise(r=>setTimeout(r,30));}
      window.__button('Thêm vùng').click();await window.__wait(()=>window.__section().querySelector('tbody tr'));
    };
    window.__autoTick=async()=>{const callbacks=[...window.__ticks.values()];window.__ticks.clear();for(const callback of callbacks)await callback();await new Promise(r=>setTimeout(r,100));};window.__poll=async()=>{for(const callback of window.__polls.values())callback();await new Promise(r=>setTimeout(r,150));};
  })()`);
});
after(async () => {
  if (!scratch) return;
  if (ws?.readyState === 1) { await evaluate("window.__root?.unmount()"); ws.close(); }
  chrome?.kill();
  harnessServer?.closeAllConnections();
  await new Promise(resolve => harnessServer ? harnessServer.close(resolve) : resolve());
  await server?.close();
  // Chrome can briefly hold its profile files after termination.
  const taskRelative = relative(resolve(tmpdir()), resolve(scratch));
  assert.ok(taskRelative && !taskRelative.startsWith("..") && basename(scratch).startsWith("parkingai-cxvision-"), "cleanup target stays inside the test temporary directory");
  await rm(scratch, { recursive: true, force: true, maxRetries: 10, retryDelay: 200 });
  assert.deepEqual(externalAttempts, [], "the isolated UI fixture attempted no external requests");
});

const start = `window.__passages=[];window.__frames=[];window.__results={};window.__deferProcess=false;window.__checkout=null;await window.__mount('camera','/sites');await window.__wait(()=>document.getElementById('camera-capture-source'));const source=document.getElementById('camera-capture-source');source.value='edge';source.dispatchEvent(new Event('change',{bubbles:true}));await new Promise(r=>setTimeout(r,50));`;
const frame = (id) => `({id:${JSON.stringify(id)},camera_id:3,capture_source:'edge',review_status:'pending',captured_at:new Date().toISOString(),observed_at:new Date().toISOString(),suggested_plate:'51A99999'})`;

uiTest("round2 #74 automated result supplies guarded selection metadata and always reconciles", async () => {
  const result = await evaluate(`(async()=>{${start}window.__frames=[${frame("frame-A")}];window.__results['frame-A']={state:'entered',session_id:'session-A',license_plate:'51A11111'};window.__button('Bật tự động').click();await window.__wait(()=>window.__passages.length);return window.__passages[0];})()`);
  assert.equal(result.options.updateSelection, false);
  assert.equal(result.options.automatic, true);
  assert.equal(result.options.allowSelection, true);
  assert.equal(result.options.cameraId, 3);
});

uiTest("round2 #74 entry fee button selects its own stay without an exit dialog after another passage", async () => {
  const result = await evaluate(`(async()=>{
    ${start}window.__frames=[${frame("frame-A")}];window.__results['frame-A']={state:'entered',session_id:'session-A',license_plate:'51A11111'};
    window.__button('Bật tự động').click();await window.__wait(()=>window.__passages.length);const ownButton=window.__button('Xem phí xe này');
    window.__frames=[${frame("frame-B")}];window.__results['frame-B']={state:'entered',session_id:'session-B',license_plate:'51A22222'};await window.__autoTick();
    const connected=ownButton.isConnected;ownButton.click();await new Promise(r=>setTimeout(r,30));
    return {connected,explicit:window.__passages.find(row=>row.options.explicit),checkout:window.__checkout};})()`);
  assert.equal(result.connected, true);
  assert.equal(result.explicit?.result.session_id, "session-A");
  assert.equal(result.explicit?.options.updateSelection, true);
  assert.equal(result.checkout, null);
});

uiTest("round2 #74 waiting-payment action remains bound to its own exit stay", async () => {
  const result = await evaluate(`(async()=>{
    ${start}window.__frames=[${frame("frame-A")}];window.__results['frame-A']={state:'waiting_payment',session_id:'session-A',license_plate:'51A11111'};
    window.__button('Bật tự động').click();await window.__wait(()=>window.__passages.length);const ownButton=window.__button('Xem phí & thanh toán');
    window.__frames=[${frame("frame-B")}];window.__results['frame-B']={state:'waiting_payment',session_id:'session-B',license_plate:'51A22222'};await window.__autoTick();
    const connected=ownButton.isConnected;ownButton.click();return {connected,checkout:window.__checkout};})()`);
  assert.deepEqual(result, { connected: true, checkout: "session-A" });
});

uiTest("round2 #74 late passage after Stop reconciles without allowing selection", async () => {
  const result = await evaluate(`(async()=>{
    ${start}window.__frames=[${frame("frame-A")}];window.__deferProcess=true;window.__resolveProcess=null;
    window.__button('Bật tự động').click();await window.__wait(()=>window.__resolveProcess);window.__button('Dừng tự động').click();await new Promise(r=>setTimeout(r,50));
    window.__resolveProcess({state:'entered',session_id:'session-A',license_plate:'51A11111'});await window.__wait(()=>window.__passages.length);
    const result=window.__passages[0];window.__deferProcess=false;return result;})()`);
  assert.equal(result.result.session_id, "session-A");
  assert.equal(result.options.updateSelection, false);
  assert.equal(result.options.allowSelection, false);
});
