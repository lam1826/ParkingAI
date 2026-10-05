import test from 'node:test';
import assert from 'node:assert/strict';
import { admissionChoices } from '../src/pages/Expansion/operationsState.js';
const types=[{id:1,name:'Unserved',is_active:true},{id:2,name:'Car',is_active:true}];
test('default admission type belongs to the selected site',()=>{
  const choices=admissionChoices(types,[{id:5,vehicle_type_id:2,available_now:true}], '');
  assert.equal(choices.typeId,2);
  assert.deepEqual(choices.types.map(t=>t.id),[2]);
});
test('reserved vacant slot can be selected and entitlement is checked by server',()=>{
  const choices=admissionChoices(types,[{id:5,vehicle_type_id:2,is_occupied:false,reserved:true,available_now:false}],2,5);
  assert.equal(choices.slotId,5);
});
