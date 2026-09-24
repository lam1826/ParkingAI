import test from "node:test";
import assert from "node:assert/strict";
import { admissionChoices, operationLookup, operationTypeName } from "./operationsState.js";

const types = [{ id: 1, name: "Ô tô", is_active: true }, { id: 2, name: "Xe đạp", requires_plate: false }, { id: 3, is_active: false }];
const slots = [{ id: 10, vehicle_type_id: 1, available_now: false }, { id: 11, vehicle_type_id: 1, available_now: true }, { id: 12, vehicle_type_id: 2, available_now: true }];
test("untouched admission uses an active type and server-available slot", () => {
  const selected = admissionChoices(types, slots);
  assert.equal(selected.typeId, 1); assert.equal(selected.slotId, 11);
  assert.equal(selected.requiresPlate, true); assert.deepEqual(selected.types.map(row => row.id), [1, 2]);
});
test("stale explicit type and slot choices require reselection", () => {
  assert.equal(admissionChoices(types, slots, 3).slotId, "");
  assert.equal(admissionChoices(types, slots, 1, 10).slotId, "");
  assert.equal(admissionChoices(types, slots, 1, 12).slotId, "");
});
test("non-plate vehicle uses server identity and type-specific capacity", () => {
  const selected = admissionChoices(types, slots, "2");
  assert.equal(selected.requiresPlate, false); assert.equal(selected.slotId, 12);
  assert.equal(admissionChoices(types, [], 2).slotId, "");
});
test("lookup keeps ticket identity separate from normalized plate", () => {
  assert.deepEqual(operationLookup(" 59a-123.45 "), { status: "active", limit: 25, offset: 0, license_plate: "59A-123.45" });
  assert.deepEqual(operationLookup(" ab-C123 ", "ticket"), { status: "active", limit: 25, offset: 0, session_id: "ab-C123" });
  assert.throws(() => operationLookup(" "), /biển số/);
});

test("active scoped stay resolves its vehicle type from its actual slot without guessing", () => {
  assert.equal(operationTypeName({ parking_slot_id: 12 }, types, slots), "Xe đạp");
  assert.equal(operationTypeName({ parking_slot_id: 12, vehicle_type_id: 1 }, types, slots), "Ô tô");
  assert.equal(operationTypeName({ vehicle_type_name: "Xe lịch sử" }, types, slots), "Xe lịch sử");
  assert.equal(operationTypeName({ parking_slot_id: 99 }, types, slots), "—");
});
