"""Scoped camera automatic-scan acceptance using simulated video, never hardware.

Baseline reads the real marked synthetic local server and never enables passage
policy or sends images. Regression mode is permitted only on a marked DB clone;
real OCR, injected transport failures and no-frame tests are reported separately.
"""
import argparse
import base64
from datetime import datetime
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

ROOT=Path(__file__).resolve().parents[3]
parser=argparse.ArgumentParser()
parser.add_argument("--credentials",type=Path,required=True)
parser.add_argument("--origin",default="http://127.0.0.1:8793")
parser.add_argument("--mode",choices=("baseline","regression"),default="baseline")
parser.add_argument("--case-filter",default="",help="Run only independently prepared regression cases whose names contain this text")
args=parser.parse_args()
credentials=json.loads(args.credentials.read_text(encoding="utf-8"))
marker=json.loads(Path(credentials["database"]+".demo.json").read_text(encoding="utf-8"))
if credentials.get("profile")!="single-lot-academic-v1" or marker.get("synthetic_history") is not True:
    raise ValueError("Explicit synthetic database required")
origin=urllib.parse.urlsplit(args.origin)
if origin.hostname!="127.0.0.1" or origin.scheme!="http":raise ValueError("Loopback HTTP only")
if args.mode=="regression" and (origin.port==8793 or marker.get("camera_auto_uat_clone") is not True):
    raise ValueError("Regression requires an isolated marked clone, never shared8793")
BASE=ROOT/"backend/artifacts/camera-auto-uat"
OUT=BASE/uuid4().hex[:10]
OUT.mkdir(parents=True)
PROFILE=OUT/"chrome-profile"
print(json.dumps({"artifacts":str(OUT),"mode":args.mode,"origin":args.origin},ensure_ascii=True),flush=True)
checks,writes,failures,errors,screenshots,states=[],[],[],[],[],[]
responses=[]
injection={"kind":None,"remaining":0,"count":0}
injected_network_ids=set()
held_process=[]
fixture_data=base64.b64encode((ROOT/"backend/artifacts/vision/rolls-royce-cc0.jpg").read_bytes()).decode()
complete=False
current="startup"
with socket.socket() as sock:
    sock.bind(("127.0.0.1",0));port=sock.getsockname()[1]
log=(OUT/"browser.log").open("w",encoding="utf-8")
chrome=subprocess.Popen([r"C:\Program Files\Google\Chrome\Application\chrome.exe","--headless=new","--disable-gpu","--no-first-run","--no-default-browser-check","--disable-background-networking","--disable-component-update","--disable-sync","--remote-debugging-address=127.0.0.1",f"--remote-debugging-port={port}","--user-data-dir="+str(PROFILE),"about:blank"],stdout=log,stderr=log,creationflags=subprocess.CREATE_NO_WINDOW)
try:
    for _ in range(100):
        try:
            page=next(r for r in json.load(urllib.request.urlopen(f"http://127.0.0.1:{port}/json",timeout=1)) if r["type"]=="page");break
        except (OSError,StopIteration):time.sleep(.1)
    else:raise RuntimeError("Private browser did not start")
    with connect(page["webSocketDebuggerUrl"],max_size=20_000_000) as ws:
        sequence=0
        def call(method,params=None):
            global sequence
            sequence+=1;wanted=sequence
            ws.send(json.dumps({"id":wanted,"method":method,"params":params or {}}))
            while True:
                response=json.loads(ws.recv(timeout=150));event=response.get("method");payload=response.get("params",{})
                if event=="Fetch.requestPaused":
                    req=payload["request"];url=urllib.parse.urlsplit(req["url"])
                    local=url.netloc==origin.netloc
                    allowed=url.scheme in {"data","blob","about"} or local and (req["method"] in {"GET","HEAD"} or req["method"]=="POST" and url.path=="/api/auth/login")
                    is_policy=url.path.startswith("/api/v2/cameras/") and url.path.endswith("/automation")
                    if args.mode=="regression" and local:
                        allowed=allowed or req["method"]=="PUT" and is_policy or req["method"]=="POST" and (url.path=="/api/v2/vision/live-frames" or url.path.startswith("/api/v2/vision/observations/") and url.path.endswith("/process"))
                    injected=local and injection["remaining"]>0 and ((injection["kind"]=="policy-put" and is_policy and req["method"]=="PUT") or (injection["kind"]=="policy-read" and is_policy and req["method"]=="GET") or (injection["kind"]=="frame" and url.path=="/api/v2/vision/live-frames" and req["method"]=="POST"))
                    hold=local and injection["kind"]=="process-hold" and injection["remaining"]>0 and req["method"]=="POST" and url.path.startswith("/api/v2/vision/observations/") and url.path.endswith("/process")
                    if local and req["method"] not in {"GET","HEAD"}:
                        write={"case":current,"method":req["method"],"path":url.path,"allowed":allowed,"injected_failure":injected,"held_mock_response":hold}
                        if is_policy and req.get("postData"):
                            body=json.loads(req["postData"]);write["policy_fields"]={k:body.get(k) for k in ("enabled","minimum_confidence","max_age_seconds")}
                        writes.append(write)
                    sequence+=1
                    if hold:
                        injection["remaining"]-=1
                        held_process.append({"request_id":payload["requestId"],"network_id":payload.get("networkId"),"path":url.path})
                    elif injected:
                        injection["remaining"]-=1;injection["count"]+=1
                        if payload.get("networkId"):injected_network_ids.add(payload["networkId"])
                        body=json.dumps({"detail":"UAT injected "+injection["kind"]+" failure; no real provider result."}).encode()
                        ws.send(json.dumps({"id":sequence,"method":"Fetch.fulfillRequest","params":{"requestId":payload["requestId"],"responseCode":503,"responseHeaders":[{"name":"Content-Type","value":"application/json"}],"body":base64.b64encode(body).decode()}}))
                    else:
                        ws.send(json.dumps({"id":sequence,"method":"Fetch.continueRequest" if allowed else "Fetch.failRequest","params":{"requestId":payload["requestId"],**({} if allowed else {"errorReason":"BlockedByClient"})}}))
                if event=="Runtime.exceptionThrown":errors.append({"case":current,"kind":"runtime","text":payload["exceptionDetails"]["text"]})
                if event=="Network.responseReceived":
                    r=payload["response"];path=urllib.parse.urlsplit(r["url"]).path
                    if path.startswith("/api/"):responses.append({"case":current,"path":path,"status":r["status"],"request_id":payload["requestId"]})
                    if r["status"]>=400 and path.startswith("/api/"):failures.append({"case":current,"path":path,"status":r["status"],"request_id":payload["requestId"],"expected_injected":r["status"]==503 and payload["requestId"] in injected_network_ids})
                if response.get("id")==wanted:
                    if "error" in response:raise RuntimeError("Browser command failed: "+method)
                    return response.get("result",{})
        def js(source):
            value=call("Runtime.evaluate",{"expression":source,"returnByValue":True,"awaitPromise":True})
            if "exceptionDetails" in value:raise RuntimeError("Browser expression failed; private inputs withheld")
            return value.get("result",{}).get("value")
        def wait(source,seconds=15):
            until=time.monotonic()+seconds
            while time.monotonic()<until:
                if js(source):return True
                time.sleep(.1)
            return False
        def record(label,passed,**evidence):checks.append({"case":current,"check":label,"status":"PASS" if passed else "FAIL",**evidence});return passed
        def require(label,source,seconds=15):
            if not record(label,wait(source,seconds)):raise AssertionError(label)
        def button(label):return "[...document.querySelectorAll('main button')].find(e=>e.textContent.trim()==="+json.dumps(label)+")"
        def click(label):
            if not wait("!!"+button(label)+"&&!"+button(label)+".disabled"):raise AssertionError("Button unavailable: "+label)
            js(button(label)+".click()")
        def fill(selector,value):
            js("(()=>{const e=document.querySelector("+json.dumps(selector)+");Object.getOwnPropertyDescriptor(HTMLInputElement.prototype,'value').set.call(e,"+json.dumps(value)+");e.dispatchEvent(new Event('input',{bubbles:true}))})()")
        def api(path,body=None,method="GET"):
            return js("fetch("+json.dumps('/api/v2'+path)+",{method:"+json.dumps(method)+",headers:{Authorization:'Bearer '+localStorage.getItem('token'),'Content-Type':'application/json'},"+("body:"+json.dumps(json.dumps(body))+"," if body is not None else "")+"}).then(async r=>({status:r.status,data:await r.json()}))")
        def login(role):
            call("Storage.clearDataForOrigin",{"origin":args.origin,"storageTypes":"all"})
            call("Page.navigate",{"url":args.origin+"/login"});require("login form","!!document.querySelector('#password')")
            fill("#username",role+"_demo");fill("#password",credentials["accounts"][role+"_demo"])
            js("document.querySelector('button[type=submit]').click()")
            require("real role authenticated","location.pathname!=='/login'&&!!document.querySelector('main')")
            call("Page.navigate",{"url":args.origin+"/sites"});require("operations camera mode","!!"+button("Camera"));click("Camera")
            require("camera controls loaded","!!document.querySelector('video')&&!!document.querySelector('#operation-camera')")
        def feed(kind="positive"):
            if kind=="denied":
                js("navigator.mediaDevices.getUserMedia=async()=>{throw new DOMException('UAT denied simulated camera','NotAllowedError')}")
            elif kind=="no-frame":
                js("window.uatStream=new MediaStream();navigator.mediaDevices.getUserMedia=async()=>window.uatStream")
            elif kind=="positive":
                js("""(async()=>{const img=new Image();img.src='data:image/jpeg;base64,"""+fixture_data+"""';await img.decode();const c=document.createElement('canvas');c.width=img.width;c.height=img.height;const x=c.getContext('2d');x.drawImage(img,0,0);window.uatCanvas=c;window.uatStream=c.captureStream(5);window.uatTimer=setInterval(()=>x.drawImage(img,0,0),200);navigator.mediaDevices.getUserMedia=async()=>window.uatStream})()""")
            else:
                js("""(()=>{const c=document.createElement('canvas');c.width=1280;c.height=720;const x=c.getContext('2d');x.fillStyle='#8899aa';x.fillRect(0,0,1280,720);window.uatCanvas=c;window.uatStream=c.captureStream(5);window.uatTimer=setInterval(()=>x.drawImage(c,0,0),200);navigator.mediaDevices.getUserMedia=async()=>window.uatStream})()""")
        def snapshot(label):
            row=js("({buttons:[...document.querySelectorAll('.camera-controls button')].map(e=>({label:e.textContent.trim(),disabled:e.disabled})),video:{ready:document.querySelector('video').readyState,width:document.querySelector('video').videoWidth,height:document.querySelector('video').videoHeight},hint:document.querySelector('#camera-automation-hint')?.textContent,settingsOpen:document.querySelector('#operation-camera')?.closest('details')?.open,permissionCheckbox:!!document.querySelector('#operation-camera')?.closest('details')?.querySelector('input[type=checkbox]')})")
            row.update(label=label,role=current);states.append(row);return row
        def shot(name,mobile=False):
            call("Emulation.setDeviceMetricsOverride",{"width":390 if mobile else 1440,"height":844 if mobile else 1000,"deviceScaleFactor":1,"mobile":mobile})
            js("document.querySelector('.camera-controls').scrollIntoView({block:'center'});new Promise(r=>setTimeout(r,150))")
            (OUT/(name+".png")).write_bytes(base64.b64decode(call("Page.captureScreenshot",{"format":"png","captureBeyondViewport":False})["data"]));screenshots.append(name+".png")
        def run_case(label,action):
            global current
            if args.case_filter and args.case_filter not in label:return
            current=label;begin=len(checks)
            try:action()
            except Exception as failure:
                record("case completed",False,reason=type(failure).__name__+": "+str(failure))
                try:snapshot("failure");shot("failed-"+str(len(checks)))
                except Exception:pass
            finally:
                injection.update(kind=None,remaining=0)
                js("window.uatStream?.getTracks().forEach(t=>t.stop());clearInterval(window.uatTimer);delete document.visibilityState")
            print(json.dumps({"case":label,"pass":sum(r["status"]=="PASS" for r in checks[begin:]),"fail":sum(r["status"]=="FAIL" for r in checks[begin:])},ensure_ascii=True),flush=True)
        def pump(milliseconds):js("new Promise(resolve=>setTimeout(resolve,"+str(milliseconds)+"))")
        def frame_count():return len([r for r in writes if r["path"]=="/api/v2/vision/live-frames"])
        def session_count():
            count=0
            while True:
                value=api("/sites/1/sessions?limit=100&offset="+str(count))
                if value["status"]!=200 or not isinstance(value["data"],list):raise AssertionError("Session inventory failed")
                count+=len(value["data"])
                if len(value["data"])<100:return count
        def configure_disabled():
            # Stricter fixture thresholds ensure the button never lowers policy.
            value=api("/cameras/1/automation",{"enabled":False,"minimum_confidence":.99,"max_age_seconds":12},"PUT")
            if value["status"]!=200:raise AssertionError("Clone policy fixture could not be prepared")
            call("Page.navigate",{"url":args.origin+"/sites"});require("camera switch after fixture reset","!!"+button("Camera"));click("Camera")
            require("clone camera ready","!!document.querySelector('#operation-camera')")
            require("policy loaded for fixture","!!document.querySelector('#camera-automation-hint')")
        for method in ("Page.enable","Runtime.enable","Network.enable"):call(method)
        call("Fetch.enable",{"patterns":[{"urlPattern":"*"}]})
        call("Emulation.setFocusEmulationEnabled",{"enabled":True})
        call("Emulation.setDeviceMetricsOverride",{"width":1440,"height":1000,"deviceScaleFactor":1,"mobile":False})
        if args.mode=="baseline":
            for role in ("manager","admin","staff"):
                current=role;login(role)
                camera_id=js("document.querySelector('#operation-camera').value")
                camera_rows=api("/cameras?site_id=1")["data"]
                camera_rows=camera_rows if isinstance(camera_rows,list) else camera_rows.get("items",[])
                camera=next(r for r in camera_rows if str(r["id"])==str(camera_id))
                before=api("/cameras/"+str(camera_id)+"/automation")["data"]
                engine=api("/vision/status")["data"]
                states.append({"role":role,"camera":{"id":camera["id"],"is_active":camera["is_active"],"direction":camera["direction"],"edge_enabled":camera.get("edge_enabled")},"policy":before,"engine":{k:v for k,v in engine.items() if k in {"engine","available","reason"}}})
                initial=snapshot("before-webcam")
                expected_available=role in {"manager","admin"} or before.get("enabled") is True
                record("automatic start available before opening camera according to role",js("!!"+button("Bật tự động")+"&&!"+button("Bật tự động")+".disabled")==expected_available,expected_available=expected_available,actual=initial)
                feed("synthetic-blank");click("Dùng webcam")
                require("simulated camera has ready frames","document.querySelector('video').readyState>=2&&document.querySelector('video').videoWidth>0")
                after=snapshot("ready-video-policy-unchanged")
                expected_available=role in {"manager","admin"} or before.get("enabled") is True
                actual_available=js("!!"+button("Bật tự động")+"&&!"+button("Bật tự động")+".disabled")
                record("automatic start availability follows role and policy",actual_available==expected_available,expected_available=expected_available,actual=after)
                record("one-shot OCR remains available",js("!!"+button("Quét biển số")+"&&!"+button("Quét biển số")+".disabled"))
                shot(role+"-auto-controls");shot(role+"-auto-controls-mobile",True)
                click("Tắt webcam")
                record("simulated track stopped",js("window.uatStream.getTracks().every(t=>t.readyState==='ended')"))
                record("policy unchanged",api("/cameras/"+str(camera_id)+"/automation")["data"]==before)
                print(json.dumps({"role":role,"policy_enabled":before.get("enabled"),"video_ready":after["video"]["ready"],"automation_button":next((b for b in after["buttons"] if b["label"]=="Bật tự động"),None)},ensure_ascii=True),flush=True)
        else:
            current="fixture setup";login("manager");configure_disabled()
            baseline_sessions=session_count()
            before_passages=api("/vision/passages?site_id=1&limit=100")["data"]
            def staff_disabled():
                login("staff");feed()
                record("staff cannot enable manager policy",js("!!"+button("Bật tự động")+"&&"+button("Bật tự động")+".disabled"))
                record("staff sees visible manager-permission explanation",js("/Admin.*Manager/.test(document.querySelector('#camera-automation-hint')?.textContent)"))
                record("staff has no editable policy checkbox",js("!document.querySelector('#operation-camera').closest('details').querySelector('input[type=checkbox]')"))
                shot("staff-policy-off")
            run_case("staff policy off",staff_disabled)
            def automatic_start_stop():
                login("manager");feed()
                require("manager can start with policy off and webcam closed","!!"+button("Bật tự động")+"&&!"+button("Bật tự động")+".disabled")
                put_before=len([r for r in writes if r["method"]=="PUT"])
                click("Bật tự động")
                require("one click opens ready webcam","document.querySelector('video').readyState>=2&&document.querySelector('video').videoWidth>0",seconds=25)
                require("automatic running has an enabled stop control","!!"+button("Dừng tự động")+"&&!"+button("Dừng tự động")+".disabled",seconds=25)
                policy=api("/cameras/1/automation")["data"]
                record("start enables clone policy without weakening thresholds",policy["enabled"] is True and policy["minimum_confidence"]==.99 and policy["max_age_seconds"]==12,policy=policy)
                record("exactly one enable policy request",len([r for r in writes if r["method"]=="PUT"])==put_before+1)
                require("real live OCR result is rendered","!!document.querySelector('[data-camera-ocr-status]')",seconds=40)
                require("real processing yields manual review for weak sample","document.querySelector('.camera-result')?.textContent.includes('Cần kiểm tra')",seconds=25)
                observations=api("/vision/observations?site_id=1&limit=25")["data"]
                observations=observations if isinstance(observations,list) else observations.get("items",[])
                real=next(r for r in observations if r.get("capture_source")=="live_camera")
                record("real fixture confidence remains below policy",real["confidence"]<.99 and real["ocr_status"]=="recognized",ocr={k:real.get(k) for k in ("id","capture_source","ocr_status","suggested_plate","confidence")},fixture="rolls-royce-cc0.jpg; simulated video, real OCR")
                record("processed live frame was captured after policy enabled",datetime.fromisoformat(real["captured_at"].replace("Z","+00:00"))>=datetime.fromisoformat(policy["enabled_at"].replace("Z","+00:00")),captured_at=real["captured_at"],enabled_at=policy["enabled_at"])
                record("manual result never claims entry",not js("document.querySelector('.camera-result')?.textContent.includes('Đã nhận xe')"))
                shot("manager-automatic-real-manual")
                shot("manager-automatic-real-manual-mobile",True)
                click("Dừng tự động")
                require("stop returns start control","!!"+button("Bật tự động"))
                pump(800);stopped_count=frame_count();pump(4500)
                record("stop prevents subsequent frame submission",frame_count()==stopped_count)
                put_before=len([r for r in writes if r["method"]=="PUT"])
                click("Bật tự động");require("resume uses already permitted policy","!!"+button("Dừng tự động"))
                pump(1200)
                record("resume does not issue another policy mutation",len([r for r in writes if r["method"]=="PUT"])==put_before)
                js("Object.defineProperty(document,'visibilityState',{configurable:true,get:()=> 'hidden'})")
                pump(1000);hidden_count=frame_count();pump(4500)
                record("controlled hidden-tab state pauses new frames",frame_count()==hidden_count,simulation="document.visibilityState getter; not physical tab/hardware acceptance")
                js("delete document.visibilityState")
                until=time.monotonic()+8
                while frame_count()<=hidden_count and time.monotonic()<until:pump(200)
                record("visible tab resumes automatic frames",frame_count()>hidden_count)
                click("Dừng tự động")
                record("stop remains available after repeated scans",js("!!"+button("Bật tự động")))
            run_case("manager one-click automatic start real OCR stop resume visibility",automatic_start_stop)
            def staff_permitted():
                login("staff");feed()
                require("staff can start when manager policy already enabled","!!"+button("Bật tự động")+"&&!"+button("Bật tự động")+".disabled")
                put_before=len([r for r in writes if r["method"]=="PUT"])
                click("Bật tự động");require("permitted staff reaches stop control","!!"+button("Dừng tự động"),seconds=25)
                record("staff start makes no manager policy write",len([r for r in writes if r["method"]=="PUT"])==put_before)
                click("Dừng tự động")
            run_case("staff manager-permitted start",staff_permitted)
            def permission_denied():
                login("manager");configure_disabled();feed("denied")
                click("Bật tự động")
                require("camera denial produces visible actionable error","[...document.querySelectorAll('main [role=alert]')].some(e=>/webcam|camera|quyền/i.test(e.textContent))")
                record("camera denial does not claim running",js("!"+button("Dừng tự động")))
                record("camera denial leaves policy off",api("/cameras/1/automation")["data"]["enabled"] is False)
                shot("permission-denied")
            run_case("simulated permission denied",permission_denied)
            def no_frame():
                login("manager");configure_disabled();feed("no-frame")
                click("Bật tự động")
                require("empty stream exits start with clear failure","[...document.querySelectorAll('main [role=alert]')].some(e=>/hình|camera|webcam/i.test(e.textContent))",seconds=30)
                record("no-frame stream never claims running",js("!"+button("Dừng tự động")))
                record("no-frame start leaves policy off",api("/cameras/1/automation")["data"]["enabled"] is False)
                record("no-frame start does not upload empty image",not any(r["case"]==current and r["path"]=="/api/v2/vision/live-frames" for r in writes))
                shot("no-video-frame")
            run_case("simulated stream with no frames",no_frame)
            def failed_policy_put():
                login("manager");configure_disabled();feed()
                injection.update(kind="policy-put",remaining=1)
                click("Bật tự động")
                require("policy-save failure shown explicitly","document.querySelector('main').innerText.includes('UAT injected policy-put failure')",seconds=25)
                record("failed policy save does not claim running",js("!"+button("Dừng tự động")))
                record("failed policy save remains disabled on server",api("/cameras/1/automation")["data"]["enabled"] is False)
                record("failed policy save causes no live frame",not any(r["case"]==current and r["path"]=="/api/v2/vision/live-frames" for r in writes))
                shot("policy-save-error")
            run_case("injected policy-save failure",failed_policy_put)
            def failed_policy_read():
                login("manager");configure_disabled();feed()
                injection.update(kind="policy-read",remaining=1)
                call("Page.navigate",{"url":args.origin+"/sites"});require("camera switch before read failure","!!"+button("Camera"));click("Camera")
                require("policy-read failure visible","document.querySelector('main').innerText.includes('UAT injected policy-read failure')")
                record("policy-read failure blocks automatic start",js("!!"+button("Bật tự động")+"&&"+button("Bật tự động")+".disabled"))
                record("policy-read failure never claims running",js("!"+button("Dừng tự động")))
                shot("policy-read-error")
            run_case("injected policy-read failure",failed_policy_read)
            def failed_policy_confirmation():
                login("manager");configure_disabled();feed()
                injection.update(kind="policy-read",remaining=1)
                click("Bật tự động")
                require("confirmation-read failure shown explicitly","document.querySelector('main').innerText.includes('UAT injected policy-read failure')",seconds=25)
                record("failed confirmation never claims running",js("!"+button("Dừng tự động")))
                record("failed confirmation sends no live frames",not any(r["case"]==current and r["path"]=="/api/v2/vision/live-frames" for r in writes))
                record("policy PUT succeeded before confirmation failed",api("/cameras/1/automation")["data"]["enabled"] is True)
                shot("policy-confirmation-error")
                click("Thử lại")
                require("retry reload recovers available start","!!"+button("Bật tự động")+"&&!"+button("Bật tự động")+".disabled")
                put_before=len([r for r in writes if r["method"]=="PUT"])
                click("Bật tự động");require("recovered confirmed policy starts automatic","!!"+button("Dừng tự động"),seconds=25)
                record("recovery does not duplicate enabled policy write",len([r for r in writes if r["method"]=="PUT"])==put_before)
                click("Dừng tự động")
            run_case("injected post-PUT policy-confirmation failure",failed_policy_confirmation)
            def failed_frame():
                login("manager");configure_disabled();feed()
                injection.update(kind="frame",remaining=1)
                click("Bật tự động")
                require("live-frame error shown without fabricated OCR","document.querySelector('main').innerText.includes('UAT injected frame failure')",seconds=25)
                record("live-frame error retains enabled stop",js("!!"+button("Dừng tự động")+"&&!"+button("Dừng tự động")+".disabled"))
                record("live-frame error never claims entry",not js("document.querySelector('.camera-result')?.textContent.includes('Đã nhận xe')"))
                click("Dừng tự động");pump(800);count=frame_count();pump(4500)
                record("stop after frame failure prevents retries",frame_count()==count)
                shot("live-frame-error-stopped")
            run_case("injected live-frame failure",failed_frame)
            def delayed_completed_passage():
                login("manager");configure_disabled();feed()
                held_process.clear();injection.update(kind="process-hold",remaining=1)
                click("Bật tự động")
                until=time.monotonic()+35
                while not held_process and time.monotonic()<until:pump(100)
                record("process request held before server execution",len(held_process)==1,controlled_mock=True)
                if not held_process:raise AssertionError("Automatic process did not reach controlled pause")
                require("stop enabled while process response pending","!!"+button("Dừng tự động")+"&&!"+button("Dừng tự động")+".disabled")
                click("Dừng tự động");pump(400)
                require("stop changes control before response release","!!"+button("Bật tự động"))
                stopped_frames=frame_count()
                before_reads=len(responses)
                body=json.dumps({"state":"entered","session_id":"UAT-MOCK-NO-REAL-ADMISSION","license_plate":"UAT-MOCK-NO-REAL-ADMISSION"}).encode()
                call("Fetch.fulfillRequest",{"requestId":held_process[0]["request_id"],"responseCode":200,"responseHeaders":[{"name":"Content-Type","value":"application/json"}],"body":base64.b64encode(body).decode()})
                until=time.monotonic()+10
                required_paths={"/api/v2/sites/1/sessions","/api/v2/sites/1/availability"}
                while not required_paths.issubset({r["path"] for r in responses[before_reads:]}) and time.monotonic()<until:pump(100)
                refreshed=[r for r in responses[before_reads:] if r["path"] in required_paths]
                record("completed response after stop refreshes sessions and availability",required_paths.issubset({r["path"] for r in refreshed}) and all(r["status"]==200 for r in refreshed),controlled_mock=True,refresh_responses=refreshed)
                record("late result does not select fabricated session",not js("document.querySelector('main').innerText.includes('UAT-MOCK-NO-REAL-ADMISSION')"),controlled_mock=True)
                pump(4500)
                record("late completed response does not restart frame loop",frame_count()==stopped_frames)
                record("late response leaves automation stopped",js("!!"+button("Bật tự động")+"&&!"+button("Dừng tự động")))
                shot("mock-late-process-after-stop")
            run_case("controlled mock delayed process after stop",delayed_completed_passage)
            current="final clone invariants";login("manager")
            final_sessions=session_count()
            passages=api("/vision/passages?site_id=1&limit=100")["data"]
            previous_ids={r["id"] for r in before_passages}
            new_passages=[r for r in passages if r["id"] not in previous_ids]
            record("real low-confidence fixtures admit no vehicle",final_sessions==baseline_sessions and all(r["state"] not in {"entered","exited"} for r in new_passages),session_count_before=baseline_sessions,session_count_after=final_sessions,passage_states=[r["state"] for r in new_passages])
            record("no policy admission checkout bank or AI writes escaped clone boundary",all(r["allowed"] for r in writes))
            checks.append({"case":"limits","check":"physical camera accuracy and automatic admission on high-confidence vehicle","status":"NOT_RUN","reason":"Simulated video with real low-confidence OCR; backend automatic-entry contract tested separately; no threshold lowered or mock success called real"})
        complete=True
except Exception as error:
    errors.append({"case":current,"kind":"harness","text":str(error)})
finally:
    chrome.terminate()
    try:chrome.wait(timeout=5)
    except subprocess.TimeoutExpired:chrome.kill();chrome.wait(timeout=5)
    log.close()
    if PROFILE.resolve().parent==OUT.resolve() and OUT.resolve().is_relative_to(BASE.resolve()):
        for _ in range(30):
            try:shutil.rmtree(PROFILE);break
            except FileNotFoundError:break
            except PermissionError:time.sleep(.1)
    report={"batch_completed":complete,"mode":args.mode,"case_filter":args.case_filter,"origin":args.origin,"simulated_video":True,"physical_device_tested":False,"checks":checks,"states":states,"writes":writes,"api_failures":failures,"injected_network_ids":sorted(injected_network_ids),"unexpected_api_failures":[r for r in failures if not r.get("expected_injected")],"errors":errors,"screenshots":screenshots,"private_profile_removed":not PROFILE.exists()}
    (OUT/"result.json").write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding="utf-8")
    print(json.dumps({"artifacts":str(OUT),"completed":complete,"pass":sum(r["status"]=="PASS" for r in checks),"fail":sum(r["status"]=="FAIL" for r in checks)},ensure_ascii=True),flush=True)
raise SystemExit(0 if complete and not any(r["status"]=="FAIL" for r in checks) and not errors and not any(not r.get("expected_injected") for r in failures) else 1)
