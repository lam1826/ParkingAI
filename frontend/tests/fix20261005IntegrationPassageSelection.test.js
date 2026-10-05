import test from "node:test";
import assert from "node:assert/strict";
import { passageSelection } from "../src/pages/Expansion/operationsState.js";

// Review 05/10/2026 #74 — root integration of the CX-VISION selection guard.
const entered = { state: "entered", session_id: "s-new", license_plate: "51K-111.11" };
const auto = { updateSelection: false, automatic: true, allowSelection: true, cameraId: 7 };

test("#74 automatic frame selects the new stay when the operator has nothing selected", () => {
  const next = passageSelection(entered, auto, null);
  assert.equal(next.refresh, true);
  assert.equal(next.action, "select");
  assert.deepEqual(next.row, { id: "s-new", license_plate: "51K-111.11", status: "active", selectionOrigin: "camera", selectionCameraId: 7 });
});

test("#74 automatic frame never replaces a stay the operator picked manually", () => {
  const manual = { id: "s-old", license_plate: "30A-999.99" };
  const next = passageSelection(entered, auto, manual);
  assert.equal(next.action, "none");
  assert.equal(next.refresh, true, "data still refreshes after an admission");
});

test("#74 automatic frame may replace a selection that the camera itself made", () => {
  const cameraPick = { id: "s-old", selectionOrigin: "camera", selectionCameraId: 7 };
  assert.equal(passageSelection(entered, auto, cameraPick).action, "select");
});

test("#74 a stopped loop (allowSelection false) refreshes but never selects", () => {
  const next = passageSelection(entered, { ...auto, allowSelection: false }, null);
  assert.deepEqual(next, { refresh: true, action: "none" });
});

test("#74 an explicit 'Xem phí xe này' click is a manual selection without camera marker", () => {
  const next = passageSelection(entered, { updateSelection: true, explicit: true, cameraId: 7 }, { id: "s-old" });
  assert.equal(next.action, "select");
  assert.equal(next.row.selectionOrigin, undefined);
});

test("#74 exited clears the selection only when it is the departing stay", () => {
  const exited = { state: "exited", session_id: "s-old" };
  assert.equal(passageSelection(exited, auto, { id: "s-old", selectionOrigin: "camera" }).action, "clear");
  assert.equal(passageSelection(exited, auto, { id: "s-other", selectionOrigin: "camera" }).action, "none");
  assert.equal(passageSelection(exited, { updateSelection: true }, { id: "s-other" }).action, "none");
});

test("#74 non-session results (manual review, waiting) never select", () => {
  assert.deepEqual(passageSelection({ state: "manual" }, auto, null), { refresh: false, action: "none" });
});
