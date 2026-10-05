// CL-AUTH #3: Admin can finish staff/manager onboarding in the UI.
import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";
import {
  accountLabel, createAccountBody, createdAccountNotice, defaultAssignmentSiteId,
  eligibleSiteMembers, expectedAssignmentSite, memberDisplayName, siteAssignmentRole,
} from "../src/pages/User/accountAssignment.js";

const source = (path) => readFile(new URL(`../src/${path}`, import.meta.url), "utf8");
const roles = [{ id: 1, name: "admin" }, { id: 2, name: "staff" }, { id: 3, name: "manager" }, { id: 4, name: "customer" }];
const users = [
  { id: 7, username: "lan_staff", full_name: "Lan", is_active: true, role: { name: "staff" } },
  { id: 8, username: "minh_mgr", full_name: "Minh", is_active: true, role: { name: "manager" } },
  { id: 9, username: "locked_staff", full_name: "Khoa", is_active: false, role: { name: "staff" } },
  { id: 10, username: "khach", full_name: "Khach", is_active: true, role: { name: "customer" } },
  { id: 11, username: "root", full_name: "Root", is_active: true, role: { name: "admin" } },
];

test("only staff and manager accounts receive a lot permission", () => {
  assert.equal(siteAssignmentRole("staff"), "staff");
  assert.equal(siteAssignmentRole("Manager"), "manager");
  assert.equal(siteAssignmentRole("admin"), null);
  assert.equal(siteAssignmentRole("customer"), null);
});

test("the lot is preselected for single-lot and configured single-site installs", () => {
  assert.equal(defaultAssignmentSiteId([{ id: 5, name: "A" }]), "5");
  assert.equal(defaultAssignmentSiteId([{ id: 1 }, { id: 2 }], 2), "2");
  assert.equal(defaultAssignmentSiteId([{ id: 1 }, { id: 2 }], null), "");
  assert.equal(defaultAssignmentSiteId([{ id: 1 }, { id: 2 }], 9), "");
});

test("create body carries site_id only for operator roles with a chosen lot", () => {
  const form = { username: "a", full_name: "A", password: "x", is_active: true };
  assert.deepEqual(createAccountBody({ ...form, role_id: "2", site_id: "5" }, roles).site_id, 5);
  assert.equal(createAccountBody({ ...form, role_id: "2", site_id: "" }, roles).site_id, undefined);
  assert.equal(createAccountBody({ ...form, role_id: "4", site_id: "5" }, roles).site_id, undefined);
  assert.equal(createAccountBody({ ...form, role_id: "2", site_id: "5" }, roles).role_id, 2);
  const sites = [{ id: 5, name: "Bãi A" }];
  assert.equal(expectedAssignmentSite({ role_id: 2 }, roles, sites)?.name, "Bãi A");
  assert.equal(expectedAssignmentSite({ role_id: 4 }, roles, sites), null);
  assert.equal(expectedAssignmentSite({ role_id: 3, site_id: 6 }, roles, [{ id: 5 }, { id: 6, name: "Bãi B" }])?.name, "Bãi B");
  assert.match(createdAccountNotice({ id: 42, username: "lan_staff" }, sites[0]), /lan_staff \(mã #42\).*Bãi A/);
});

test("the grant picker lists active staff/manager accounts by name, and members show names", () => {
  const options = eligibleSiteMembers(users);
  assert.deepEqual(options.map((item) => item.id).sort(), [7, 8]);
  assert.match(options.find((item) => item.id === 7).label, /Lan \(lan_staff\)/);
  assert.equal(options.find((item) => item.id === 8).role, "manager");
  assert.equal(memberDisplayName(8, users), "Minh (minh_mgr)");
  assert.equal(memberDisplayName(99, users), "Tài khoản #99");
  assert.equal(accountLabel({ username: "same", full_name: "same" }), "same");
});

test("Users screen shows the account code and passes the lot on Admin create", async () => {
  const table = await source("pages/User/components/UserTable.jsx");
  assert.match(table, /#\$\{user\.id\}|#\{user\.id\}/);
  const dialog = await source("pages/User/components/UserDialog.jsx");
  assert.match(dialog, /Bãi phân công/);
  assert.match(dialog, /name="site_id"/);
  const hook = await source("pages/User/hooks/useUser.js");
  assert.match(hook, /createAccountBody/);
  assert.match(hook, /createdAccountNotice\(created/);
  assert.match(hook, /\/api\/v2\/sites|getSites/);
});

test("Site configuration grants by picking an account, not by typing a hidden numeric ID", async () => {
  const page = await source("pages/Expansion/SiteConfiguration.jsx");
  assert.doesNotMatch(page, /label="Mã tài khoản nhân sự" type="number"/);
  assert.match(page, /eligibleSiteMembers/);
  assert.match(page, /memberDisplayName/);
  assert.match(page, /label="Tài khoản nhân sự"/);
});
