import assert from "node:assert/strict";
import { test } from "node:test";
import { refundAction, refundDecisions, refundStatusLabel } from "./supportState.js";

test("refund button follows the server eligibility block only", () => {
  assert.deepEqual(refundAction({ kind: "receipt", refund: { eligible: true, refundable_amount: 1000 } }), { kind: "request", label: "Yêu cầu hoàn" });
  assert.equal(refundAction({ kind: "receipt", refund: { eligible: false, open_request_id: "x" } }).kind, "open");
  assert.equal(refundAction({ kind: "receipt", refund: { eligible: false, blocked_label: "Vé đã được sử dụng nên không hoàn." } }).label, "Vé đã được sử dụng nên không hoàn.");
  assert.equal(refundAction({ kind: "refund", refund: null }).kind, "none");
  assert.equal(refundAction({ kind: "receipt" }).kind, "none");
});

test("manager decisions depend on state and channel; legacy rows are read-only here", () => {
  assert.deepEqual(refundDecisions({ status: "pending", payment_channel: "counter" }), { review: true, approve: true, reject: true, record: false });
  assert.deepEqual(refundDecisions({ status: "approved", payment_channel: "counter" }), { review: false, approve: false, reject: true, record: true });
  assert.deepEqual(refundDecisions({ status: "approved", payment_channel: "demo" }), { review: false, approve: false, reject: true, record: false });
  assert.deepEqual(refundDecisions({ status: "refunded", payment_channel: "counter" }), { review: false, approve: false, reject: false, record: false });
  assert.deepEqual(refundDecisions({ status: "pending", legacy: true }), { review: false, approve: false, reject: false, record: false });
});

test("status labels keep the DEMO distinction", () => {
  assert.equal(refundStatusLabel({ status: "refunded", demo: true }), "Đã hoàn mô phỏng (DEMO)");
  assert.equal(refundStatusLabel({ status: "refunded", demo: false }), "Đã hoàn tiền");
  assert.equal(refundStatusLabel({ status: "approved" }), "Được duyệt, chờ hoàn");
});
