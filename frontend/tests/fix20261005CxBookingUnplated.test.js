import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync, mkdtempSync, rmSync } from 'node:fs';
import { createRequire } from 'node:module';
import { pathToFileURL, fileURLToPath } from 'node:url';
import path from 'node:path';
import {tmpdir} from 'node:os';
import { admissionTypeId } from '../src/utils/admissionVehicleTypes.js';
const frontend = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const req = createRequire(path.join(frontend,'package.json'));
const React=req('react'), {renderToStaticMarkup}=req('react-dom/server');
const {createServer} = await import(pathToFileURL(path.join(frontend,'node_modules/vite/dist/node/index.js')).href);
const types=[{id:1,name:'Car',requires_plate:true,is_active:true},{id:2,name:'Bike',requires_plate:false,is_active:true}];
test('unplated legacy form permits a blank identifier; plated type still requires one',async()=>{
 const cacheDir=mkdtempSync(path.join(tmpdir(),'parkingai-cxbooking-'));
 const server=await createServer({configFile:false,root:frontend,cacheDir,logLevel:'error',appType:'custom',server:{middlewareMode:true,hmr:false,watch:null,ws:false},resolve:{dedupe:['react','react-dom']},optimizeDeps:{noDiscovery:true,include:[]}});
 try {
  const {default:Card}=await server.ssrLoadModule('/src/pages/ParkingSession/components/CheckInCard.jsx');
  for (const [typeId,expected] of [[1,true],[2,false]]) {
   const html=renderToStaticMarkup(React.createElement(Card,{licensePlate:'',vehicleTypeId:typeId,vehicleTypes:types,availableSlots:[],zones:[],zoneId:'',slotId:'',submitting:false}));
   const submit=html.match(/<button[^>]*type="submit"[^>]*>/)[0];
   assert.equal(/\sdisabled=""/.test(submit),expected);
   const input=html.match(/<input[^>]*value=""[^>]*>/)[0];
   assert.equal(/\srequired=""/.test(input),expected);
  }
 } finally { await server.close(); rmSync(cacheDir,{recursive:true,force:true}); }
});
test('blank unplated check-in reaches the backend to issue an identifier',async()=>{
 const source=readFileSync(path.join(frontend,'src/pages/ParkingSession/hooks/useParkingSession.js'),'utf8');
 const handler=source.slice(source.indexOf('  const handleCheckIn ='),source.indexOf('  const handleCheckoutCompleted ='));
 const noop=()=>{};
 const fields={licensePlate:'',vehicleTypes:types,vehicleTypeId:2,admissionTypeId,zoneId:'',slotId:'',showNotify:noop,setSubmitting:noop,setLicensePlate:noop,setSlotId:noop,fetchSessions:noop,fetchAvailableSlots:noop};
 const sent=[];
 fields.parkingSessionService={checkIn:async body=>{sent.push(body);return {session_id:'issued',slot_name:'A1'};}};
 const run=new Function(...Object.keys(fields),handler+';return handleCheckIn;')(...Object.values(fields));
 assert.equal(await run({preventDefault(){}}),'issued');
 assert.equal(sent[0].licensePlate,'');
});
