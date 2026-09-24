import test from "node:test";
import assert from "node:assert/strict";
import { availabilityByZone, availabilityLabel } from "../src/utils/availabilityPresentation.js";

test("zone counts separate occupied, held and server-confirmed admission capacity", () => {
  const slots = [
    { zone_id: 1, zone_name: "A", is_occupied: true, available_now: false, reserved: false },
    { zone_id: 1, zone_name: "A", is_occupied: false, available_now: false, reserved: true },
    { zone_id: 1, zone_name: "A", is_occupied: false, available_now: true, reserved: false },
    { zone_id: 2, zone_name: "A", is_occupied: false, available_now: false, reserved: true },
  ];
  assert.deepEqual(availabilityByZone(slots), [
    { id: 1, name: "A", total: 3, occupied: 1, reserved: 1, available: 1 },
    { id: 2, name: "A", total: 1, occupied: 0, reserved: 1, available: 0 },
  ]);
  assert.deepEqual(slots.map(availabilityLabel), ["Đang có xe", "Đã dành chỗ", "Có thể nhận xe", "Đã dành chỗ"]);
});

test("missing availability cannot be advertised as a free admission space", () => {
  const unknown = { zone_id: 1, zone_name: "A", is_occupied: false };
  assert.equal(availabilityByZone([unknown])[0].available, 0);
  assert.equal(availabilityLabel(unknown), "Chưa xác nhận khả năng nhận xe");
  assert.deepEqual(availabilityByZone(), []);
});
