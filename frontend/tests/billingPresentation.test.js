import assert from "node:assert/strict";
import test from "node:test";
import { billingPresentation, formatBillableDuration, prepaidPresentation } from "../src/pages/ParkingSession/billingPresentation.js";

const basis = { policy_version: "entry-v1", rate_source: "entry_snapshot", rate_id: 1, unit_price: 10000,
  ticket_type: "HOURLY", effective_date: "2026-09-15", billable_from: "2026-09-15T08:00:00+07:00", billable_seconds: 3601, billable_blocks: 2 };

test("billing details preserve the server's rounded blocks and exact charge duration", () => {
  const result = billingPresentation(basis);
  assert.equal(result.available, true);
  assert.equal(result.sourceLabel, "Giá ghi nhận lúc xe vào");
  assert.equal(result.rows.find((row) => row.label === "Thời gian tính phí").value, "1 giờ 1 giây");
  assert.equal(result.rows.find((row) => row.label === "Số đơn vị tính phí").value, "2 × 1 giờ");
  assert.equal("parking_fee" in result, false);
});

test("zero-cost and fully covered stays retain legitimate zeroes", () => {
  const result = billingPresentation({ ...basis, unit_price: 0, billable_seconds: 0, billable_blocks: 0 });
  assert.equal(result.available, true);
  assert.equal(result.rows[0].value, "0 VND / giờ");
  assert.equal(result.rows.find((row) => row.label === "Thời gian tính phí").value, "0 giây");
});

test("day pricing is a 24-hour block and old policy remains explicitly labelled", () => {
  const result = billingPresentation({ ...basis, ticket_type: "DAILY", policy_version: "legacy-current-rate", rate_source: "legacy_current_rate" });
  assert.equal(result.legacy, true);
  assert.equal(result.rows[0].value, "10.000 VND / 24 giờ");
  assert.equal(formatBillableDuration(86461), "1 ngày 1 phút 1 giây");
});

test("missing historical basis or malformed metadata never fabricates a snapshot", () => {
  for (const value of [null, undefined, {}, { ...basis, unit_price: -1 }, { ...basis, billable_from: "invalid" }, { ...basis, policy_version: "unknown" }]) {
    assert.equal(billingPresentation(value).available, false);
  }
});

test("prepaid basis is labelled at purchase time and remains separate from the paid package", () => {
  const result = billingPresentation({ ...basis, policy_version: "prepaid-window-v1", rate_source: "prepaid_snapshot" });
  assert.equal(result.available, true);
  assert.equal(result.prepaid, true);
  assert.equal(result.sourceLabel, "Giá phụ trội đã chốt khi mua gói");
  assert.equal(billingPresentation({ ...basis, policy_version: "prepaid-window-v1" }).available, false);
  const prepaid = prepaidPresentation({ order_id: "order", amount: 30000, payment_mode: "demo", start_at: "2026-09-15T10:00:00+07:00", end_at: "2026-09-15T12:00:00+07:00" });
  assert.equal(prepaid.amount, "30.000 VND");
  assert.equal(prepaid.demo, true);
  assert.equal("parking_fee" in prepaid, false);
  assert.equal(prepaidPresentation(null).available, false);
  assert.equal(prepaidPresentation({ order_id: "order", amount: -1 }).available, false);
});
