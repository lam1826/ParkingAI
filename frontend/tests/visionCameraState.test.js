import test from "node:test";
import assert from "node:assert/strict";
import { cameraHealthText, cameraWriteBody, canManageCameras } from "../src/pages/Expansion/visionCameraState.js";

test("camera administration requires both account and current site management rights", () => {
  assert.equal(canManageCameras("manager", "manager"), true);
  assert.equal(canManageCameras("admin", "admin"), true);
  assert.equal(canManageCameras("manager", "staff"), false);
  assert.equal(canManageCameras("staff", "manager"), false);
  assert.equal(canManageCameras("customer", "manager"), false);
  assert.equal(canManageCameras("admin", undefined), false);
});

test("health describes received images and inactive cameras override stale health metadata", () => {
  assert.equal(cameraHealthText({ is_active: true, health: "unseen" }), "Chưa nhận ảnh");
  assert.equal(cameraHealthText({ is_active: true, health: "recent" }), "Có ảnh mới");
  assert.equal(cameraHealthText({ is_active: true, health: "stale" }), "Chưa có ảnh mới — kiểm tra kết nối");
  assert.equal(cameraHealthText({ is_active: false, health: "recent" }), "Ngừng hoạt động");
  assert.equal(cameraHealthText({ is_active: true }), "Chưa có thông tin nhận ảnh");
});

test("camera update changes only editable configuration, never scope, health or credentials", () => {
  const form = { name: " Làn vào ", direction: "entry", retention_hours: "24", is_active: true, site_id: 99, zone_id: 88, token: "ignored", health: "recent" };
  assert.deepEqual(cameraWriteBody(form, { editing: true }), { name: "Làn vào", direction: "entry", retention_hours: 24, is_active: true });
  assert.deepEqual(cameraWriteBody(form, { siteId: "1" }), { name: "Làn vào", direction: "entry", retention_hours: 24, is_active: true, site_id: 1, zone_id: null });
});

test("malformed camera settings are rejected before a write", () => {
  const form = { name: "Camera", direction: "exit", retention_hours: 24, is_active: false };
  for (const patch of [{ retention_hours: 0 }, { retention_hours: 73 }, { retention_hours: 1.5 }, { retention_hours: "bad" }, { name: " " }, { direction: "both" }, { is_active: "false" }]) {
    assert.throws(() => cameraWriteBody({ ...form, ...patch }, { editing: true }));
  }
  assert.throws(() => cameraWriteBody(form, { siteId: 0 }));
});
