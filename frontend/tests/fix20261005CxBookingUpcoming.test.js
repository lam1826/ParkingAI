import { Buffer } from "node:buffer";
import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {fileURLToPath} from 'node:url';
import path from 'node:path';
const frontend=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'..');
const {transformWithOxc}=await import('vite');
const moduleURL=source=>'data:text/javascript;base64,'+Buffer.from(source).toString('base64');
const reactURL=moduleURL(`export const Fragment=Symbol();export function createElement(type,props,...children){return {type,props:{...props,children:children.flat(Infinity)}}};export const useCallback=fn=>fn;export const useState=v=>[typeof v==='function'?v():v,()=>{}];export const useRef=v=>({current:v});export const useContext=()=>({});`);
const rows={reservations:[{id:31,license_plate:'30A12345',slot_name:'A1',site_name:'Lot',start_at:'2026-10-07T09:00:00+07:00',arrival_deadline:'2026-10-07T09:15:00+07:00',status:'confirmed'}],waitlist:[{id:45,license_plate:'30A67890',start_at:'2026-10-07T10:00:00+07:00',end_at:'2026-10-07T12:00:00+07:00',status:'waiting'},{id:46,license_plate:'30A12345',status:'offered'}]};
const miscURL=moduleURL(`export const sent=[];export const items=v=>Array.isArray(v)?v:v?.items||[];export const dateTime=v=>v;export const useRemote=load=>({data:${JSON.stringify(rows)},loading:false,error:'',reload:()=>{}});export const useAction=()=>({busy:false,run:async op=>op()});export const send=async path=>sent.push(path);export const read=()=>{};export const refreshAll=()=>{};export const requestKey=()=>'';export const usePage=()=>{};export const useSites=()=>{};export const nextBookingWindow=()=>{};export const advanceBookingBody=()=>{};export const uncertainMutation=()=>{};export const AuthContext={};export const Alert='alert',Button='button',Stack='div',Link='a',PageHeader='header',PrototypeIcon='i',PageControls='div',Records='div',RemoteSection='div',StateChip='span',SitePicker='div';`);
function walk(node,fn){if(!node||typeof node!=='object')return;if(Array.isArray(node))return node.forEach(x=>walk(x,fn));fn(node);(node.props?.children||[]).forEach(x=>walk(x,fn));}
const text=node=>node==null?'':typeof node!=='object'?String(node):(node.props?.children||[]).map(text).join('');
test('customer upcoming area shows operational offers and a waiting row with working cancellation',async()=>{
 const file=path.join(frontend,'src/pages/Expansion/ReservationsPage.jsx'),source=readFileSync(file,'utf8');
 assert.ok(source.includes('function UpcomingCommitments('),'current offers must be visible without opening history');
 const out=await transformWithOxc(source,file,{lang:'jsx',jsx:{runtime:'classic',pragma:'createElement',pragmaFrag:'Fragment'}});
 const code=`import {createElement,Fragment} from ${JSON.stringify(reactURL)};\n`+out.code.replace(/from\s+["']([^"']+)["']/g,(_,specifier)=>`from ${JSON.stringify(specifier==='react'?reactURL:miscURL)}`)+'\nexport { UpcomingCommitments };';
 const {UpcomingCommitments}=await import(moduleURL(code));
 const tree=UpcomingCommitments({siteId:1}),buttons=[];
 walk(tree,node=>{if(node.type==='button')buttons.push(node);});
 assert.ok(text(tree).includes('30A12345'));
 assert.ok(text(tree).includes('A1'));
 assert.ok(text(tree).includes('09:15'));
 assert.ok(text(tree).includes('30A67890'));
 const misc=await import(miscURL);
 for(const button of buttons)if(button.props.onClick)await button.props.onClick();
 assert.deepEqual(misc.sent.sort(),['/me/reservations/31/cancel','/me/waitlist/45/cancel','/me/waitlist/46/cancel']);
 // This section is mounted directly in upcoming, before collapsed history.
 assert.ok(source.indexOf('<UpcomingCommitments')<source.indexOf('<details'));
});
test('one-lot fleet UI removes the orphan account grant form',()=>{
 const source=readFileSync(path.join(frontend,'src/pages/Expansion/FleetSection.jsx'),'utf8');
 assert.ok(!source.includes('Mã tài khoản được xem nhóm'));
 assert.ok(!source.includes('Cấp quyền xem'));
 assert.ok(source.includes('Thêm xe vào nhóm'));
});
