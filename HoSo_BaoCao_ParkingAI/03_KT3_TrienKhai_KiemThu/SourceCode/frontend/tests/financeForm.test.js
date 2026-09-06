import assert from "node:assert/strict";
import test from "node:test";
import { buildRefundPayload, parseCashAmount, paymentMethodLabels } from "../src/pages/Finance/financeForm.js";

test("cash count accepts exact whole VND and rejects ambiguous values", () => {
  assert.equal(parseCashAmount(" 100000 "), 100000);
  assert.equal(parseCashAmount("0"), 0);
  for (const invalid of ["", " ", "-1", "1.5", "1e3", "1,000", "NaN", "9007199254740992"]) {
    assert.throws(() => parseCashAmount(invalid));
  }
});

test("refund keeps the same idempotency key when retried", () => {
  const input = { amount: "100000", method: "cash", reason: " Hủy kỳ tiếp theo ", idempotencyKey: "stable-refund-id", refundableAmount: 500000 };
  assert.deepEqual(buildRefundPayload(input), { amount: 100000, method: "cash", reason: "Hủy kỳ tiếp theo", idempotency_key: "stable-refund-id" });
  assert.deepEqual(buildRefundPayload(input), buildRefundPayload(input));
  assert.throws(() => buildRefundPayload({ ...input, amount: "0" }));
  assert.throws(() => buildRefundPayload({ ...input, amount: "500001" }));
  assert.throws(() => buildRefundPayload({ ...input, reason: " " }));
  assert.throws(() => buildRefundPayload({ ...input, method: "legacy_unknown" }));
});

test("legacy payment methods remain explicitly unknown", () => {
  assert.equal(paymentMethodLabels.legacy_unknown, "Không rõ (dữ liệu cũ)");
});
