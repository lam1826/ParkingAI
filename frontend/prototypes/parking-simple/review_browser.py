"""Browser checks for the standalone preview only. No backend/provider requests."""
import base64,json,shutil,socket,subprocess,time,urllib.request
from pathlib import Path
from uuid import uuid4
from websockets.sync.client import connect
ROOT=Path(__file__).resolve().parents[3]
OUT=ROOT/'backend/artifacts/simple-ui-demo/core-completion'/uuid4().hex[:10]
OUT.mkdir(parents=True)
PROFILE=(OUT/'chrome-profile').resolve()
checks=[];errors=[];requests=[];completed=False
with socket.socket() as channel:
    channel.bind(('127.0.0.1',0));port=channel.getsockname()[1]
log=(OUT/'browser.log').open('w',encoding='utf-8')
process=subprocess.Popen([r'C:\Program Files\Google\Chrome\Application\chrome.exe','--headless=new','--disable-gpu','--no-first-run','--no-default-browser-check','--disable-background-networking','--disable-component-update','--disable-sync','--remote-debugging-address=127.0.0.1',f'--remote-debugging-port={port}','--user-data-dir='+str(PROFILE),'about:blank'],stdout=log,stderr=log,creationflags=subprocess.CREATE_NO_WINDOW)
try:
    for _ in range(80):
        try:
            page=next(x for x in json.load(urllib.request.urlopen(f'http://127.0.0.1:{port}/json',timeout=1)) if x['type']=='page');break
        except (OSError,StopIteration):
            if process.poll() is not None: raise RuntimeError('Private Chrome did not start')
            time.sleep(.1)
    with connect(page['webSocketDebuggerUrl'],max_size=20_000_000) as ws:
        sequence=0
        def call(method,params=None):
            global sequence
            sequence+=1;wanted=sequence
            ws.send(json.dumps({'id':wanted,'method':method,'params':params or {}}))
            while True:
                result=json.loads(ws.recv(timeout=30))
                if result.get('method')=='Runtime.exceptionThrown':errors.append(result['params']['exceptionDetails'])
                if result.get('method')=='Network.requestWillBeSent':requests.append(result['params']['request']['url'])
                if result.get('id')==wanted:
                    if 'error' in result: raise RuntimeError(result['error'])
                    return result.get('result',{})
        def js(source):
            result=call('Runtime.evaluate',{'expression':source,'returnByValue':True,'awaitPromise':True})
            if 'exceptionDetails' in result: raise RuntimeError(result['exceptionDetails'])
            return result.get('result',{}).get('value')
        def check(name,source):
            passed=bool(js(source));checks.append({'name':name,'passed':passed});print(name,passed,flush=True)
            if not passed:raise AssertionError(name)
        def click(selector):js('document.querySelector('+json.dumps(selector)+').click()')
        def form(selector,values):
            js('(()=>{const f=document.querySelector('+json.dumps(selector)+');const v='+json.dumps(values)+';for(const [key,value]of Object.entries(v)){const n=f.elements.namedItem(key);if(!n)throw Error("Missing "+key);if(n.type==="checkbox")n.checked=Boolean(value);else n.value=value;}if(!f.checkValidity())throw Error("Invalid form "+[...f.elements].filter(n=>!n.checkValidity()).map(n=>n.name));f.requestSubmit();})()')
        def tab(name):click('[data-action="nav"][data-tab="'+name+'"]')
        def role(name):
            if name=='staff':click('[data-action="auth-quick"][data-role="staff"]')
            else:click('[data-action="role"][data-role="'+name+'"]')
        def sub(page,value):click('[data-action="core-tab"][data-page="'+page+'"][data-value="'+value+'"]')
        def core(kind,values):
            click('[data-action="core-open"][data-kind="'+kind+'"]');form('form[data-action="core-save"]',values)
        def shot(name,width=1440,height=1000):
            call('Emulation.setDeviceMetricsOverride',{'width':width,'height':height,'deviceScaleFactor':1,'mobile':width<600})
            js('window.scrollTo(0,0);document.getElementById("toast").hidden=true');time.sleep(.15)
            (OUT/(name+'.png')).write_bytes(base64.b64decode(call('Page.captureScreenshot',{'format':'png','captureBeyondViewport':False})['data']))
            check(name+' fits viewport','document.documentElement.scrollWidth<=innerWidth')
        call('Runtime.enable');call('Page.enable');call('Network.enable');call('Emulation.setFocusEmulationEnabled',{'enabled':True})
        call('Page.navigate',{'url':'http://127.0.0.1:8790/'})
        for _ in range(50):
            if js('!!window.ParkingDemo'):break
            time.sleep(.1)
        check('preview starts at login','!!document.querySelector("form[data-action=auth-login]")')
        click('[data-action="demo-guide"]')
        check('guide available before login','!!document.querySelector(".modal")')
        click('[data-action="close-modal"]')
        check('guide closes before login','!document.querySelector(".modal")')
        shot('login-desktop');shot('login-mobile',390,844)
        form('form[data-action="auth-login"]',{'username':'manager_demo','password':'wrong'})
        check('invalid login shows error','!!document.querySelector("[role=alert]")&&!ParkingDemo.ui.loggedIn')
        form('form[data-action="auth-login"]',{'username':'manager_demo','password':'demo123'})
        check('manager login and three primary actors','ParkingDemo.ui.role==="manager"&&document.querySelectorAll(".role-switch button").length===3')
        check('core menus visible','["operations","lot","history","customers","finance","catalog"].every(t=>document.querySelector(".nav-item[data-tab="+t+"]"))')
        tab('catalog');core('type',{'label':'Xe tải nhẹ','prefix':'E','rate':15000,'requiresPlate':True,'active':True})
        check('add vehicle category','ParkingDemo.state.vehicleTypes.some(t=>t.label==="Xe tải nhẹ")')
        custom=js('ParkingDemo.state.vehicleTypes.find(t=>t.label==="Xe tải nhẹ").id')
        check('new category starts without capacity','DemoEngine.available(ParkingDemo.state,'+json.dumps(custom)+')===0')
        tab('lot');sub('lot','zones');core('zone',{'name':'Khu thử E','vehicleType':custom,'capacity':3,'active':True})
        zone=js('ParkingDemo.state.zones.find(z=>z.name==="Khu thử E").id')
        check('add independent zone','!!ParkingDemo.state.zones.find(z=>z.name==="Khu thử E")')
        sub('lot','slots');core('slot',{'code':'E-01','zoneId':zone,'active':True})
        check('add named slot','DemoEngine.available(ParkingDemo.state,'+json.dumps(custom)+')===1')
        click('[data-action="core-open"][data-kind="slot"][data-id="E-01"]');form('form[data-action="core-save"]',{'active':False})
        check('inactive slot removes availability','DemoEngine.available(ParkingDemo.state,'+json.dumps(custom)+')===0')
        click('[data-action="core-open"][data-kind="slot"][data-id="E-01"]');form('form[data-action="core-save"]',{'active':True})
        shot('lot-desktop');shot('lot-mobile',390,844)
        tab('customers');sub('customers','customers');core('customer',{'name':'Khách thử UI','phone':'0900111222','email':'preview@example.test','active':True})
        customer=js('ParkingDemo.state.customers.find(c=>c.name==="Khách thử UI").id')
        check('create regular customer','!!ParkingDemo.state.customers.find(c=>c.name==="Khách thử UI")')
        sub('customers','vehicles');core('vehicle',{'customerId':customer,'plate':'51D-123.45','vehicleType':custom,'active':True})
        check('link customer vehicle','ParkingDemo.state.vehicles.some(v=>v.plate==="51D-123.45")')
        sub('customers','passes');core('pass',{'customerId':customer,'plate':'51D-123.45','vehicleType':custom,'startDate':'2026-09-23','endDate':'2026-10-22','price':450000,'active':True})
        check('issue monthly pass','ParkingDemo.state.monthlyPasses.some(p=>p.plate==="51D-123.45")')
        check('monthly issue creates receipt','ParkingDemo.state.transactions.some(t=>t.amount===450000)')
        pass_id=js('ParkingDemo.state.monthlyPasses.find(p=>p.plate==="51D-123.45").id')
        click('[data-action="core-open"][data-kind="renewal"][data-id="'+pass_id+'"]')
        form('form[data-action="core-save"]',{'startDate':'2026-10-23','endDate':'2026-11-22','price':450000})
        check('renewal preserves separate periods','ParkingDemo.state.monthlyPasses.filter(p=>p.plate==="51D-123.45").length===2')
        shot('monthly-desktop');shot('monthly-mobile',390,844)
        tab('operations');form('form[data-action="checkin"]',{'plate':'51D-123.45','vehicleType':custom})
        check('walk-in admitted without reservation','ParkingDemo.state.sessions.some(s=>s.plate==="51D-123.45"&&s.status==="active")')
        check('monthly fee applied','(()=>{let s=ParkingDemo.state.sessions.find(s=>s.plate==="51D-123.45");return DemoEngine.quote(ParkingDemo.state,s).gross===0&&!!s.monthlyPassId})()')
        check('admission consumes space','DemoEngine.available(ParkingDemo.state,'+json.dumps(custom)+')===0')
        form('form[data-action="checkin"]',{'plate':'51D-123.45','vehicleType':custom})
        check('duplicate entry rejected','ParkingDemo.state.sessions.filter(s=>s.plate==="51D-123.45"&&s.status==="active").length===1')
        click('[data-action="checkout"]')
        check('monthly checkout frees slot','DemoEngine.available(ParkingDemo.state,'+json.dumps(custom)+')===1')
        form('form[data-action="checkin"]',{'plate':'51D-543.21','vehicleType':custom})
        check('new walk-in hourly fee','DemoEngine.quote(ParkingDemo.state,ParkingDemo.state.sessions.find(s=>s.plate==="51D-543.21")).due===15000')
        click('[data-action="advance"]')
        check('elapsed time reflected','DemoEngine.quote(ParkingDemo.state,ParkingDemo.state.sessions.find(s=>s.plate==="51D-543.21")).minutes===60')
        click('[data-action="cash-pay"]');click('[data-action="confirm-pay"]');click('[data-action="checkout"]')
        check('cash payment plus exit','ParkingDemo.state.sessions.some(s=>s.plate==="51D-543.21"&&s.status==="closed"&&s.paid===15000)')
        tab('history');form('form[data-action="core-filter-history"]',{'query':'51D-543.21','from':'2026-09-23','to':'2026-09-23','status':'closed'})
        check('plate/date/status lookup','document.querySelectorAll("[data-action=core-detail]").length===1')
        click('[data-action="core-detail"]')
        check('history detail fee and elapsed','document.querySelector(".modal").textContent.includes("15.000")&&document.querySelector(".modal").textContent.includes("Giờ ra")')
        click('[data-action="core-close-detail"]')
        form('form[data-action="core-filter-history"]',{'from':'2026-09-24','to':'2026-09-22'})
        check('inverted history dates rejected','!!document.querySelector("[role=alert]")')
        click('[data-action="core-reset-history"]');shot('history-desktop');shot('history-mobile',390,844)
        tab('finance');click('[data-action="report-tab"][data-tab="flow"]');click('[data-action="report-period"][data-days="7"]')
        check('weekly traffic is displayed','document.querySelector("main").textContent.includes("Lượt vào")||document.querySelector("main").textContent.includes("lượt vào")')
        shot('traffic-desktop');shot('traffic-mobile',390,844)
        click('[data-action="report-tab"][data-tab="ai"]')
        for kind,period in [('report','day'),('report','week'),('question','week'),('staff','week')]:
            form('form[data-action="report-ai-generate"]',{'kind':kind,'period':period,'anchorDate':'2026-09-23','question':'Khung giờ nào đông nhất? Còn bao nhiêu chỗ?'})
            check('AI '+kind+' '+period+' saved','ParkingDemo.state.aiReports.length>0&&document.querySelector("main").textContent.includes("Kết quả đã lưu")')
        check('all AI kinds keep history','ParkingDemo.state.aiReports.filter(r=>r.role==="manager").length===4')
        form('form[data-action="report-ai-generate"]',{'kind':'report','period':'week','anchorDate':'2026-07-01','question':''})
        check('AI empty period disclosed','/không có|chưa có|chưa đủ/i.test(ParkingDemo.state.aiReports.at(-1)?.text||document.querySelector("main").textContent)')
        form('form[data-action="report-ai-generate"]',{'kind':'question','question':''})
        check('AI empty question rejected','!!document.querySelector("[role=alert]")')
        shot('ai-desktop');shot('ai-mobile',390,844)
        role('staff');check('staff operations available','ParkingDemo.ui.role==="staff"&&!!document.querySelector("form[data-action=checkin]")')
        check('staff no account/catalog management menu','!document.querySelector(".nav-item[data-tab=accounts]")&&!document.querySelector(".nav-item[data-tab=catalog]")')
        tab('lot');check('staff readonly inventory','!document.querySelector("[data-action=core-open]")')
        tab('customers');check('staff readonly customers','!document.querySelector("[data-action=core-open]")')
        tab('finance');check('staff finance tab unavailable','!document.querySelector("[data-action=report-tab][data-tab=money]")')
        click('[data-action="report-tab"][data-tab="ai"]')
        check('staff cannot view manager AI history','!document.querySelector("[data-action=report-ai-open]")')
        form('form[data-action="report-ai-generate"]',{'kind':'question','period':'day','anchorDate':'2026-09-23','question':'Doanh thu hôm nay bao nhiêu?'})
        check('staff financial question denied','/quyền|tài chính|doanh thu/i.test(document.querySelector("main").textContent)')
        role('customer');check('customer has no internal history route','!document.querySelector(".nav-item[data-tab=history]")')
        tab('tickets');check('customer sees own monthly periods','document.querySelector("main").textContent.includes("59A-888.88")')
        click('[data-action="chat-open"]');form('form[data-action="chat-send"]',{'question':'Còn bao nhiêu chỗ?'})
        check('customer chatbot answers capacity','/chỗ/i.test(document.querySelector(".bubble.assistant:last-child").textContent)')
        shot('customer-chat-mobile',390,844);click('[data-action="chat-close"]')
        role('admin');check('admin inherits manager screens','["operations","lot","history","customers","finance","catalog","accounts"].every(t=>document.querySelector(".nav-item[data-tab="+t+"]"))')
        tab('accounts');check('account management remains','document.querySelector("main").textContent.includes("staff_demo")')
        click('[data-action="auth-profile"]');form('form[data-action="auth-profile-save"]',{'name':'Admin thử giao diện','email':'admin@example.test'})
        check('personal profile editable','ParkingDemo.users.find(u=>u.id===ParkingDemo.ui.userId).name==="Admin thử giao diện"')
        click('[data-action="demo-guide"]');check('SDLC evidence visible','document.querySelector(".modal").textContent.includes("KT3")');click('[data-action="close-modal"]')
        click('[data-action="auth-logout"]');check('logout returns login','!ParkingDemo.ui.loggedIn&&!!document.querySelector("form[data-action=auth-login]")')
        check('no runtime errors',json.dumps(not errors))
        check('no API or provider calls',json.dumps(not any('/api/' in url or url.startswith('https:') for url in requests)))
        completed=True
finally:
    process.terminate()
    try:process.wait(timeout=8)
    except subprocess.TimeoutExpired:process.kill();process.wait(timeout=5)
    log.close()
    # Only remove the newly created private browser profile under this run.
    if PROFILE.parent==OUT.resolve() and OUT.resolve().is_relative_to((ROOT/'backend/artifacts/simple-ui-demo/core-completion').resolve()):
        shutil.rmtree(PROFILE,ignore_errors=True)
    (OUT/'result.json').write_text(json.dumps({'passed':completed,'checks':checks,'errors':errors,'scope':'Standalone prototype and generated demo data only','private_profile_removed':not PROFILE.exists()},ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({'passed':completed,'checks':len(checks),'output':str(OUT)},ensure_ascii=False),flush=True)
