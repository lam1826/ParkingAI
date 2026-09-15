import test from "node:test";
import assert from "node:assert/strict";
import { corePermissions } from "../src/constants/corePermissions.js";
import { canShowMenuItem } from "../src/utils/menuPermissions.js";

test("staff can read core catalogs while management mutations fail closed", () => {
  for (const role of ["staff", "customer", "unknown", undefined]) {
    assert.equal(Object.values(corePermissions(role)).some(Boolean), false, String(role));
  }
  for (const role of ["manager", "admin"]) {
    assert.equal(Object.values(corePermissions(role)).every(Boolean), true, role);
  }
});

test("one-site navigation keeps every core catalog reachable for its authorized roles", () => {
  const capabilities = { legacy_workspace_allowed: true, site_finance_enabled: true };
  for (const role of ["staff", "manager"]) {
    for (const path of ["/zones", "/parking-slots", "/vehicle-types", "/price-configs", "/customers", "/vehicles", "/monthly-passes"]) {
      assert.equal(canShowMenuItem({ path, role: "staff" }, role, capabilities, true), true, `${role}: ${path}`);
    }
  }
  for (const path of ["/users", "/audit-logs", "/roles"]) {
    assert.equal(canShowMenuItem({ path, role: "manager" }, "manager", capabilities, true), true, path);
    assert.equal(canShowMenuItem({ path, role: "manager" }, "staff", capabilities, true), false, path);
  }
});

test("one-site display never bypasses backend workspace denial or missing capability", () => {
  for (const capabilities of [null, {}, { legacy_workspace_allowed: false }]) {
    for (const role of ["staff", "manager", "admin"]) {
      assert.equal(canShowMenuItem({ path: "/monthly-passes", role: "staff" }, role, capabilities, true), false);
      assert.equal(canShowMenuItem({ path: "/sites", role: "staff", scoped: true }, role, capabilities, true), true);
    }
  }
});

test("finance remains reachable when the scoped finance feature is unavailable", () => {
  const item = { path: "/finance", role: "staff" };
  assert.equal(canShowMenuItem(item, "staff", { legacy_workspace_allowed: true }, true), true);
  assert.equal(canShowMenuItem(item, "staff", { legacy_workspace_allowed: true, site_finance_enabled: true }, true), false);
  assert.equal(canShowMenuItem(item, "staff", { legacy_workspace_allowed: true, site_finance_enabled: true }, false), true);
});
