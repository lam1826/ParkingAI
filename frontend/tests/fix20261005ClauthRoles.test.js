// CL-AUTH #41: missing canonical roles can be restored, and the Users form never
// silently locks a new account to the admin role.
import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";
import { CANONICAL_ROLES, missingCanonicalRoles } from "../src/pages/Role/roleRestore.js";
import { autoSelectedRoleId } from "../src/pages/User/accountAssignment.js";

const source = (path) => readFile(new URL(`../src/${path}`, import.meta.url), "utf8");

test("missing canonical roles are detected case-insensitively, in a stable order", () => {
  assert.deepEqual(CANONICAL_ROLES.map((role) => role.name), ["admin", "manager", "staff", "customer"]);
  assert.deepEqual(missingCanonicalRoles([{ id: 1, name: "admin" }]).map((role) => role.name), ["manager", "staff", "customer"]);
  assert.deepEqual(missingCanonicalRoles([{ name: "Admin" }, { name: "STAFF" }, { name: "manager" }, { name: "customer" }]), []);
  assert.ok(missingCanonicalRoles([]).every((role) => role.description));
});

test("a single available role is preselected only when it is not admin", () => {
  assert.equal(autoSelectedRoleId([{ id: 1, name: "admin" }]), "");
  assert.equal(autoSelectedRoleId([{ id: 3, name: "staff" }]), 3);
  assert.equal(autoSelectedRoleId([{ id: 1, name: "admin" }, { id: 3, name: "staff" }]), "");
  assert.equal(autoSelectedRoleId([]), "");
});

test("Roles page offers Admin a restore action for missing canonical roles", async () => {
  const page = await source("pages/Role/RolePage.jsx");
  assert.match(page, /missingCanonicalRoles/);
  assert.match(page, /roleService\.create/);
  assert.match(page, /Khôi phục vai trò/);
  assert.match(page, /role === "admin"/);
});

test("Users form no longer auto-locks the role select to the only role", async () => {
  const dialog = await source("pages/User/components/UserDialog.jsx");
  assert.doesNotMatch(dialog, /roles\.length === 1 \? roles\[0\]\.id/);
  assert.doesNotMatch(dialog, /disabled=\{roles\.length === 1/);
  assert.match(dialog, /autoSelectedRoleId\(roles\)/);
});
