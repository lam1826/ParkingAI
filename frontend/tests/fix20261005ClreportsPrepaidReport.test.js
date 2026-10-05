import test from "node:test";
import assert from "node:assert/strict";
import { reportStatistics } from "../src/utils/coreAnalytics.js";

// #35: hour/day package revenue is part of net revenue, so it must have its own row.
test("report revenue rows include hour/day package revenue and reconcile with net", () => {
  const data = { data_scope: "management", total_arrivals: 0, total_departures: 0, total_movements: 0,
    revenue: { parking_revenue: 5000, monthly_pass_revenue: 100000, prepaid_revenue: 12000, refunds: 2000,
      total_revenue: 115000, demo_receipts: 0, demo_refunds: 0 } };
  const rows = reportStatistics(data, "manager").filter((row) => row.currency);
  assert.deepEqual(rows.map((row) => row.id), ["parking", "monthly", "prepaid", "refunds", "net"]);
  assert.equal(rows.find((row) => row.id === "prepaid").label, "Thu vé giờ/ngày");
  const parts = rows.filter((row) => row.id !== "net")
    .reduce((sum, row) => sum + (row.id === "refunds" ? -row.value : row.value), 0);
  assert.equal(parts, rows.find((row) => row.id === "net").value);
});

test("older saved AI inputs without prepaid_revenue do not show an empty prepaid row", () => {
  const data = { data_scope: "management", total_arrivals: 1, total_departures: 0,
    revenue: { parking_revenue: 0, monthly_pass_revenue: 100000, refunds: 2000, total_revenue: 98000 } };
  assert.deepEqual(reportStatistics(data, "manager").filter((row) => row.currency).map((row) => row.id),
    ["parking", "monthly", "refunds", "net"]);
});
