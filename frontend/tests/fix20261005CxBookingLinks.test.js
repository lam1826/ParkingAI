import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
// Execute the actual link builder before rendering the overview.
const source=readFileSync(new URL('../src/pages/Expansion/OverviewPage.jsx',import.meta.url),'utf8').replaceAll('\r','');
const start=source.indexOf('export function overviewLinks');
const code=source.slice(start,source.indexOf('\n}\n',start)+3).replace('export ','');
test('staff and manager overview links stay within the selected site',()=>{
 const links=new Function(code+';return overviewLinks;')()({id:2,role:'staff'});
 assert.ok(links.some(link=>link.to==='/sites?site=2&tab=availability'));
 assert.ok(links.some(link=>link.to==='/sites?site=2&tab=reservations'));
 assert.ok(!links.some(link=>['/customers','/parking-slots','/users'].includes(link.to)));
});
