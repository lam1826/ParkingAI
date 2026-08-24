import assert from "node:assert/strict";
import test from "node:test";

import { getParkingSlotVisualStatus } from "../src/utils/parkingSlotStatus.js";

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
