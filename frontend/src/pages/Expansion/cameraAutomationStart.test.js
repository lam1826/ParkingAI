import test from "node:test";
import assert from "node:assert/strict";
import { canStartCameraAutomation, startCameraAutomation } from "./cameraAutomationStart.js";

const policy = { enabled: false, minimum_confidence: .99, max_age_seconds: 12 };
function scenario(overrides = {}) {
  const calls = [];
  return { calls, options: {
    policy, canManage: true, hasSource: false,
    openSource: async () => { calls.push("camera"); return true; },
    enablePolicy: async update => { calls.push(update); return { ...update }; },
    reloadPolicy: async () => { calls.push("confirm"); return { ...policy, enabled: true }; },
    isActive: () => true, ...overrides,
  } };
}

test("Admin/Manager can start an active camera with policy off; Staff requires prior permission", () => {
  const camera = { is_active: true };
  assert.equal(canStartCameraAutomation(camera, policy, true), true);
  assert.equal(canStartCameraAutomation(camera, policy, false), false);
  assert.equal(canStartCameraAutomation(camera, { ...policy, enabled: true }, false), true);
  assert.equal(canStartCameraAutomation({ is_active: false }, policy, true), false);
  assert.equal(canStartCameraAutomation(camera, null, true), false);
});

test("opens camera, preserves configured thresholds, then waits for server confirmation", async () => {
  const { calls, options } = scenario();
  assert.equal(await startCameraAutomation(options), true);
  assert.deepEqual(calls, ["camera", { enabled: true, minimum_confidence: .99, max_age_seconds: 12 }, "confirm"]);
});

test("existing webcam or edge source does not request a second camera", async () => {
  const { calls, options } = scenario({ hasSource: true });
  assert.equal(await startCameraAutomation(options), true);
  assert.deepEqual(calls, [{ enabled: true, minimum_confidence: .99, max_age_seconds: 12 }, "confirm"]);
});

test("Staff can run an enabled policy without writing manager settings", async () => {
  const { calls, options } = scenario({ policy: { ...policy, enabled: true }, canManage: false });
  assert.equal(await startCameraAutomation(options), true);
  assert.deepEqual(calls, ["camera", "confirm"]);
});

test("Staff cannot enable automation or open camera through forbidden startup", async () => {
  const { calls, options } = scenario({ canManage: false });
  await assert.rejects(startCameraAutomation(options), /Admin hoặc Manager/);
  assert.deepEqual(calls, []);
});

test("denied camera permission prevents policy writes and running", async () => {
  const { calls, options } = scenario({ openSource: async () => false });
  await assert.rejects(startCameraAutomation(options), /Chưa mở được webcam/);
  assert.deepEqual(calls, []);
});

test("failed policy write prevents confirmation and running", async () => {
  const { calls, options } = scenario({ enablePolicy: async () => { throw new Error("HTTP 403"); } });
  await assert.rejects(startCameraAutomation(options), /HTTP 403/);
  assert.deepEqual(calls, ["camera"]);
});

test("server refusal to enable is not a successful start", async () => {
  const { calls, options } = scenario({ enablePolicy: async () => ({ ...policy }) });
  await assert.rejects(startCameraAutomation(options), /Máy chủ chưa cho phép/);
  assert.deepEqual(calls, ["camera"]);
});

for (const confirmed of [null, { ...policy }]) {
  test(`failed or revoked confirmation prevents running (${confirmed ? "disabled" : "null"})`, async () => {
    const { options } = scenario({ reloadPolicy: async () => confirmed });
    await assert.rejects(startCameraAutomation(options), /Chưa xác nhận/);
  });
}

test("unmount while camera opens prevents enabling a shared policy", async () => {
  let active = true;
  const { calls, options } = scenario({
    openSource: async () => { active = false; return true; }, isActive: () => active,
  });
  assert.equal(await startCameraAutomation(options), false);
  assert.deepEqual(calls, []);
});

test("unmount while confirmation loads cannot start the loop", async () => {
  let active = true;
  const { options } = scenario({
    reloadPolicy: async () => { active = false; return { ...policy, enabled: true }; }, isActive: () => active,
  });
  assert.equal(await startCameraAutomation(options), false);
});
