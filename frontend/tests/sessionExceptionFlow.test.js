import assert from "node:assert/strict";
import test from "node:test";
import { createSessionExceptionFlow, validCorrectionPlate, validExceptionReason } from "../src/pages/ParkingSession/sessionExceptionFlow.js";

function setup(send, extra = {}) {
  const flow = createSessionExceptionFlow({ sessionId: "stay-1", requestId: () => "request-1", send, ...extra });
  flow.start(); flow.choose("cancel"); flow.setReason("  Nhập nhầm biển số  ");
  return flow;
}
const result = { session_id: "stay-1", status: "cancelled", event: { id: 1, action: "cancelled" }, next_action: "none" };

test("exception validates reasons and posts only server-authorized fields", async () => {
  assert.equal(validExceptionReason("  "), false);
  assert.equal(validExceptionReason("ab"), false);
  assert.equal(validExceptionReason("x".repeat(501)), false);
  const calls = [];
  const flow = setup(async (action, body) => { calls.push({ action, body }); return result; });
  await flow.submit();
  assert.deepEqual(calls, [{ action: "cancel", body: { reason: "Nhập nhầm biển số", request_id: "request-1" } }]);
  assert.equal(flow.getSnapshot().phase, "completed");
});

test("uncertain mutation retries identical action and body and cannot be dismissed or edited", async () => {
  const calls = [];
  const flow = setup(async (action, body) => { calls.push({ action, body }); if (calls.length === 1) throw new Error("offline"); return result; });
  await flow.submit();
  assert.equal(flow.getSnapshot().phase, "uncertain");
  assert.equal(flow.canDismiss(), false);
  flow.choose("lost-ticket"); flow.setReason("Changed reason");
  await flow.submit();
  assert.equal(calls[1].body, calls[0].body);
  assert.equal(calls[1].action, "cancel");
});

test("double click sends once and late completion is ignored across auth boundary", async () => {
  let finish, count = 0, completed = 0, authorized = true;
  const flow = setup(() => { count += 1; return new Promise((resolve) => { finish = resolve; }); }, { isAuthorized: () => authorized, onCompleted: () => { completed += 1; } });
  const first = flow.submit();
  await flow.submit();
  assert.equal(count, 1);
  authorized = false;
  finish(result); await first;
  assert.equal(completed, 0);
});

test("definitive conflict reloads eligibility and does not silently retry", async () => {
  let reloads = 0, calls = 0;
  const flow = setup(async () => { calls += 1; throw { response: { status: 409, data: { detail: "Đã trả xe" } } }; }, { onRejected: () => { reloads += 1; } });
  await flow.submit();
  assert.equal(flow.getSnapshot().phase, "editing");
  assert.equal(flow.getSnapshot().error, "Đã trả xe");
  assert.equal(flow.canDismiss(), true);
  assert.equal(reloads, 1);
  assert.equal(calls, 1);
});

test("wrong-session response stays uncertain instead of recording false success", async () => {
  const flow = setup(async () => ({ ...result, session_id: "another-stay" }));
  await flow.submit();
  assert.equal(flow.getSnapshot().phase, "uncertain");
});

test("plate correction normalizes only the plate and retries the same replacement request", async () => {
  assert.equal(validCorrectionPlate("abc"), false);
  assert.equal(validCorrectionPlate("x".repeat(16)), false);
  const calls = [];
  const flow = setup(async (action, body) => {
    calls.push({ action, body });
    if (calls.length === 1) throw new Error("network timeout");
    return { ...result, event: { id: 2, action: "plate_corrected" }, next_action: "print_replacement_ticket", replacement_session_id: "new-stay" };
  });
  flow.choose("correct-plate"); flow.setReason("Đọc nhầm biển số"); flow.setLicensePlate(" 30a-12345 ");
  await flow.submit();
  flow.setLicensePlate("30B-67890");
  await flow.submit();
  assert.equal(calls[1].body, calls[0].body);
  assert.deepEqual(calls[0], { action: "correct-plate", body: { reason: "Đọc nhầm biển số", request_id: "request-1", license_plate: "30A-12345" } });
  assert.equal(flow.getSnapshot().result.replacement_session_id, "new-stay");
});

test("plate correction cannot succeed without a new replacement ticket id", async () => {
  for (const replacement of [null, "stay-1"]) {
    const flow = setup(async () => ({ ...result, event: { action: "plate_corrected" }, next_action: "print_replacement_ticket", replacement_session_id: replacement }));
    flow.choose("correct-plate"); flow.setReason("Nhập sai biển số"); flow.setLicensePlate("30A-12345");
    await flow.submit();
    assert.equal(flow.getSnapshot().phase, "uncertain");
  }
});

test("lost-ticket approval leads to quote checkout, and revoked manager permission prevents submission", async () => {
  let calls = 0;
  const flow = setup(async () => { calls += 1; return { ...result, status: "active", event: { action: "lost_ticket" }, next_action: "checkout" }; });
  flow.choose("lost-ticket"); flow.setReason("Đã kiểm tra giấy tờ");
  flow.setAuthorization(false);
  await flow.submit();
  assert.equal(calls, 0);
  flow.setAuthorization(true);
  await flow.submit();
  assert.equal(flow.getSnapshot().result.next_action, "checkout");
});

test("lost-ticket retry after another operator completes the stay preserves terminal state", async () => {
  for (const status of ["completed", "cancelled", "checking_out"]) {
    let calls = 0;
    const flow = setup(async () => {
      if (++calls === 1) throw new Error("response lost after commit");
      return { ...result, status, event: { action: "lost_ticket" }, next_action: "none" };
    });
    flow.choose("lost-ticket"); flow.setReason("Đã đối chiếu giấy tờ");
    await flow.submit();
    assert.equal(flow.getSnapshot().phase, "uncertain");
    await flow.submit();
    assert.equal(flow.getSnapshot().phase, "completed");
    assert.equal(flow.getSnapshot().result.status, status);
    assert.equal(flow.getSnapshot().result.next_action, "none");
  }
});

test("lost-ticket result cannot reopen checkout on an already completed stay", async () => {
  const flow = setup(async () => ({ ...result, status: "completed", event: { action: "lost_ticket" }, next_action: "checkout" }));
  flow.choose("lost-ticket"); flow.setReason("Đã kiểm tra giấy tờ");
  await flow.submit();
  assert.equal(flow.getSnapshot().phase, "uncertain");
});
