import assert from "node:assert/strict";
import { test } from "node:test";
import { actionTargets, mapLinks, planDuration, textOrPlaceholder } from "./publicSiteState.js";

test("missing information is shown as not published, never invented", () => {
  assert.equal(textOrPlaceholder(null), "Chưa cập nhật");
  assert.equal(textOrPlaceholder("  "), "Chưa cập nhật");
  assert.equal(textOrPlaceholder(" 06:00–22:00 "), "06:00–22:00");
  assert.deepEqual(mapLinks({ address: null, location: null }), { kind: "none", directions: null, open: null, embed: null });
});

test("map links prefer coordinates, fall back to the address, and need no API key", () => {
  const byPoint = mapLinks({ address: "1 Đường A", location: { latitude: 10.7769, longitude: 106.7009 } });
  assert.equal(byPoint.kind, "coordinates");
  assert.match(byPoint.directions, /^https:\/\/www\.google\.com\/maps\/dir\/\?api=1&destination=10\.7769%2C106\.7009$/);
  assert.match(byPoint.embed, /^https:\/\/www\.openstreetmap\.org\/export\/embed\.html\?bbox=/);
  assert.ok(!/key=/.test(byPoint.embed));
  const byAddress = mapLinks({ address: "12 Nguyễn Huệ", location: { latitude: "x", longitude: null } });
  assert.equal(byAddress.kind, "address");
  assert.equal(byAddress.embed, null);
  assert.match(byAddress.open, /query=12%20Nguy/);
});

test("plan durations and call-to-action continuations", () => {
  assert.equal(planDuration({ product_kind: "monthly", duration_days: 30 }), "30 ngày");
  assert.equal(planDuration({ product_kind: "hourly", duration_minutes: 120 }), "2 giờ");
  assert.equal(planDuration({ product_kind: "daily" }), "24 giờ");
  const anonymous = actionTargets({ plans: [{ product_kind: "hourly" }] }, null);
  assert.equal(anonymous.purchase.to, "/login?next=" + encodeURIComponent("/portal?tab=purchase&kind=hourly"));
  assert.equal(anonymous.signedIn, false);
  assert.equal(actionTargets({ plans: [] }, { role: "customer" }).purchase.to, "/portal?tab=purchase");
  assert.equal(actionTargets({ plans: [] }, { role: "staff" }).purchase.to, "/sites");
});
