// Review 05/10/2026 CL-LEDGER #1/#26/#27 (direct refund button) and #24 (stable refund key).
import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import {
  directRefundAction, loadPendingRefunds, refundDialogState, refundFailure, refundOutcomeUncertain,
  settleRefundAttempt, UNCERTAIN_REFUND_MESSAGE,
} from "../src/pages/Expansion/siteFinanceRefund.js";

const receipt = { id: "r1", kind: "receipt", method: "cash", refundable_amount: 75000 };

function memoryStorage() {
  const data = new Map();
  return { getItem: (key) => data.get(key) ?? null, setItem: (key, value) => data.set(key, String(value)), data };
}

test("#1/#26/#27 the Hoàn tiền button follows the server's direct-refund block", () => {
  assert.deepEqual(directRefundAction(receipt, true), { kind: "refund", label: "Hoàn tiền" });
  for (const reason of ["portal_ticket", "portal_monthly", "request_open"]) {
    const blocked = directRefundAction({ ...receipt, direct_refund_blocked_reason: reason, direct_refund_blocked_label: `label ${reason}` }, true);
    assert.deepEqual(blocked, { kind: "blocked", label: `label ${reason}` });
  }
  assert.equal(directRefundAction({ ...receipt, direct_refund_blocked_reason: "portal_ticket" }, true).kind, "blocked");
  assert.equal(directRefundAction(receipt, false).kind, "none");
  assert.equal(directRefundAction({ ...receipt, method: "demo" }, true).kind, "none");
  assert.equal(directRefundAction({ ...receipt, refundable_amount: 0 }, true).kind, "none");
  assert.equal(directRefundAction({ ...receipt, kind: "refund" }, true).kind, "none");
});

test("#24 an uncertain refund keeps its idempotency key and content for the reopened dialog", () => {
  const storage = memoryStorage();
  let minted = 0;
  const makeKey = () => `key-${++minted}`;
  const first = refundDialogState({}, "r1", makeKey);
  assert.equal(first.key, "key-1");
  assert.equal(first.uncertain, false);
  const attempt = { key: first.key, amount: 37500, method: "cash", reason: "Khách trả lại" };
  const timeout = Object.assign(new Error("timeout of 10000ms exceeded"), { code: "ECONNABORTED" });
  const pending = settleRefundAttempt({}, "r1", attempt, timeout, storage);
  // Closing with "Quay lại" and reopening must not mint a new key (the backend dedupes by key).
  const reopened = refundDialogState(pending, "r1", makeKey);
  assert.deepEqual(reopened, { key: "key-1", amount: "37500", method: "cash", reason: "Khách trả lại", uncertain: true });
  assert.equal(minted, 1);
  // Survives a page reload of the same tab.
  assert.deepEqual(loadPendingRefunds(storage).r1.key, "key-1");
  // Other receipts are unaffected.
  assert.equal(refundDialogState(pending, "r2", makeKey).key, "key-2");
  // 5xx, 408 and 429 are uncertain too; a definitive 4xx or a success forgets the key.
  for (const status of [500, 502, 408, 429]) assert.equal(refundOutcomeUncertain({ response: { status } }), true);
  for (const status of [400, 403, 409, 422]) assert.equal(refundOutcomeUncertain({ response: { status } }), false);
  const refused = settleRefundAttempt(pending, "r1", attempt, { response: { status: 409, data: { detail: "x" } } }, storage);
  assert.equal(refused.r1, undefined);
  const again = settleRefundAttempt(pending, "r1", attempt, undefined, storage);
  assert.equal(again.r1, undefined);
  assert.deepEqual(loadPendingRefunds(storage), {});
});

test("#24 uncertain failures are shown as 'not confirmed', never as a raw axios message", () => {
  const network = new Error("Network Error");
  assert.equal(refundFailure(network).message, UNCERTAIN_REFUND_MESSAGE);
  assert.equal(refundFailure(network).response, undefined);
  const conflict = { response: { status: 409, data: { detail: "Số tiền hoàn vượt quá" } } };
  assert.equal(refundFailure(conflict), conflict);
  assert.match(UNCERTAIN_REFUND_MESSAGE, /tải lại/);
  assert.deepEqual(loadPendingRefunds({ getItem: () => { throw new Error("blocked"); } }), {});
  assert.deepEqual(loadPendingRefunds({ getItem: () => "[1,2]" }), {});
});

test("SiteFinance.jsx wires the server block and the per-receipt key", () => {
  const source = readFileSync(new URL("../src/pages/Expansion/SiteFinance.jsx", import.meta.url), "utf8");
  assert.match(source, /directRefundAction\(row, manager\)/);
  assert.match(source, /refundDialogState\(pendingRefunds, row\.id, requestKey\)/);
  assert.match(source, /settleRefundAttempt\(old, row\.id, attempt, failure\)/);
  assert.match(source, /throw refundFailure\(failure\)/);
  assert.doesNotMatch(source, /row\.refundable_amount > 0 && <Button/);
});
