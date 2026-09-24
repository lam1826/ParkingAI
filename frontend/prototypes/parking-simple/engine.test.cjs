/* Pure demo tests: no application database, browser, provider or network. */
const test = require('node:test');
const assert = require('node:assert/strict');
const { readFileSync } = require('node:fs');
const { join } = require('node:path');
const vm = require('node:vm');
const context = { window: {} };
vm.runInNewContext(readFileSync(join(__dirname, 'engine.js'), 'utf8'), context);
const E = context.window.DemoEngine;
const plain = value => JSON.parse(JSON.stringify(value));
const apply = (state, action) => E.apply(state, { role: 'manager', ...action });
const ok = (state, action) => {
  const result = apply(state, action);
  assert.equal(result.ok, true, result.message);
  return result.state;
};
const no = (state, action) => {
  const before = plain(state);
  const result = apply(state, action);
  assert.equal(result.ok, false, result.message);
  assert.deepEqual(plain(state), before, 'input state must not mutate');
  assert.deepEqual(plain(result.state), before, 'failed actions must be atomic');
};
const session = (state, plate) => state.sessions.find(item => item.status === 'active' && E.normalize(item.plate) === E.normalize(plate));
const at = (state, time) => ({ ...plain(state), now: time });
const typeAction = (state, id, changes = {}) => ({ ...E.typeInfo(id, state), ...changes, type: 'save-vehicle-type' });
const slotAction = (state, code, changes = {}) => ({ ...state.slots.find(item => item.code === code), ...changes, originalCode: code, type: 'save-slot' });

test('seed has seven days of non-overlapping completed stays and paired receipts', () => {
  const state = E.seed();
  const history = state.sessions.filter(item => Number(item.id.slice(3)) >= 6000);
  assert.equal(history.length, 28);
  assert.equal(new Set(history.map(item => item.entry.slice(0, 10))).size, 7);
  for (const item of history) {
    assert.equal(item.status, 'closed');
    assert.ok(Date.parse(item.exit) <= Date.parse(state.now));
    const receipt = state.transactions.filter(row => row.sessionId === item.id);
    assert.equal(receipt.length, 1);
    assert.equal(receipt[0].amount, E.quote(state, item).gross);
    for (const other of state.sessions) {
      if (other.id === item.id || other.slot !== item.slot) continue;
      assert.ok(Date.parse(item.exit) <= Date.parse(other.entry) || (other.exit && Date.parse(other.exit) <= Date.parse(item.entry)), `${item.id} overlaps ${other.id}`);
    }
  }
  assert.equal(E.available(state, 'car'), 9, 'two occupied plus one held out of twelve');
  assert.equal(E.slotStatus(state, state.slots.find(row => row.code === 'B-03')), 'reserved');
  assert.equal(E.passStatus(state, state.monthlyPasses[0]).key, 'active');
  assert.equal(E.passStatus(state, state.monthlyPasses[1]).key, 'expired');
  assert.equal(E.passStatus(state, state.monthlyPasses[2]).key, 'upcoming');
});

test('walk-in, immutable hourly price, partial-time payment, extra block, exit and lookup', () => {
  let state = E.seed();
  const original = plain(state);
  const free = E.available(state, 'car');
  state = ok(state, { type: 'checkin', plate: '51A-777.77', vehicleType: 'car' });
  assert.equal(original.sessions.length + 1, state.sessions.length);
  let stay = session(state, '51A77777');
  assert.equal(E.quote(state, stay).gross, 20000);
  assert.equal(E.lookupSession(state, stay.ticket, 'car').id, stay.id);
  assert.equal(E.available(state, 'car'), free - 1);
  no(state, { type: 'checkin', plate: '51a77777', vehicleType: 'car' });
  no(state, { type: 'checkout', sessionId: stay.id });
  state = ok(state, typeAction(state, 'car', { rate: 99000 }));
  state = ok(state, { type: 'advance', minutes: 60 });
  assert.equal(E.quote(state, session(state, stay.plate)).gross, 20000);
  state = ok(state, { type: 'pay', sessionId: stay.id, method: 'cash' });
  assert.equal(E.slotStatus(state, state.slots.find(row => row.code === stay.slot)), 'occupied');
  const receiptCount = state.transactions.length;
  state = ok(state, { type: 'pay', sessionId: stay.id, method: 'cash' });
  assert.equal(state.transactions.length, receiptCount, 'payment replay cannot duplicate a receipt');
  state = ok(state, { type: 'advance', minutes: 1 });
  assert.equal(E.quote(state, session(state, stay.plate)).due, 20000);
  no(state, { type: 'checkout', sessionId: stay.id });
  state = ok(state, { type: 'pay', sessionId: stay.id, method: 'online' });
  state = ok(state, { type: 'checkout', sessionId: stay.id });
  assert.equal(E.available(state, 'car'), free);
  assert.equal(E.lookupSession(state, stay.ticket, 'car'), undefined);
  const closed = state.sessions.find(row => row.id === stay.id);
  state = ok(state, { type: 'advance', minutes: 24 * 60 });
  assert.equal(E.quote(state, closed).gross, 40000, 'closed total must not accrue');
  assert.equal(state.transactions.filter(row => row.sessionId === stay.id).reduce((sum, row) => sum + row.amount, 0), 40000);
});

test('monthly coverage uses entry snapshot, inclusive end date and hourly overtime', () => {
  let state = at(E.seed(), '2026-09-30T23:30:00+07:00');
  state = ok(state, { type: 'checkin', plate: '59A-888.88', vehicleType: 'car' });
  let stay = session(state, '59A88888');
  assert.equal(stay.monthlyPassId, 'VT-1');
  assert.equal(stay.customerId, 'KH-1');
  assert.equal(E.quote(state, stay).due, 0);
  assert.equal(Date.parse(stay.coverageEnd), Date.parse('2026-10-01T00:00:00+07:00'));
  const original = plain(state.monthlyPasses[0]);
  state = ok(state, { type: 'renew-pass', id: 'VT-1', endDate: '2026-10-31', price: 650000 });
  assert.deepEqual(plain(state.monthlyPasses[0]), original, 'renewal retains old period');
  state = ok(state, { ...original, active: false, type: 'save-pass' });
  state = ok(state, typeAction(state, 'car', { rate: 99000 }));
  state = ok(state, { type: 'advance', minutes: 30 });
  stay = session(state, stay.plate);
  assert.equal(E.quote(state, stay).due, 0, 'exclusive coverage boundary has zero elapsed overtime');
  state = ok(state, { type: 'advance', minutes: 1 });
  assert.equal(E.quote(state, stay).due, 20000, 'renewal and new tariff must not alter the stay snapshot');
  assert.equal(E.quote(state, stay).coveredMinutes, 30);
  assert.equal(E.quote(state, stay).billableMinutes, 1);
  state = ok(state, { type: 'advance', minutes: 59 });
  assert.equal(E.quote(state, stay).due, 20000);
  state = ok(state, { type: 'advance', minutes: 1 });
  assert.equal(E.quote(state, stay).due, 40000);
  state = ok(state, { type: 'pay', sessionId: stay.id, method: 'cash' });
  state = ok(state, { type: 'checkout', sessionId: stay.id });
  assert.equal(state.sessions.find(row => row.id === stay.id).closedGross, 40000);
});

test('valid monthly pass permits a free exit; expired and future passes do not cover entry', () => {
  let state = E.seed();
  state = ok(state, { type: 'checkin', plate: '59A88888', vehicleType: 'car' });
  const stay = session(state, '59A88888');
  const receipts = state.transactions.length;
  state = ok(state, { type: 'checkout', sessionId: stay.id });
  assert.equal(state.transactions.length, receipts, 'free covered exit does not invent income');
  for (const [plate, vehicleType, amount] of [['59B1-555.55', 'motorbike', 5000], ['59A-888.89', 'car', 20000]]) {
    state = ok(state, { type: 'checkin', plate, vehicleType });
    const fee = E.quote(state, session(state, plate));
    assert.equal(fee.monthlyPassId, null);
    assert.equal(fee.due, amount);
  }
});

test('future holds consume usable space, correct arrival consumes hold, late holds expire', () => {
  let state = E.seed();
  const free = E.available(state, 'ebike');
  state = ok(state, { type: 'reserve', plate: 'XDD-TEST', vehicleType: 'ebike', start: state.now, end: '2026-09-23T19:00:00+07:00' });
  const hold = state.reservations[0];
  assert.equal(E.available(state, 'ebike'), free - 1);
  no(state, slotAction(state, hold.slot, { active: false }));
  no(state, { ...state.zones.find(row => row.id === 'zone_ebike'), type: 'save-zone', active: false });
  no(state, typeAction(state, 'ebike', { active: false }));
  state = ok(state, { type: 'advance', minutes: 15 });
  assert.equal(state.reservations.find(row => row.id === hold.id).status, 'confirmed');
  state = ok(state, { type: 'checkin', plate: hold.plate, vehicleType: 'ebike' });
  assert.equal(session(state, hold.plate).slot, hold.slot);
  assert.equal(state.reservations.find(row => row.id === hold.id).status, 'arrived');
  assert.equal(E.available(state, 'ebike'), free - 1, 'arrival replaces one hold with one occupied slot');
  state = ok(state, { type: 'reserve', plate: 'XDD-LATE', vehicleType: 'ebike', start: state.now, end: '2026-09-23T19:00:00+07:00' });
  const late = state.reservations[0];
  state = ok(state, { type: 'advance', minutes: 16 });
  assert.equal(state.reservations.find(row => row.id === late.id).status, 'expired');
  assert.equal(E.available(state, 'ebike'), free - 1);
});

test('disabled slot, zone and type are excluded; existing occupied state remains visible', () => {
  let state = E.seed();
  state = ok(state, slotAction(state, 'D-01', { active: false }));
  assert.equal(E.available(state, 'ebike'), 7);
  assert.equal(state.capacity.ebike, 7);
  assert.equal(E.slotStatus(state, state.slots.find(row => row.code === 'D-01')), 'inactive');
  const zone = state.zones.find(row => row.id === 'zone_ebike');
  state = ok(state, { ...zone, type: 'save-zone', active: false });
  assert.equal(E.available(state, 'ebike'), 0);
  assert.equal(state.capacity.ebike, 0);
  no(state, { type: 'checkin', plate: '', vehicleType: 'ebike' });
  no(state, { type: 'reserve', plate: '', vehicleType: 'ebike', start: state.now, end: '2026-09-23T18:00:00+07:00' });
  state = ok(state, { ...zone, type: 'save-zone', active: true });
  state = ok(state, typeAction(state, 'ebike', { active: false }));
  assert.equal(E.available(state, 'ebike'), 0);
  assert.equal(E.typesFor(state).find(row => row.id === 'ebike').active, false);
  no(state, { type: 'checkin', plate: '', vehicleType: 'ebike' });
  assert.equal(E.slotStatus(state, state.slots.find(row => row.code === 'B-01')), 'occupied');
});

test('catalogue permissions reject missing, employee and customer roles atomically', () => {
  const state = E.seed();
  const actions = ['save-zone', 'delete-zone', 'save-vehicle-type', 'add-vehicle-type', 'delete-vehicle-type', 'save-slot', 'add-slot', 'delete-slot', 'save-customer', 'save-vehicle', 'save-pass', 'renew-pass'];
  for (const role of [undefined, 'staff', 'employee', 'customer']) {
    for (const type of actions) no(state, { type, role });
  }
  const admin = ok(state, { type: 'save-zone', role: 'admin', name: 'Khu quản trị', vehicleType: 'car', capacity: 1, active: true });
  assert.equal(admin.zones.length, state.zones.length + 1);
});

test('catalogue capacity, canonical uniqueness, unused deletion and historical retention', () => {
  let state = E.seed();
  no(state, { type: 'save-slot', code: 'B-13', vehicleType: 'car', zoneId: 'zone_car', active: true });
  no(state, { type: 'save-slot', code: 'b-0001', vehicleType: 'car', zoneId: 'zone_car', active: true });
  no(state, { ...state.zones[0], type: 'save-zone', capacity: 11 });
  no(state, { type: 'delete-zone', id: 'zone_car' });
  no(state, { type: 'delete-vehicle-type', id: 'car' });
  no(state, { type: 'delete-slot', code: 'B-04' });
  no(state, slotAction(state, 'B-04', { code: 'B-NEW' }));
  state = ok(state, { type: 'save-zone', name: 'Khu thử riêng', vehicleType: 'car', capacity: 1, active: true });
  const zone = state.zones.at(-1);
  state = ok(state, { type: 'save-slot', code: 'ZZ-01', vehicleType: 'car', zoneId: zone.id, active: true });
  assert.equal(E.available(state, 'car'), 10);
  state = ok(state, { type: 'save-slot', code: 'ZZ-01', newCode: 'ZZ-02', vehicleType: 'car', zoneId: zone.id, active: true });
  state = ok(state, { type: 'delete-slot', code: 'ZZ-02' });
  state = ok(state, { type: 'delete-zone', id: zone.id });
  assert.equal(E.available(state, 'car'), 9);
  state = ok(state, { type: 'add-vehicle-type', label: 'Xe thử nghiệm', prefix: 'Z', requiresPlate: false, rate: 1000 });
  state = ok(state, { type: 'delete-vehicle-type', id: 'custom_z' });
  state = ok(state, { type: 'add-slot', code: 'B-13', vehicleType: 'car' });
  assert.equal(state.zones.find(row => row.id === 'zone_car').capacity, 13, 'old add-slot contract remains supported');
});

test('customer, registered vehicle, issued pass and renewal retain financial history', () => {
  let state = E.seed();
  state = ok(state, { type: 'save-customer', name: 'Khách kiểm thử', phone: '0901234567', email: 'test@example.test', active: true });
  const customer = state.customers.at(-1);
  state = ok(state, { type: 'save-vehicle', customerId: customer.id, plate: '51A-999.99', vehicleType: 'car', active: true });
  const vehicle = state.vehicles.at(-1);
  no(state, { type: 'save-vehicle', customerId: customer.id, plate: '51a99999', vehicleType: 'car', active: true });
  const pass = { type: 'save-pass', customerId: customer.id, plate: vehicle.plate, vehicleType: 'car', startDate: '2026-09-23', endDate: '2026-10-22', price: 500000, active: true };
  state = ok(state, pass);
  const saved = state.monthlyPasses.at(-1);
  assert.equal(state.transactions[0].monthlyPassId, saved.id);
  assert.equal(state.transactions[0].amount, 500000);
  no(state, pass);
  no(state, { ...saved, type: 'save-pass', price: 1 });
  no(state, { ...vehicle, type: 'save-vehicle', plate: '51A-111.11' });
  no(state, { ...vehicle, type: 'save-vehicle', customerId: 'KH-1' });
  state = ok(state, { type: 'renew-pass', id: saved.id, endDate: '2026-11-22', price: 550000 });
  const renewed = state.monthlyPasses.at(-1);
  assert.equal(renewed.startDate, '2026-10-23');
  assert.notEqual(renewed.id, saved.id);
  assert.equal(state.transactions.filter(row => row.monthlyPassId === saved.id).length, 1);
  assert.equal(state.transactions.filter(row => row.monthlyPassId === renewed.id).length, 1);
  no(state, { type: 'renew-pass', id: saved.id, endDate: '2026-11-22', price: 550000 });
  state = ok(state, { type: 'checkin', plate: vehicle.plate, vehicleType: 'car' });
  no(state, { ...customer, type: 'save-customer', active: false });
  no(state, { ...vehicle, type: 'save-vehicle', active: false });
});

test('invalid catalogue inputs fail without coercing booleans to money or throwing', () => {
  const state = E.seed();
  for (const rate of [false, null, '', -1, 0.5, Number.MAX_SAFE_INTEGER]) no(state, typeAction(state, 'car', { rate }));
  for (const price of [false, null, '', -1, 0.5]) no(state, { type: 'renew-pass', id: 'VT-1', endDate: '2026-10-31', price });
  no(state, { type: 'save-vehicle', customerId: 'KH-1', plate: '', vehicleType: 'missing', active: true });
  no(state, { type: 'renew-pass', id: 'VT-1', startDate: '2026-02-30', endDate: '2026-10-31', price: 1 });
  no(state, { type: 'save-customer', name: '<b>Unsafe</b>', phone: '0901234567', email: '' });
  no(state, { type: 'save-zone', name: 'Khu mới', vehicleType: 'car', capacity: -1, active: true });
});

test('inactive customers can have vehicles disabled, but cannot be granted a new pass', () => {
  let state = E.seed();
  const customer = state.customers.find(row => row.id === 'KH-2');
  state = ok(state, { ...customer, type: 'save-customer', active: false });
  const vehicle = state.vehicles.find(row => row.id === 'XE-2');
  state = ok(state, { ...vehicle, type: 'save-vehicle', active: false });
  no(state, { type: 'renew-pass', id: 'VT-2', startDate: '2026-09-01', endDate: '2026-09-30', price: 150000 });
  no(state, { type: 'checkin', plate: vehicle.plate, vehicleType: vehicle.vehicleType });
});

test('unregistered bicycles get unique identifiers and unsupported operations are harmless', () => {
  let state = E.seed();
  state = ok(state, { type: 'checkin', plate: '', vehicleType: 'bicycle' });
  const first = state.sessions[0];
  state = ok(state, { type: 'checkin', plate: '', vehicleType: 'bicycle' });
  assert.notEqual(first.plate, state.sessions[0].plate);
  assert.ok(first.plate.startsWith('XD-'));
  assert.equal(E.lookupSession(state, first.ticket, 'bicycle').id, first.id);
  no(state, { type: 'does-not-exist' });
});
