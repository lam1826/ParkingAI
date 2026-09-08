import test from "node:test";
import assert from "node:assert/strict";
import { analysisPayload, sessionSearchParams } from "../src/utils/coreAnalytics.js";

test("session filters preserve dates and pagination without unrelated authority", () => {
  assert.deepEqual(sessionSearchParams({ limit: 25, offset: 50 }, { license_plate: "51A12345", status: "completed", date_from: "2026-09-01", date_to: "2026-09-08", site_id: 999 }),
    { limit: 25, offset: 50, license_plate: "51A12345", status: "completed", date_from: "2026-09-01", date_to: "2026-09-08" });
  assert.deepEqual(sessionSearchParams({ limit: 25, offset: 0 }, { status: "", date_from: "", date_to: "" }), { limit: 25, offset: 0 });
});

test("AI defaults use Vietnamese calendar and retain retry identity", () => {
  assert.deepEqual(analysisPayload({ kind: "question", period: "week", question: "  Còn chỗ không?  ", requestId: "same-retry-id" }, new Date("2026-09-08T17:30:00Z")),
    { kind: "question", period: "week", anchor_date: "2026-09-09", question: "Còn chỗ không?", request_id: "same-retry-id" });
});

test("report uses selected period without stale question or client statistics", () => {
  const result = analysisPayload({ kind: "report", period: "day", anchorDate: "2026-08-01", question: "Stale question", requestId: "new-id", parking_stats: { total: 999 } });
  assert.deepEqual(result, { kind: "report", period: "day", anchor_date: "2026-08-01", question: "", request_id: "new-id" });
});
