import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {transformWithOxc} from 'vite';
const path=new URL('../src/pages/Expansion/siteComponents.jsx',import.meta.url);
const source=readFileSync(path,'utf8');
const components=source.slice(source.indexOf('export function BookingRecords')).replaceAll('export function','function');
const {code}=await transformWithOxc(components,'siteComponents.jsx',{lang:'jsx',jsx:{runtime:'classic',pragma:'createElement',pragmaFrag:'Fragment'}});
const createElement=(type,props,...children)=>({type,props:{...props,children:children.flat(Infinity)}});
const {BookingRecords,WaitlistRecords}=new Function('createElement','Records','Stack','Button','StateChip','dateTime',code+';return {BookingRecords,WaitlistRecords};')(createElement,'records','stack','button','state',value=>value);
const findButtons=node=>node&&typeof node==='object'?[...(node.type==='button'?[node]:[]),...(node.props?.children||[]).flatMap(findButtons)]:[];
for(const [plate,identity] of [['30A12345','30A12345'],[undefined,'#12']])test(`booking action accessible labels identify ${identity}`,()=>{
 const row={vehicle_id:12,license_plate:plate,status:'confirmed'};
 const tree=BookingRecords({rows:[row],onArrive(){},onCancel(){}});
 const actions=tree.props.columns.find(column=>column.key==='actions').render(row);
 const labels=findButtons(actions).map(button=>button.props['aria-label']);
 assert.deepEqual(labels,[`Xác nhận xe ${identity} đã đến`,`Hủy giữ chỗ xe ${identity}`]);
});
for(const status of ['used','expired','offered'])test(`waitlist ${status} exposes only live withdrawal actions`,()=>{
 const row={status};
 const tree=WaitlistRecords({rows:[row],onOffer(){},onCancel(){}});
 const actions=tree.props.columns.find(column=>column.key==='actions').render(row);
 assert.equal(findButtons(actions).length,status==='offered'?1:0);
});
