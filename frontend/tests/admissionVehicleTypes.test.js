import assert from "node:assert/strict";
import test from "node:test";
import { admissionTypeId, admissionVehicleTypes } from "../src/utils/admissionVehicleTypes.js";

test("admission excludes inactive types without removing historical catalog rows", () => {
  const types = Object.freeze([{ id: 1, is_active: true }, { id: 2, is_active: false }, { id: 3 }, { id: 4, is_active: null }]);
  assert.deepEqual(admissionVehicleTypes(types).map((row) => row.id), [1, 3]);
  assert.equal(types.length, 4);
  assert.equal(types[1].is_active, false);
});

test("an active selection becomes empty when refreshed metadata disables or removes it", () => {
  assert.equal(admissionTypeId([{ id: 1, is_active: true }], "1"), "1");
  assert.equal(admissionTypeId([{ id: 1, is_active: false }], "1"), "");
  assert.equal(admissionTypeId([], 1), "");
  assert.equal(admissionTypeId([{ id: 1 }], ""), "");
  assert.equal(admissionTypeId([{ id: 1 }], 1), 1);
});
