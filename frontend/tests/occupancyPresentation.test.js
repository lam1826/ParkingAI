import test from "node:test";
import assert from "node:assert/strict";
import { normalizedPoint, occupancyIsCurrent, visibleReadings, occupancyReason, regionDraft } from "../src/pages/Expansion/occupancyPresentation.js";

test("pointer coordinates normalize independently of viewport size and reject outside/invalid bounds", () => {
  assert.deepEqual(normalizedPoint(150, 100, { left: 50, top: 20, width: 200, height: 160 }), [.5, .5]);
  assert.equal(normalizedPoint(20, 100, { left: 50, top: 20, width: 200, height: 160 }), null);
  assert.equal(normalizedPoint(150, 100, { left: 50, top: 20, width: 0, height: 160 }), null);
});

test("draft regions preserve independent polygons and reject missing or duplicate vertices", () => {
  const points = [[.1, .1], [.4, .1], [.4, .7]];
  const region = regionDraft("2", points);
  points[0][0] = .9;
  assert.deepEqual(region, { slot_id: 2, polygon: [[.1, .1], [.4, .1], [.4, .7]] });
  assert.throws(() => regionDraft(2, [[0, 0], [0, 0], [1, 1]]));
  assert.throws(() => regionDraft(2, [[0, 0], [1, 1]]));
  assert.throws(() => regionDraft(0, points));
});

test("stored occupied/empty state becomes unknown at server expiry even before the next poll", () => {
  const data = { server_now: "2026-09-15T10:00:00+07:00", valid_until: "2026-09-15T10:00:30+07:00", readings: [
    { slot_id: 1, state: "occupied", mismatch: true, reason: null },
    { slot_id: 2, state: "unknown", mismatch: null, reason: "reference_expired" },
  ] };
  assert.equal(occupancyIsCurrent(data, 29999), true);
  assert.equal(occupancyIsCurrent(data, 30000), false);
  assert.equal(visibleReadings(data, 30000)[0].state, "unknown");
  assert.equal(visibleReadings(data, 30000)[0].mismatch, null);
  assert.equal(visibleReadings(data, 30000)[1].reason, "reference_expired");
  assert.equal(data.readings[0].state, "occupied");
  assert.equal(occupancyIsCurrent(data, -1), false);
  assert.equal(occupancyIsCurrent({}), false);
});

test("unknown causes are explained without presenting model score as measured accuracy", () => {
  assert.match(occupancyReason("reference_expired"), /ảnh nền mới/);
  assert.match(occupancyReason("insufficient_history"), /thêm ảnh mới/);
  assert.match(occupancyReason("lighting_changed"), /Ánh sáng/);
  assert.equal(occupancyReason(null), "");
});
