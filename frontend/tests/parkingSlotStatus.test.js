import assert from "node:assert/strict";
import test from "node:test";

import { getParkingSlotVisualStatus } from "../src/utils/parkingSlotStatus.js";

test("vị trí của loại xe ngừng hoạt động không hiển thị còn trống", () => {
  assert.equal(getParkingSlotVisualStatus({ is_active: true, is_occupied: false }, { is_active: true }, { is_active: false }), "inactive");
});

test("slot trống trong khu vực hoạt động hiển thị còn trống", () => {
  assert.equal(
    getParkingSlotVisualStatus(
      { is_active: true, is_occupied: false },
      { is_active: true },
    ),
    "available",
  );
});

test("slot có xe trong khu vực hoạt động hiển thị đang có xe", () => {
  assert.equal(
    getParkingSlotVisualStatus(
      { is_active: true, is_occupied: true },
      { is_active: true },
    ),
    "occupied",
  );
});

test("khu vực ngừng hoạt động làm mọi slot bên trong hiển thị inactive", () => {
  assert.equal(
    getParkingSlotVisualStatus(
      { is_active: true, is_occupied: false },
      { is_active: false },
    ),
    "inactive",
  );
  assert.equal(
    getParkingSlotVisualStatus(
      { is_active: true, is_occupied: true },
      { is_active: false },
    ),
    "inactive",
  );
});

test("slot ngừng hoạt động hoặc thiếu khu vực đều fail closed thành inactive", () => {
  assert.equal(
    getParkingSlotVisualStatus(
      { is_active: false, is_occupied: false },
      { is_active: true },
    ),
    "inactive",
  );
  assert.equal(
    getParkingSlotVisualStatus({ is_active: true, is_occupied: false }, undefined),
    "inactive",
  );
});


test("held capacity and unknown inventory never advertise a physically empty space", () => {
  const slot = { is_active: true, is_occupied: false }, zone = { is_active: true };
  assert.equal(getParkingSlotVisualStatus(slot, zone, undefined, { reserved: true, available_now: false }), "reserved");
  assert.equal(getParkingSlotVisualStatus(slot, zone, undefined, null), "unknown");
  assert.equal(getParkingSlotVisualStatus(slot, zone, undefined, { available_now: true }), "available");
  assert.equal(getParkingSlotVisualStatus({ ...slot, is_occupied: true }, zone, undefined, { reserved: true }), "occupied");
});
