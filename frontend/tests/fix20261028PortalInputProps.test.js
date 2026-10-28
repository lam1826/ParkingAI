// Fix 28/10/2026, lane FB, item N-1: MUI 9.2 TextField no longer forwards the
// top-level `inputProps` prop to the <input> (only `slotProps.htmlInput` is wired,
// see node_modules/@mui/material/TextField/TextField.js), so the client-side
// min/max/maxLength of the customer portal and portal admin forms did nothing.
import test from "node:test";
import assert from "node:assert/strict";
import { readdirSync, readFileSync } from "node:fs";
import { createRequire } from "node:module";
import { fakeApi, fakeRouter, findAll, h, loadReal, R, settle, STUBS } from "./fix20261005IntegrationHarness.js";

const require = createRequire(import.meta.url);
const source = (name) => readFileSync(new URL(`../src/pages/Expansion/${name}`, import.meta.url), "utf8");

// Every lane-FB file; none may keep a TextField `inputProps`.
const OWNED = ["CustomerPortal.jsx", "PortalPurchase.jsx", "PortalOrderDetails.jsx", "PortalSessionDetails.jsx", "CustomerFees.jsx",
  "CustomerSupportPanel.jsx", "PortalAdminPage.jsx", "RefundAdminPanel.jsx", "OnlinePaymentPanel.jsx", "OnlinePaymentReview.jsx",
  "ReservationsPage.jsx", "SupportAdminPanel.jsx", "SessionFeePayment.jsx", "SiteFinance.jsx", "SiteFinancePage.jsx"];

test("N-1 MUI 9.2 applies slotProps.htmlInput to the rendered <input>", () => {
  const React = require("react");
  const { renderToStaticMarkup } = require("react-dom/server");
  const TextField = require("@mui/material/TextField").default;
  const html = renderToStaticMarkup(React.createElement(TextField, { label: "Biển số", value: "", onChange() {}, slotProps: { htmlInput: { maxLength: 20, min: 1 } } }));
  const input = html.match(/<input[^>]*>/)[0];
  assert.match(input, /maxLength="20"/);
  assert.match(input, /min="1"/);
});

test("N-1 no customer-portal or portal-admin TextField passes the ignored inputProps", () => {
  const offenders = OWNED.filter((name) => /\binputProps\s*=/.test(source(name)));
  assert.deepEqual(offenders, []);
});

test("N-1 no screen anywhere in src passes the ignored inputProps", () => {
  // Integration step: the remaining screens (insights, occupancy, vision, profile, register, settings).
  const root = new URL("../src/", import.meta.url);
  const offenders = readdirSync(root, { recursive: true })
    .filter((name) => /\.jsx?$/.test(name) && /\binputProps\s*=/.test(readFileSync(new URL(name.replaceAll("\\", "/"), root), "utf8")));
  assert.deepEqual(offenders, []);
  const pages = (name) => readFileSync(new URL(`../src/pages/${name}`, import.meta.url), "utf8");
  const moved = {
    "Register/RegisterPage.jsx": [["minLength: 2, maxLength: 100", 1], ["minLength: 3, maxLength: 50", 1], ["minLength: 8, maxLength: 72", 1]],
    "Profile/ProfilePage.jsx": [["minLength: 2, maxLength: 100", 1], ["minLength: 3, maxLength: 50", 1]],
    "Setting/SettingPage.jsx": [["minLength: 8, maxLength: 72", 1]],
    "Expansion/OccupancyPage.jsx": [["min: 0, max: 1, step: .001", 2], ["min, max, step", 1]],
    "Expansion/InsightsPage.jsx": [["min: 5, max: 600", 1], ["min: 1, max: 50", 2]],
    "Expansion/VisionPage.jsx": [["maxLength: 20", 1], ["maxLength: 100", 1], ["min: 1, max: 72, step: 1", 1]],
  };
  for (const [name, constraints] of Object.entries(moved)) {
    for (const [constraint, count] of constraints) {
      assert.equal(pages(name).split(`slotProps={{ htmlInput: { ${constraint} } }}`).length - 1, count, `${name}: slotProps.htmlInput { ${constraint} }`);
    }
  }
});

test("N-1 every former inputProps constraint is now passed as slotProps.htmlInput", () => {
  const expected = {
    "CustomerPortal.jsx": [["maxLength: 100", 1], ["maxLength: 20", 2], ["maxLength: 500", 2]],
    "PortalAdminPage.jsx": [["maxLength: 100", 1], ["min: 1, max: 366, step: 1", 1], ["min: 60, max: 1440, step: 60", 1],
      ["min: 1, max: Number.MAX_SAFE_INTEGER, step: 1", 1], ["maxLength: 500", 1]],
    "PortalOrderDetails.jsx": [["maxLength: 500", 1]],
    "OnlinePaymentPanel.jsx": [["minLength: 3, maxLength: 200", 1]],
    "OnlinePaymentReview.jsx": [["minLength: 3, maxLength: 500", 1], ["minLength: 3, maxLength: 100", 1]],
  };
  for (const [name, constraints] of Object.entries(expected)) {
    const text = source(name);
    for (const [constraint, count] of constraints) {
      const found = text.split(`slotProps={{ htmlInput: { ${constraint} } }}`).length - 1;
      assert.equal(found, count, `${name}: slotProps.htmlInput { ${constraint} }`);
    }
  }
});

test("N-1 the rendered customer profile fields carry their limits in slotProps.htmlInput", async () => {
  fakeRouter.location.search = "tab=tickets&view=profile";
  fakeApi.setHandler(async (method, url) => {
    if (method === "get" && url === "/api/v2/me/profile") return { linked: false };
    if (method === "get") return { items: [] };
    throw new Error(`unexpected ${method} ${url}`);
  });
  const leaves = Object.fromEntries(["PortalPurchase", "PortalOrderDetails", "PortalSessionDetails", "CustomerSupportPanel", "CustomerFees"]
    .map((name) => [`pages/Expansion/${name}.jsx`, STUBS.empty]));
  const { default: CustomerPortal } = await loadReal("pages/Expansion/CustomerPortal.jsx", leaves);
  const root = R.createRoot();
  root.render(h(CustomerPortal));
  await settle(root);
  const field = (label) => findAll(root, (node) => node.type === "mui-textfield" && node.props.label === label)[0];
  for (const [label, maxLength] of [["Họ và tên", 100], ["Số điện thoại", 20], ["Thông tin hỗ trợ xác minh", 500]]) {
    assert.ok(field(label), `field ${label} is rendered`);
    assert.equal(field(label).props.inputProps, undefined, `${label}: no ignored inputProps`);
    assert.equal(field(label).props.slotProps?.htmlInput?.maxLength, maxLength, `${label}: maxLength reaches the input`);
  }
  root.unmount();
});
