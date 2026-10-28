// Fix 28/10/2026, round 2 (fixer): findings of the second review and the critic's gaps.
// FE-R2-01 a signed-in account leaves /login by the same role rule as login, FE-R2-02 joined
// server messages, FE-R2-03 / G6(c) 422 lists on the profile and password forms, FE-R2-04 price
// rows named apart in the delete question, G6(b) DataGrid column menu labels, G6(d) live holds
// always visible, G6(e) reservation and waitlist rows ask before cancelling, G2 the stop dialog.
// Real components run under the shared harness (fake HTTP client, no network).
import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { buttonsNamed, fakeApi, findAll, fire, h, loadReal, R, settle, setGlobal, STUBS, stub, textOf } from "./fix20261005IntegrationHarness.js";

const source = (file) => readFileSync(new URL(`../src/${file}`, import.meta.url), "utf8");

// The 422 body the server returns for /register with full_name " a" and username "ab c".
const REGISTER_422 = { response: { status: 422, data: { detail: [
  { type: "string_pattern_mismatch", loc: ["body", "username"], msg: "Tên đăng nhập: sai định dạng." },
  { type: "string_too_short", loc: ["body", "full_name"], msg: "Họ tên: cần ít nhất 2 ký tự." },
] } } };
const JOINED = "Tên đăng nhập: sai định dạng. Họ tên: cần ít nhất 2 ký tự.";
const CRUD_MUI = stub("fixer-r2-crud-mui", `
const host = (tag) => function Mui({ children, ...props }) { return createElement(tag, props, children); };
export const Alert = host("mui-alert");
export function Snackbar({ open, children }) { return open ? createElement("snackbar", null, children) : null; }
`);

test("FE-R2-02 server sentences are joined without a doubled full stop on every screen", async () => {
  const { getErrorMessage } = await import("../src/utils/errorMessage.js");
  assert.equal(getErrorMessage(REGISTER_422, "Không thể đăng ký"), JOINED);
  // Messages without their own full stop keep the earlier ". " separator.
  assert.equal(getErrorMessage({ response: { data: { detail: [{ msg: "Thiếu lý do" }, { msg: "Thiếu số tiền" }] } } }), "Thiếu lý do. Thiếu số tiền");
  const { extractErrorMessage } = await loadReal("components/common/CrudPage.jsx", { "@mui/material": CRUD_MUI, "@mui/icons-material/Add": STUBS.icon });
  assert.equal(extractErrorMessage(REGISTER_422), JOINED);
  const { extractReportDownloadErrorMessage } = await import("../src/pages/Report/services/reportDownloadError.js");
  assert.equal(await extractReportDownloadErrorMessage(REGISTER_422, "Không thể xuất"), JOINED);
});

test("FE-R2-01 a signed-in account leaves /login by the same role rule as login", async () => {
  const { postLoginDestination } = await import("../src/pages/Login/loginDestination.js");
  const ROUTER = stub("fixer-r2-guest-router", `
export const location = { search: "" };
export const useLocation = () => ({ pathname: "/login", search: location.search });
export function Navigate({ to }) { return createElement("navigate", { to }); }
`);
  for (const [role, next, expected] of [["staff", "/portal", "/"], ["admin", "/reservations", "/"],
    ["manager", "/portal?tab=purchase&kind=hourly", "/"], ["customer", "/reservations", "/reservations"], ["customer", null, "/portal"]]) {
    const AUTH = stub(`fixer-r2-guest-auth-${role}-${expected.length}`, `export const AuthContext = createContext({ user: { id: 9, role: ${JSON.stringify(role)} } });`);
    const { default: GuestRoute } = await loadReal("routes/GuestRoute.jsx", { "react-router-dom": ROUTER, "context/AuthContext.jsx": AUTH });
    (await import(ROUTER)).location.search = next ? `?next=${encodeURIComponent(next)}` : "";
    const root = R.createRoot();
    root.render(h(GuestRoute, null, h("form")));
    await settle(root);
    const to = findAll(root, (node) => node.type === "navigate")[0]?.props.to;
    root.unmount();
    assert.equal(to, expected, `${role} with next=${next}`);
    assert.equal(to, postLoginDestination(next, role));
  }
});

const FORM_MUI = stub("fixer-r2-form-mui", `
const host = (tag) => function Mui({ children, ...props }) { return createElement(tag, props, children); };
export const Alert = host("mui-alert"), Avatar = host("span"), Box = host("div"), Button = host("button"), Card = host("div"), CardContent = host("div");
export const Chip = host("span"), CircularProgress = host("progress"), Divider = host("hr"), Stack = host("div"), TextField = host("mui-textfield"), Typography = host("span");
`);
const submitForm = (root) => fire(findAll(root, (node) => node.props?.component === "form")[0], "onSubmit", { preventDefault() {} });

test("FE-R2-03 the profile page shows the server's 422 message", async () => {
  fakeApi.setHandler(async (method, url) => {
    if (method === "put" && url === "/api/auth/me") throw { response: { status: 422, data: { detail: [{ msg: "Tên đăng nhập: sai định dạng." }] } } };
    throw new Error(`unexpected ${method} ${url}`);
  });
  const AUTH = stub("fixer-r2-profile-auth", `export const AuthContext = createContext({ user: { id: 4, role: "customer", username: "khach", full_name: "Khách" }, refreshUser: async () => {} });`);
  const { default: ProfilePage } = await loadReal("pages/Profile/ProfilePage.jsx", {
    "@mui/material": FORM_MUI, "@mui/icons-material/Person": STUBS.icon, "context/AuthContext.jsx": AUTH });
  const root = R.createRoot();
  root.render(h(ProfilePage));
  await settle(root);
  submitForm(root);
  await settle(root);
  assert.equal(textOf(findAll(root, (node) => node.type === "mui-alert")[0]), "Tên đăng nhập: sai định dạng.");
  root.unmount();
});

test("G6(c) the password form shows the server's 422 list", async () => {
  const AUTH = stub("fixer-r2-setting-auth", `export const AuthContext = createContext({ logout() {},
  changePassword: async () => { throw { response: { status: 422, data: { detail: [{ msg: "Mật khẩu mới: cần ít nhất 8 ký tự." }] } } }; } });`);
  const FIELD = stub("fixer-r2-password-field", `export default function PasswordField(props) { return createElement("input", props); }`);
  const { default: SettingPage } = await loadReal("pages/Setting/SettingPage.jsx", {
    "@mui/material": FORM_MUI, "@mui/icons-material/Delete": STUBS.icon, "@mui/icons-material/Lock": STUBS.icon,
    "@mui/icons-material/Logout": STUBS.icon, "context/AuthContext.jsx": AUTH, "components/common/PasswordField.jsx": FIELD });
  const root = R.createRoot();
  root.render(h(SettingPage));
  await settle(root);
  submitForm(root);
  await settle(root);
  assert.equal(textOf(findAll(root, (node) => node.type === "mui-alert")[0]), "Mật khẩu mới: cần ít nhất 8 ký tự.");
  root.unmount();
});

test("FE-R2-04 two prices of one vehicle type get different delete questions", async () => {
  const confirmations = [];
  setGlobal("window", { addEventListener() {}, removeEventListener() {}, confirm: (message) => { confirmations.push(message); return false; } });
  fakeApi.setHandler(async (method, url) => {
    if (method === "get" && url === "/api/v1/vehicle-types") return [{ id: 1, name: "Xe máy DEMO" }];
    if (method === "get" && url === "/api/v1/price-configs") return [
      { id: 1, vehicle_type_id: 1, ticket_type: "HOURLY", price: 5000, effective_date: "2026-07-30", is_active: true },
      { id: 3, vehicle_type_id: 1, ticket_type: "DAILY", price: 30000, effective_date: "2026-07-30", is_active: true }];
    throw new Error(`unexpected ${method} ${url}`);
  });
  const AUTH = stub("fixer-r2-price-auth", `export const AuthContext = createContext({ user: { id: 2, role: "manager" } });`);
  const { default: PriceConfigPage } = await loadReal("pages/PriceConfig/PriceConfigPage.jsx", {
    "@mui/material": CRUD_MUI, "@mui/icons-material/Add": STUBS.icon, "context/AuthContext.jsx": AUTH });
  const root = R.createRoot();
  root.render(h(PriceConfigPage));
  await settle(root);
  for (const button of buttonsNamed(root, "Xóa")) { fire(button, "onClick"); await settle(root); }
  root.unmount();
  assert.deepEqual(confirmations, ['Xóa bảng giá "Xe máy DEMO · Theo giờ · 5.000 ₫"?', 'Xóa bảng giá "Xe máy DEMO · Theo ngày · 30.000 ₫"?']);
  setGlobal("window", { addEventListener() {}, removeEventListener() {}, dispatchEvent() {}, confirm: () => true });
});

test("G6(b) the legacy sessions grid names its column menus in Vietnamese", async () => {
  const { VI_DATA_GRID_TEXT } = await import("../src/utils/dataGridLocale.js");
  assert.equal(VI_DATA_GRID_TEXT.columnMenuAriaLabel("Biển số"), "Menu cột Biển số");
  for (const key of ["columnMenuLabel", "columnHeaderSortIconLabel", "noColumnsOverlayLabel", "noColumnsOverlayManageColumns",
    "columnsManagementDeleteIconLabel"]) {
    assert.doesNotMatch(String(VI_DATA_GRID_TEXT[key]), /^(Menu|Sort|No columns|Manage columns|Clear)$/, key);
  }
});

const RESERVATIONS_AUTH = stub("fixer-r2-reservations-auth", `export const AuthContext = createContext({ user: { role: "customer" } });`);
const declaration = (id, status, extra = {}) => ({ id, site_id: 1, slot_id: 5, license_plate: `51A-111.${id.slice(1).padStart(2, "0")}`,
  vehicle_type_id: 2, start_at: "2026-10-29T08:00:00+07:00", end_at: "2026-10-29T10:00:00+07:00",
  arrival_deadline: "2026-10-29T08:15:00+07:00", status, created_at: "2026-10-28T08:00:00+07:00", slot_name: "A-01", ...extra });

async function renderReservations({ live = [], history = [], reservations = [], waitlist = [] }) {
  const sent = [];
  fakeApi.setHandler(async (method, url, params) => {
    if (method === "get" && url === "/api/v2/sites") return [{ id: 1, name: "Bãi trung tâm" }];
    if (method === "get" && url === "/api/v2/catalog/vehicle-types") return { items: [{ id: 2, name: "Ô tô", requires_plate: true }] };
    if (method === "get" && url === "/api/v2/sites/1/availability") return { site_id: 1, slots: [{ id: 5, vehicle_type_id: 2, available_now: true }] };
    if (method === "get" && url === "/api/v2/me/profile") return { linked: true };
    if (method === "get" && url === "/api/v2/me/reservations") return { items: reservations.filter((row) => !params?.status || row.status === params.status) };
    if (method === "get" && url === "/api/v2/me/waitlist") return { items: waitlist.filter((row) => !params?.status || row.status === params.status) };
    // The server pages by creation time; only status=confirmed returns every live hold.
    if (method === "get" && url === "/api/v2/me/advance-bookings") return params?.status === "confirmed"
      ? { items: live, total: live.length, limit: params.limit, offset: 0 } : { items: history, total: 60, limit: 25, offset: params?.offset ?? 0 };
    if (method === "post") { sent.push(url); return {}; }
    throw new Error(`unexpected ${method} ${url}`);
  });
  const { default: ReservationsPage } = await loadReal("pages/Expansion/ReservationsPage.jsx", { "context/AuthContext.jsx": RESERVATIONS_AUTH });
  const root = R.createRoot();
  root.render(h(ReservationsPage));
  await settle(root);
  return { root, sent };
}
const sectionTitled = (root, title) => findAll(root, (node) => node.type === "section"
  && findAll({ tree: node }, (child) => child.type === "h2" && textOf(child).trim() === title).length)[0];

test("G6(d) a live hold stays under 'Lịch sắp đến' whatever page of the history is shown", async () => {
  const history = Array.from({ length: 25 }, (_, index) => declaration(`c${index + 10}`, "cancelled"));
  const { root } = await renderReservations({ live: [declaration("b1", "confirmed")], history });
  const upcoming = textOf(sectionTitled(root, "Lịch sắp đến"));
  assert.match(upcoming, /51A-111\.01/, "the live hold from another page is upcoming");
  fire(buttonsNamed({ tree: sectionTitled(root, "Đặt chỗ đã kết thúc") }, "Trang sau")[0], "onClick");
  await settle(root);
  assert.match(textOf(sectionTitled(root, "Lịch sắp đến")), /51A-111\.01/, "still upcoming on the next history page");
  const finished = textOf(sectionTitled(root, "Đặt chỗ đã kết thúc"));
  assert.doesNotMatch(finished, /51A-111\.01/);
  root.unmount();
});

test("G6(e) cancelling a granted reservation or leaving the waitlist asks first, like an advance booking", async () => {
  const reservations = [{ id: 31, license_plate: "30A12345", slot_name: "A1", site_name: "Bãi trung tâm", status: "confirmed",
    start_at: "2026-10-29T09:00:00+07:00", arrival_deadline: "2026-10-29T09:15:00+07:00", order_id: null }];
  const waitlist = [{ id: 45, license_plate: "30A67890", status: "waiting", start_at: "2026-10-29T10:00:00+07:00", end_at: "2026-10-29T12:00:00+07:00" },
    { id: 46, license_plate: "30A12345", status: "offered" }];
  const { root, sent } = await renderReservations({ reservations, waitlist });
  for (const [label, index, confirm, url] of [["Hủy chỗ", 0, "Xác nhận hủy chỗ", "/api/v2/me/reservations/31/cancel"],
    ["Rời danh sách chờ", 0, "Xác nhận rời danh sách", "/api/v2/me/waitlist/45/cancel"],
    ["Rời danh sách chờ", 1, "Xác nhận rời danh sách", "/api/v2/me/waitlist/46/cancel"]]) {
    fire(buttonsNamed(root, label)[index], "onClick");
    await settle(root);
    assert.deepEqual(sent, [], `${label}: the first click only asks`);
    assert.equal(buttonsNamed(root, confirm).length, 1);
    fire(buttonsNamed(root, "Giữ lại")[0], "onClick");
    await settle(root);
    assert.equal(buttonsNamed(root, confirm).length, 0, "keeping it closes the question");
    fire(buttonsNamed(root, label)[index], "onClick");
    await settle(root);
    fire(buttonsNamed(root, confirm)[0], "onClick");
    await settle(root);
    assert.deepEqual(sent, [url]);
    sent.length = 0;
  }
  root.unmount();
});

test("G2 the stop dialog says where each kind of payment is refunded", () => {
  const page = source("pages/MonthlyPass/MonthlyPassPage.jsx");
  assert.doesNotMatch(page, /Thu tiền &amp; Chốt ca/, "no such menu; DEMO money cannot be refunded there");
  assert.match(page, /Thu chi &amp; ca làm việc/);
  assert.match(page, /DEMO[^<]*yêu cầu hoàn tiền của khách/);
});
