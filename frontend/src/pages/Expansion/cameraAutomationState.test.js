import test from "node:test";
import assert from "node:assert/strict";
import { framesForAutomation } from "./cameraAutomationState.js";

const now = Date.parse("2026-09-23T10:00:00+07:00");
const row = { id: "fresh", camera_id: 1, capture_source: "live_camera", review_status: "pending", captured_at: new Date(now - 1000).toISOString() };
test("only fresh live/edge frames from chosen camera enter bounded automation", () => {
  const rows = [row, { ...row, id: "file", capture_source: "manual_upload" }, { ...row, id: "foreign", camera_id: 2 },
    { ...row, id: "reviewed", review_status: "accepted" }, { ...row, id: "future", captured_at: new Date(now + 1).toISOString() },
    { ...row, id: "old", captured_at: new Date(now - 16000).toISOString() }, { ...row, id: "bad", captured_at: "invalid" }];
  assert.deepEqual(framesForAutomation(rows, 1, new Set(), now).map(row => row.id), ["fresh"]);
  assert.deepEqual(framesForAutomation(rows, 1, new Set(["fresh"]), now), []);
});
test("process at most four oldest eligible frames per tick", () => {
  const rows = Array.from({ length: 8 }, (_, index) => ({ ...row, id: String(index), captured_at: new Date(now - index * 1000).toISOString() }));
  assert.deepEqual(framesForAutomation(rows, 1, new Set(), now).map(row => row.id), ["7", "6", "5", "4"]);
});
