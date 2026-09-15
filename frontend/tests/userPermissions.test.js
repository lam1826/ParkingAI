import assert from "node:assert/strict";
import test from "node:test";
import { assignableRoles, canCreateUser, canEditUser } from "../src/constants/userPermissions.js";

test("manager can manage other staff without granting higher roles or changing self", () => {
  const manager = { id: 2, role: "manager" };
  const roles = [{ id: 1, name: "staff" }, { id: 2, name: "manager" }, { id: 3, name: "admin" }];
  assert.equal(canCreateUser(manager), true);
  assert.deepEqual(assignableRoles(manager, roles), [roles[0]]);
  assert.equal(canEditUser(manager, { id: 5, role: roles[0] }), true);
  for (const target of [{ id: 2, role: roles[0] }, { id: 5, role: roles[1] }, { id: 5, role: roles[2] }, { id: 5, role: "customer" }]) {
    assert.equal(canEditUser(manager, target), false);
  }
});

test("unknown or staff identities cannot inherit stored superuser claims", () => {
  for (const user of [null, { role: "staff", is_superuser: true }, { role: "unknown" }]) {
    assert.equal(canCreateUser(user), false);
    assert.equal(canEditUser(user, { role: "staff" }), false);
    assert.deepEqual(assignableRoles(user, [{ id: 1, name: "staff" }]), []);
  }
});
