import assert from "node:assert/strict";
import fs from "node:fs";
import test from "node:test";

import { loadPeriodReport } from "../src/pages/Report/services/loadPeriodReport.js";


test("loadPeriodReport gửi cùng một period cho revenue và traffic", async () => {
  const calls = [];
  const fakeReportClient = {
    async getRevenueReport(params) {
      calls.push({ endpoint: "revenue", params });
      return { total_trips: 1 };
    },
    async getTrafficReport(params) {
      calls.push({ endpoint: "traffic", params });
      return { traffic_by_hour: [] };
    },
  };

  const now = new Date("2026-08-31T17:00:00Z"); // 01/09/2026 00:00 giờ VN
  const result = await loadPeriodReport(fakeReportClient, "month", now);

  assert.deepEqual(calls, [
    { endpoint: "revenue", params: { period: "month", anchor_date: "2026-09-01" } },
    { endpoint: "traffic", params: { period: "month", anchor_date: "2026-09-01" } },
  ]);
  assert.deepEqual(result, {
    revenue: { total_trips: 1 },
    traffic: { traffic_by_hour: [] },
    anchorDate: "2026-09-01",
  });
});


test("ReportPage tái sử dụng ngày neo đã tải khi xuất file", () => {
  const pageSource = fs.readFileSync(
    new URL("../src/pages/Report/ReportPage.jsx", import.meta.url),
    "utf8",
  );
  const serviceSource = fs.readFileSync(
    new URL("../src/pages/Report/services/reportService.js", import.meta.url),
    "utf8",
  );

  assert.match(pageSource, /setReportAnchor\(anchorDate\)/);
  assert.match(
    pageSource,
    /downloadReport\(format,\s*period,\s*reportAnchor\)/,
  );
  assert.match(pageSource, /parking-report-\$\{period\}-\$\{reportAnchor\}/);
  assert.match(serviceSource, /anchor_date:\s*anchorDate/);
});
