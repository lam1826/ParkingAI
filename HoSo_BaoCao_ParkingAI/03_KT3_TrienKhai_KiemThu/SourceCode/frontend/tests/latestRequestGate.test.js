import assert from "node:assert/strict";
import test from "node:test";

import { createLatestRequestGate } from "../src/utils/latestRequestGate.js";


test("latest request gate chỉ cho request mới nhất cập nhật giao diện", () => {
  const gate = createLatestRequestGate();
  const firstRequest = gate.begin();
  const secondRequest = gate.begin();

  assert.equal(gate.isCurrent(firstRequest), false);
  assert.equal(gate.isCurrent(secondRequest), true);

  gate.invalidate();
  assert.equal(gate.isCurrent(secondRequest), false);
});
