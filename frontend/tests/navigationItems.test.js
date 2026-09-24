import test from "node:test";
import assert from "node:assert/strict";
import { navigationSections, navigationItemSelected, workspaceTabs } from "../src/utils/navigationItems.js";

const capabilities = { legacy_workspace_allowed: true, site_finance_enabled: true, site_analytics_enabled: true };
const paths = (groups) => groups.flatMap((group) => group.items.map((item) => item.path));

test("approved internal navigation groups every core screen within seven primary destinations", () => {
  for (const role of ["manager", "admin"]) {
    const groups = navigationSections(role, capabilities, true);
    assert.deepEqual(groups[0].items.map((item) => item.path), ["/", "/sites", "/parking-slots", "/history", "/customers", "/reports", "/vehicle-types"]);
    const reachable = new Set(paths(groups));
    for (const path of [...reachable]) for (const tab of workspaceTabs(path, role, capabilities)) reachable.add(tab.path);
    for (const path of ["/zones", "/monthly-passes", "/vehicles", "/price-configs", "/ai", "/finance", "/portal-admin", "/users"])
      assert.ok(reachable.has(path), `${role}: ${path}`);
    assert.equal(groups.find((group) => group.id === "extensions").collapsible, true);
    assert.ok(!paths(groups).includes("/reservations"), "staff cannot create customer bookings through navigation");
    assert.equal(new Set(paths(groups)).size, paths(groups).length);
  }
});

test("admin inherits all manager destinations and staff retains operations without administration", () => {
  const manager = paths(navigationSections("manager", capabilities, true));
  const admin = paths(navigationSections("admin", capabilities, true));
  assert.ok(manager.every((path) => admin.includes(path)));
  const staff = paths(navigationSections("staff", capabilities, true));
  for (const path of ["/", "/sites", "/history", "/reports", "/customers"]) assert.ok(staff.includes(path));
  for (const path of ["/users", "/roles", "/audit-logs", "/portal-admin"]) assert.ok(!staff.includes(path));
  assert.ok(!workspaceTabs("/customers", "staff", capabilities).some((tab) => tab.path === "/portal-admin"));
});

test("customer has four explicit tasks and query-aware selection survives payment redirects", () => {
  const customer = navigationSections("customer", capabilities, true);
  assert.deepEqual(paths(customer), ["/portal?tab=fees", "/reservations", "/portal?tab=tickets", "/portal?tab=support"]);
  const select = (search) => customer[0].items.filter((item) => navigationItemSelected({ pathname: "/portal", search }, item)).map((item) => item.path);
  assert.deepEqual(select(""), ["/portal?tab=fees"]);
  assert.deepEqual(select("?tab=support"), ["/portal?tab=support"]);
  assert.deepEqual(select("?order=private-order-id"), ["/portal?tab=tickets"]);
  assert.deepEqual(select("?tab=purchase&kind=monthly"), ["/portal?tab=tickets"]);
  assert.deepEqual(workspaceTabs("/ai", "customer", capabilities), []);
});

test("unapproved legacy workspaces remain hidden and grouped selection is exact", () => {
  const scopedOnly = paths(navigationSections("admin", { ...capabilities, legacy_workspace_allowed: false }, true));
  assert.ok(scopedOnly.includes("/sites") && scopedOnly.includes("/history"));
  assert.ok(!scopedOnly.includes("/vehicle-types") && !scopedOnly.includes("/customers"));
  const lot = navigationSections("manager", capabilities, true)[0].items.find((item) => item.path === "/parking-slots");
  assert.equal(navigationItemSelected({ pathname: "/zones", search: "" }, lot), true);
  assert.equal(navigationItemSelected({ pathname: "/zones-private", search: "" }, lot), false);
  assert.deepEqual(navigationSections("unknown", capabilities, true), []);
});

test("admin has scoped site configuration while account tabs retain the manager boundary", () => {
  const adminGroups = navigationSections("admin", capabilities, true);
  const management = adminGroups.find(group => group.id === "management").items;
  const configuration = management.find(item => item.path === "/site-settings");
  assert.equal(configuration.icon, "settings");
  assert.equal(configuration.scoped, true);
  assert.ok(paths(navigationSections("admin", { ...capabilities, legacy_workspace_allowed: false }, true)).includes("/site-settings"));
  for (const role of ["manager", "staff", "customer"]) assert.ok(!paths(navigationSections(role, capabilities, true)).includes("/site-settings"));
  const accounts = management.find(item => item.path === "/users");
  assert.equal(navigationItemSelected({ pathname: "/roles", search: "" }, accounts), true);
  for (const role of ["admin", "manager"]) assert.deepEqual(workspaceTabs("/users", role, capabilities).map(item => item.path), ["/users", "/roles"]);
  assert.deepEqual(workspaceTabs("/users", "staff", capabilities), []);
  assert.deepEqual(workspaceTabs("/roles", "manager", { ...capabilities, legacy_workspace_allowed: false }), []);
});
