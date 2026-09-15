import test from "node:test";
import assert from "node:assert/strict";
import { getMonthlyPassStatus } from "../src/utils/monthlyPassStatus.js";

const now = new Date("2026-09-15T17:00:00Z"); // September 16, midnight in Vietnam.
const pass = { is_active: true, start_date: "2026-09-01", end_date: "2026-09-30" };

test("monthly pass remains valid through its inclusive Vietnam end date", () => {
  assert.equal(getMonthlyPassStatus({ ...pass, end_date: "2026-09-15" }, now).label, "Hết hạn");
  assert.equal(getMonthlyPassStatus({ ...pass, end_date: "2026-09-16" }, now).label, "Sắp hết hạn");
  assert.equal(getMonthlyPassStatus({ ...pass, end_date: "2026-09-15" }, new Date("2026-09-15T16:59:59Z")).label, "Sắp hết hạn");
});

test("near-expiry warning includes seven days ahead and excludes eight", () => {
  assert.equal(getMonthlyPassStatus({ ...pass, end_date: "2026-09-23" }, now).color, "warning");
  assert.equal(getMonthlyPassStatus({ ...pass, end_date: "2026-09-24" }, now).color, "success");
  assert.equal(getMonthlyPassStatus({ ...pass, start_date: "2026-09-17", end_date: "2026-09-23" }, now).label, "Chưa đến hạn");
});

test("inactive and invalid validity dates never appear active", () => {
  assert.equal(getMonthlyPassStatus({ ...pass, is_active: false }, now).label, "Ngừng hoạt động");
  for (const end_date of [undefined, "2026-02-30", "invalid", "2026-08-31"]) {
    assert.equal(getMonthlyPassStatus({ ...pass, end_date }, now).label, "Chưa rõ hiệu lực");
  }
});
