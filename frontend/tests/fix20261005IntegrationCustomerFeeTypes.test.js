// Integration round 2 (PORTAL), review 05/10/2026 #78 customer side: the fee lookup
// offers only vehicle types the selected site has active slots for (CX-BOOKING
// request 3). The availability panel keeps every active catalog type.
import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { feeLookupTypes } from "../src/pages/Expansion/customerFlow.js";

const types = [
  { id: 1, name: "Xe máy", is_active: true },
  { id: 2, name: "Ô tô", is_active: true },
  { id: 3, name: "Xe tải", is_active: false },
];
const loaded = (slots) => ({ data: { site_id: 2, slots }, loading: false, error: "" });
const ids = (rows) => rows.map((row) => row.id);

test("#78 fee lookup offers only the active types the selected site serves", () => {
  // Real /sites/{id}/availability rows: active slots only, occupied ones included.
  const slots = [
    { id: 9, vehicle_type_id: 2, is_occupied: true, available_now: false, reserved: false },
    { id: 10, vehicle_type_id: 2, is_occupied: false, available_now: true, reserved: false },
    { id: 11, vehicle_type_id: 3, is_occupied: false, available_now: true, reserved: false },
  ];
  assert.deepEqual(ids(feeLookupTypes(types, loaded(slots))), [2]);
  // A full site still serves its types: a parked car must find its own type.
  assert.deepEqual(ids(feeLookupTypes(types, loaded([{ id: 9, vehicle_type_id: 1, is_occupied: true, available_now: false }]))), [1]);
  assert.deepEqual(ids(feeLookupTypes(types, loaded([{ id: 9, vehicle_type_id: "1" }]))), [1]);
  assert.deepEqual(feeLookupTypes(types, loaded([])), []);
  assert.deepEqual(feeLookupTypes(null, loaded([{ id: 9, vehicle_type_id: 2 }])), []);
});

test("#78 saved repro shape: production catalog rows (no is_active) on site 2 serving types 2 and 3", () => {
  // backend/artifacts/code-review-20261005/repro/verify-r2-3-gap-prod-single-site-topology-repro/topology.test.mjs
  const catalog = [
    { id: 1, name: "xe máy", requires_plate: true, code_prefix: null },
    { id: 2, name: "DEMO demo260908 Ô tô", requires_plate: true, code_prefix: null },
    { id: 3, name: "DEMO demo260908 Xe máy", requires_plate: true, code_prefix: null },
  ];
  const site2Slots = Array.from({ length: 16 }, (_, i) => ({ id: 100 + i, vehicle_type_id: i < 8 ? 2 : 3, available_now: true }));
  assert.deepEqual(ids(feeLookupTypes(catalog, loaded(site2Slots))), [2, 3]);
});

test("#78 the choice waits for the site's inventory; only a failed inventory falls back to the catalog", () => {
  assert.deepEqual(feeLookupTypes(types, { data: null, loading: true, error: "" }), []);
  // The fee lookup must stay usable when only the availability panel failed; the server validates the type.
  assert.deepEqual(ids(feeLookupTypes(types, { data: null, loading: false, error: "Không tải được dữ liệu." })), [1, 2]);
  assert.deepEqual(feeLookupTypes(types, undefined), []);
});

test("#78 CustomerFees wires served types into the select and never submits a stale choice", () => {
  const source = readFileSync(new URL("../src/pages/Expansion/CustomerFees.jsx", import.meta.url), "utf8");
  assert.match(source, /const choices = feeLookupTypes\(types\.data, availability\);/);
  assert.doesNotMatch(source, /const choices = \(types\.data \|\| \[\]\)\.filter/);
  // A type chosen before the inventory narrowed the list is dropped, not submitted.
  assert.match(source, /const vehicleTypeId = choices\.some\(\(row\) => String\(row\.id\) === form\.vehicle_type_id\) \? form\.vehicle_type_id : "";/);
  assert.match(source, /<select id="customer-type"[^>]*disabled=\{action\.busy \|\| types\.loading \|\| availability\.loading \|\| !!types\.error\}/);
  // The availability panel keeps every active catalog type (zero capacity stays visible).
  assert.match(source, /availability\.data && activeTypes\.map\(\(row\) =>/);
  // The 02/10 lookup guards and CL-ONLINE's #79 payment choice stay.
  assert.match(source, /if \(token !== localStorage\.getItem\("token"\)\) throw new Error\("Phiên đăng nhập đã thay đổi\."\);/);
  assert.match(source, /if \(!validFeeLookup\(data\)\) throw new Error/);
  assert.match(source, /const payment = feePaymentChoice\(balance\);/);
  assert.match(source, /feeLookupBody\(\{ \.\.\.form, vehicle_type_id: vehicleTypeId \}, site\.id\)/);
});
