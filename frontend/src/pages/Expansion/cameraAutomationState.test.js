import test from "node:test";
import assert from "node:assert/strict";
import { framesForAutomation, hasRecentEdgeFrames } from "./cameraAutomationState.js";

const now = Date.parse("2026-09-23T10:00:00+07:00");
const row = { id: "fresh", camera_id: 1, capture_source: "live_camera", review_status: "pending", captured_at: new Date(now - 1000).toISOString() };
test("only fresh live/edge frames from chosen camera enter bounded automation", () => {
  const rows = [row, { ...row, id: "file", capture_source: "manual_upload" }, { ...row, id: "foreign", camera_id: 2 },
    { ...row, id: "reviewed", review_status: "accepted" }, { ...row, id: "future", captured_at: new Date(now + 5001).toISOString() },
    { ...row, id: "old", captured_at: new Date(now - 16000).toISOString() }, { ...row, id: "bad", captured_at: "invalid" }];
  assert.deepEqual(framesForAutomation(rows, 1, new Set(), now).map(row => row.id), ["fresh"]);
  assert.deepEqual(framesForAutomation(rows, 1, new Set(["fresh"]), now), []);
});
test("process at most four oldest eligible frames per tick", () => {
  const rows = Array.from({ length: 8 }, (_, index) => ({ ...row, id: String(index), captured_at: new Date(now - index * 1000).toISOString() }));
  assert.deepEqual(framesForAutomation(rows, 1, new Set(), now).map(row => row.id), ["7", "6", "5", "4"]);
});

test("source choice isolates native webcam from external edge events", () => {
  const rows = [row, { ...row, id: "edge", capture_source: "edge" }];
  assert.deepEqual(framesForAutomation(rows, 1, new Set(), now, 15, "live_camera").map(item => item.id), ["fresh"]);
  assert.deepEqual(framesForAutomation(rows, 1, new Set(), now, 15, "edge").map(item => item.id), ["edge"]);
});

test("edge source requires actual recent edge receipts, not token or webcam activity", () => {
  const edge = { ...row, capture_source: "edge", observed_at: new Date(now - 1000).toISOString() };
  assert.equal(hasRecentEdgeFrames([], 1, now), false);
  assert.equal(hasRecentEdgeFrames([{ ...edge, capture_source: "live_camera" }], 1, now), false);
  assert.equal(hasRecentEdgeFrames([edge], 2, now), false);
  for (const observed_at of ["bad", new Date(now + 1).toISOString(), new Date(now - 30000).toISOString()]) {
    assert.equal(hasRecentEdgeFrames([{ ...edge, observed_at }], 1, now), false);
  }
  assert.equal(hasRecentEdgeFrames([edge], 1, now), true);
});
