import test from "node:test";
import assert from "node:assert/strict";
import { analysisPayload, canViewReportRevenue, reportStatistics, sessionSearchParams } from "../src/utils/coreAnalytics.js";

test("operational summary renders without revenue and keeps departure-only traffic", () => {
  const data = { data_scope: "operations", revenue: null, total_arrivals: 0, total_departures: 5, total_movements: 5 };
  assert.deepEqual(reportStatistics(data, "staff").map((row) => row.value), [0, 5, 5]);
  assert.equal(canViewReportRevenue(data, "manager"), false);
});

test("revenue rows are only presented for a management response and role", () => {
  const data = { data_scope: "management", total_arrivals: 1, total_departures: 0,
    revenue: { parking_revenue: 0, monthly_pass_revenue: 100000, refunds: 2000, total_revenue: 98000 } };
  assert.equal(reportStatistics(data, "staff").length, 2);
  assert.equal(reportStatistics(data, "unknown").length, 2);
  assert.deepEqual(reportStatistics(data, "manager").filter((row) => row.currency).map((row) => row.value), [0, 100000, 2000, 98000]);
  assert.equal(reportStatistics({ ...data, data_scope: "operations" }, "manager").length, 2);
});

test("session filters preserve dates and pagination without unrelated authority", () => {
  assert.deepEqual(sessionSearchParams({ limit: 25, offset: 50 }, { license_plate: "51A12345", status: "completed", date_from: "2026-09-01", date_to: "2026-09-08", site_id: 999 }),
    { limit: 25, offset: 50, license_plate: "51A12345", status: "completed", date_from: "2026-09-01", date_to: "2026-09-08" });
  assert.deepEqual(sessionSearchParams({ limit: 25, offset: 0 }, { status: "", date_from: "", date_to: "" }), { limit: 25, offset: 0 });
  assert.deepEqual(sessionSearchParams({ limit: 25, offset: 0 }, { license_plate: "30A-12345", session_id: "stay-id", status: "cancelled" }),
    { limit: 25, offset: 0, license_plate: "30A-12345", session_id: "stay-id", status: "cancelled" });
});

test("AI defaults use Vietnamese calendar and retain retry identity", () => {
  assert.deepEqual(analysisPayload({ kind: "question", period: "week", question: "  Còn chỗ không?  ", requestId: "same-retry-id" }, new Date("2026-09-08T17:30:00Z")),
    { kind: "question", period: "week", anchor_date: "2026-09-09", question: "Còn chỗ không?", request_id: "same-retry-id" });
});

test("report uses selected period without stale question or client statistics", () => {
  const result = analysisPayload({ kind: "report", period: "day", anchorDate: "2026-08-01", question: "Stale question", requestId: "new-id", parking_stats: { total: 999 } });
  assert.deepEqual(result, { kind: "report", period: "day", anchor_date: "2026-08-01", question: "", request_id: "new-id" });
});
