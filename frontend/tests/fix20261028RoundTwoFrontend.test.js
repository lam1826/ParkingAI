// Fix 28/10/2026, round-2 tester findings on the internal screens (fixer round 1).
// B-05 Vietnamese validation messages, B-08 one POST per double click, B-12 legacy sessions grid,
// B-17 roles subtitle, B-18 delete confirmation, B-19 signed-in accounts leave /login, R1-EXCEL
// Excel export button. Real components run under the shared harness (fake HTTP client, no network);
// layout-only items (R2-07, B-14, B-09, B-10, R2-02, B-16) are pinned on their source.
import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { buttonsNamed, fakeApi, findAll, fire, h, loadReal, R, settle, setGlobal, STUBS, stub, textOf } from "./fix20261005IntegrationHarness.js";

const source = (file) => readFileSync(new URL(`../src/${file}`, import.meta.url), "utf8");

const CRUD_MUI = stub("fix20261028-crud-mui", `
const host = (tag) => function Mui({ children, ...props }) { return createElement(tag, props, children); };
export const Alert = host("mui-alert");
export function Snackbar({ open, children }) { return open ? createElement("snackbar", null, children) : null; }
`);

async function renderCrud(props) {
  const { default: CrudPage, extractErrorMessage } = await loadReal("components/common/CrudPage.jsx", {
    "@mui/material": CRUD_MUI, "@mui/icons-material/Add": STUBS.icon });
  const root = R.createRoot();
  if (props) {
    root.render(h(CrudPage, props));
    await settle(root);
  }
  return { root, extractErrorMessage };
}

test("B-05 a validation list shows the server's Vietnamese messages, never the raw field key", async () => {
  const { extractErrorMessage } = await renderCrud();
  const error = { response: { data: { detail: [
    { type: "greater_than_equal", loc: ["body", "capacity"], msg: "Sức chứa: phải lớn hơn hoặc bằng 0." },
    { type: "string_pattern_mismatch", loc: ["body", "code_prefix"], msg: "Tiền tố mã: sai định dạng." },
  ] } } };
  const text = extractErrorMessage(error);
  // Round 2 (FE-R2-02): sentences that end in a full stop are joined by a space, never ".;".
  assert.equal(text, "Sức chứa: phải lớn hơn hoặc bằng 0. Tiền tố mã: sai định dạng.");
  assert.doesNotMatch(text, /capacity|code_prefix|\^\[A-Z\]/);
  assert.equal(extractErrorMessage({ response: { data: { detail: "Tên khu vực đã tồn tại." } } }), "Tên khu vực đã tồn tại.");
});

test("B-18 deleting a catalog record names it instead of its id", async () => {
  const confirmations = [];
  setGlobal("window", { confirm: (message) => { confirmations.push(message); return false; } });
  const service = { getAll: async () => [{ id: 8, name: "Xe tai zo", capacity: 3, is_active: true }], delete: async () => { throw new Error("must not delete"); } };
  const { root } = await renderCrud({ title: "Quản lý khu vực bãi xe", service, fields: [
    { name: "name", label: "Tên khu vực", required: true }, { name: "capacity", label: "Sức chứa", type: "number" }] });
  fire(buttonsNamed(root, "Xóa")[0], "onClick");
  await settle(root);
  assert.deepEqual(confirmations, ['Xóa khu vực "Xe tai zo"?']);
  root.unmount();
});

test("B-17 the roles page explains the fixed roles instead of the generic catalog subtitle", async () => {
  const service = { getAll: async () => [{ id: 1, name: "manager", description: "Quản lý bãi" }] };
  const { root } = await renderCrud({ title: "Vai trò hệ thống", service, canEdit: false, fields: [
    { name: "name", label: "Tên vai trò" }, { name: "description", label: "Mô tả quyền hạn" }] });
  const header = textOf(findAll(root, (node) => node.type === "header")[0]);
  assert.match(header, /Bốn vai trò cố định/);
  assert.doesNotMatch(header, /Tra cứu và cập nhật thông tin của bãi/);
  root.unmount();
});

test("B-12 the legacy sessions grid speaks Vietnamese and shows no fee for a stay still in the lot", async () => {
  const grid = {};
  const GRID = stub("fix20261028-grid", `
export const seen = {};
export function DataGrid(props) { Object.assign(seen, props); return null; }
`);
  const MUI = stub("fix20261028-session-mui", `
const host = (tag) => function Mui({ children, ...props }) { return createElement(tag, props, children); };
export const Card = host("div"), CardContent = host("div"), Typography = host("span"), Box = host("div"), Button = host("button"), Chip = host("span");
`);
  const { default: SessionTable } = await loadReal("pages/ParkingSession/components/SessionTable.jsx", {
    "@mui/material": MUI, "@mui/x-data-grid": GRID, "@mui/icons-material/Logout": STUBS.icon,
    // The real bundled Vietnamese locale, loaded by Node itself.
    "@mui/x-data-grid/locales": import.meta.resolve("@mui/x-data-grid/locales") });
  const root = R.createRoot();
  root.render(h(SessionTable, { sessions: [], total: 9, loading: false, page: 0, pageSize: 10, onPaginationModelChange() {}, onCheckOut() {}, onTicket() {} }));
  await settle(root);
  Object.assign(grid, (await import(GRID)).seen);
  assert.equal(grid.localeText.paginationRowsPerPage, "Số hàng mỗi trang:");
  assert.equal(grid.localeText.paginationDisplayedRows({ from: 1, to: 9, count: 9 }), "1–9 trên 9");
  const fee = grid.columns.find((column) => column.field === "parkingFee");
  assert.equal(fee.valueGetter(0, { status: "active" }), null);
  assert.equal(fee.valueFormatter(null), "Chưa tính phí");
  assert.equal(fee.valueGetter(20000, { status: "completed" }), 20000);
  root.unmount();
});

test("B-08 two clicks in the same tick create one monthly pass", async () => {
  fakeApi.setHandler(async (method, url) => {
    if (method === "get") return [];
    if (method === "post" && url === "/api/v1/monthly-passes") { await new Promise((resolve) => setTimeout(resolve, 20)); return { id: 6 }; }
    throw new Error(`unexpected ${method} ${url}`);
  });
  const { default: useMonthlyPass } = await loadReal("pages/MonthlyPass/hooks/useMonthlyPass.js");
  const hook = {};
  function Probe() { Object.assign(hook, useMonthlyPass()); return null; }
  const root = R.createRoot();
  root.render(h(Probe));
  await settle(root);
  const body = { pass_code: "TB-B08-5154", vehicle_id: 1, start_date: "2026-10-28", end_date: "2026-11-27", price: 180000, payment_method: "cash" };
  await Promise.all([hook.handleSave(body), hook.handleSave(body)]);
  await settle(root);
  assert.equal(fakeApi.calls.filter((call) => call.method === "post").length, 1);
  assert.equal(hook.notify.severity, "success");
  root.unmount();
});

test("B-19 a signed-in account is sent away from login and registration", async () => {
  const ROUTER = stub("fix20261028-guest-router", `
export const location = { search: "" };
export const useLocation = () => ({ pathname: "/login", search: location.search });
export function Navigate({ to }) { return createElement("navigate", { to }); }
`);
  for (const [user, search, expected] of [[{ id: 1, role: "manager" }, "", "/"], [{ id: 2, role: "customer" }, "?next=%2Fportal%3Ftab%3Dbuy", "/portal?tab=buy"],
    [{ id: 3, role: "staff" }, "?next=%2F%2Fevil.example", "/"], [null, "", null]]) {
    const AUTH = stub(`fix20261028-guest-auth-${user?.id ?? "none"}`, `export const AuthContext = createContext({ user: ${JSON.stringify(user)} });`);
    const { default: GuestRoute } = await loadReal("routes/GuestRoute.jsx", { "react-router-dom": ROUTER, "context/AuthContext.jsx": AUTH });
    (await import(ROUTER)).location.search = search;
    const root = R.createRoot();
    root.render(h(GuestRoute, null, h("form", { id: "login" })));
    await settle(root);
    const redirect = findAll(root, (node) => node.type === "navigate")[0];
    assert.equal(redirect?.props.to ?? null, expected, JSON.stringify(user));
    assert.equal(findAll(root, (node) => node.type === "form").length, user ? 0 : 1);
    root.unmount();
  }
});

test("R1-EXCEL the lot report downloads the same query as CSV or as Excel", async () => {
  const SUMMARY = { period: "week", end_date: "2026-10-26", start_date: "2026-10-20", daily_traffic: [], hourly_traffic: [], peak_hours: [],
    peak_departure_hours: [], peak_movement_hours: [], total_arrivals: 0, total_departures: 0, total_movements: 0, revenue: null,
    current_availability: { zones: [] }, notes: [], data_scope: "operations" };
  fakeApi.setHandler(async (method, url) => {
    if (url === "/api/v2/sites") return [{ id: 1, name: "Bãi 1", role: "staff" }];
    if (url === "/api/v2/sites/1/reports/summary") return SUMMARY;
    if (url === "/api/v2/sites/1/ai/status") return { enabled: false };
    if (url === "/api/v2/sites/1/ai/analyses") return [];
    if (url === "/api/v2/sites/1/reports/export") return new Blob(["x"]);
    throw new Error(`unexpected ${method} ${url}`);
  });
  const downloads = [];
  setGlobal("document", { createElement: () => ({ click() { downloads.push(this.download); }, remove() {} }), body: { appendChild() {} } });
  const { default: CoreAnalyticsPage } = await loadReal("pages/Expansion/CoreAnalyticsPage.jsx", {
    "components/ai/AIResultContent.js": STUBS.empty,
    "context/AuthContext.jsx": stub("fix20261028-excel-auth", "export const AuthContext = createContext({ user: { role: 'staff' } });") });
  const root = R.createRoot();
  root.render(h(CoreAnalyticsPage, { mode: "reports" }));
  await settle(root);
  for (const [label, format] of [["Xuất CSV", "csv"], ["Xuất Excel", "xlsx"]]) {
    fire(buttonsNamed(root, label)[0], "onClick");
    await settle(root);
    const call = fakeApi.calls.filter((item) => item.url === "/api/v2/sites/1/reports/export").at(-1);
    assert.deepEqual(call.params, { period: "week", anchor_date: "2026-10-26", format }, label);
  }
  assert.deepEqual(downloads, ["parking-report-1-week-2026-10-26.csv", "parking-report-1-week-2026-10-26.xlsx"]);
  root.unmount();
});

test("R2-07 the assistant launcher sits in the header row, never over page content", () => {
  const layout = source("layouts/MainLayout.jsx");
  const header = layout.slice(layout.indexOf('<header className="topbar">'), layout.indexOf("</header>"));
  assert.match(header, /<div className="top-actions">[\s\S]*<AIChatbot \/>/);
  assert.equal(layout.match(/<AIChatbot \/>/g).length, 1, "rendered once, in the header");
  const css = source("styles/prototype-app.css");
  assert.match(css, /\.top-actions \.chat-widget\{position:static/);
  assert.match(css, /\.top-actions \.chat-window\{position:fixed;z-index:25;top:96px/);
});

test("B-14 the sidebar names the lot instead of a fixed 'BÃI TRUNG TÂM'", () => {
  const layout = source("layouts/MainLayout.jsx");
  assert.doesNotMatch(layout, /BÃI TRUNG TÂM/);
  assert.match(layout, /<div className="nav-label">\{lotName \|\|/);
  assert.match(layout, /read\("\/sites"\)/);
});

test("B-09 / B-10 / R2-02 / B-16: filters, banners, renewal note and the test timeout", () => {
  const workspace = source("pages/Expansion/SitesWorkspace.jsx");
  assert.match(workspace, /sessionsPage\.setFilters\(\{ status: event\.target\.value, \.\.\.\(invalidDateRange \? \{\} : dateRange\) \}\)/);
  assert.match(source("pages/Expansion/OperationsPanel.jsx"), /selectStay\(null\);\s*\/\/ B-10[^\n]*\n\s*action\.clear\?\.\(\);/);
  assert.match(source("pages/Expansion/shared.jsx"), /return \{ run, busy, error, notice, notify, clear \};/);
  assert.match(source("pages/MonthlyPass/components/MonthlyPassDialog.jsx"), /Kỳ mới không áp dụng cho lượt gửi đang diễn ra/);
  const pkg = JSON.parse(readFileSync(new URL("../package.json", import.meta.url), "utf8"));
  assert.match(pkg.scripts.test, /--test-timeout=\d+/);
});
