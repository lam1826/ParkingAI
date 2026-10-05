// Integration round 2 (review 05/10/2026, agent MONEY): CL-ONLINE requests to root
//   R3 (#25) the customer's "Đơn mua vé" list shows the payment deadline of a pending order;
//   R4 (#53) the customer's link/vehicle request lists show what was sent (phone/note, type/note)
//            and the link form is cleared after a successful request.
// Runs the REAL CustomerPortal under the shared harness (fake HTTP client, stubbed leaves).
import test from "node:test";
import assert from "node:assert/strict";
import { buttonsNamed, fakeApi, fakeRouter, findAll, fire, h, loadReal, R, settle, STUBS, tableUnder } from "./fix20261005IntegrationHarness.js";
import { formatBusinessTimestamp } from "../src/utils/formatDate.js";

const LEAVES = Object.fromEntries(["PortalPurchase", "PortalOrderDetails", "PortalSessionDetails", "CustomerSupportPanel", "CustomerFees"]
  .map((name) => [`pages/Expansion/${name}.jsx`, STUBS.empty]));
const TYPES = [{ id: 1, name: "Ô tô" }, { id: 2, name: "Xe máy" }];
const DEADLINE = "2026-10-05T03:15:00+00:00";

function portalApi(routes) {
  fakeApi.setHandler(async (method, url, params, body) => {
    const key = `${method} ${url.replace(/^\/api\/v2/, "")}`;
    if (key in routes) return typeof routes[key] === "function" ? routes[key](body, params) : routes[key];
    if (method === "get") return { items: [] };
    throw new Error(`unexpected ${key}`);
  });
}

async function renderPortal(search, routes) {
  fakeRouter.location.search = search;
  portalApi(routes);
  const { default: CustomerPortal } = await loadReal("pages/Expansion/CustomerPortal.jsx", LEAVES);
  const root = R.createRoot();
  root.render(h(CustomerPortal));
  await settle(root);
  return root;
}

const linkedProfile = { linked: true, customer: { id: 9, full_name: "Khách A", phone_number: "0900000001" } };

test("R3 #25 'Đơn mua vé' shows the payment deadline of a pending order, and '—' once it is settled", async () => {
  const pending = { id: "order-pending-0001", status: "pending", product_kind: "monthly", amount: 300000, payment_mode: "manual",
    start_date: "2026-10-05", end_date: "2026-11-04", payment_deadline: DEADLINE };
  const fulfilled = { ...pending, id: "order-fulfilled-0002", status: "fulfilled" };
  const root = await renderPortal("tab=tickets&view=purchase", {
    "get /me/profile": linkedProfile, "get /catalog/vehicle-types": { items: TYPES }, "get /me/orders": [pending, fulfilled],
  });
  const table = tableUnder(root, "Đơn mua vé");
  assert.ok(table, "the order list is rendered");
  const column = table.headers.indexOf("Hạn thanh toán");
  assert.ok(column >= 0, `the order list has a 'Hạn thanh toán' column (headers: ${table.headers.join(", ")})`);
  assert.equal(table.rows[0][column], formatBusinessTimestamp(DEADLINE), "pending order: deadline in business time");
  assert.equal(table.rows[1][column], "—", "a fulfilled order has no payment deadline");
  root.unmount();
});

test("R4 #53 the link-request list shows the phone and note that were sent; the form is cleared after success", async () => {
  const sent = [];
  const root = await renderPortal("tab=tickets&view=profile", {
    "get /me/profile": { linked: false },
    "get /me/link-requests": [{ id: 1, status: "pending", phone_number: "0900000002", note: "Tên trên hồ sơ: B", created_at: "2026-10-05T02:00:00+00:00" }],
    "post /me/link-requests": (body) => { sent.push(body); return { id: 2, status: "pending", ...body }; },
  });
  const table = tableUnder(root, "Tôi đã có hồ sơ tại bãi");
  assert.ok(table, "the link-request list is rendered");
  const row = Object.fromEntries(table.headers.map((header, index) => [header, table.rows[0][index]]));
  assert.equal(row["Số điện thoại"], "0900000002");
  assert.equal(row["Thông tin xác minh"], "Tên trên hồ sơ: B");

  const field = (label) => findAll(root, (node) => node.type === "mui-textfield" && node.props.label === label)[0];
  fire(field("Số điện thoại đã đăng ký"), "onChange", { target: { value: "0900000003" } });
  fire(field("Thông tin hỗ trợ xác minh"), "onChange", { target: { value: "Biển 51A" } });
  await settle(root);
  fire(buttonsNamed(root, "Yêu cầu liên kết")[0], "onSubmit");
  await settle(root);
  assert.deepEqual(sent, [{ phone_number: "0900000003", note: "Biển 51A" }]);
  assert.equal(field("Số điện thoại đã đăng ký").props.value, "", "the phone field is cleared after a successful request");
  assert.equal(field("Thông tin hỗ trợ xác minh").props.value, "");
  root.unmount();
});

test("R4 #53 the vehicle-request list shows the requested type and note", async () => {
  const root = await renderPortal("tab=tickets&view=profile", {
    "get /me/profile": linkedProfile, "get /catalog/vehicle-types": { items: TYPES },
    "get /me/vehicle-requests": [
      { id: 1, status: "pending", license_plate: "51A12345", vehicle_type_id: 2, note: "Xe của vợ" },
      { id: 2, status: "rejected", license_plate: "51B67890", vehicle_type_id: 99, note: null },
    ],
  });
  const table = tableUnder(root, "Yêu cầu thêm xe đã gửi");
  assert.ok(table, "the vehicle-request list is rendered");
  const rows = table.rows.map((cells) => Object.fromEntries(table.headers.map((header, index) => [header, cells[index]])));
  assert.equal(rows[0]["Loại xe"], "Xe máy");
  assert.equal(rows[0]["Ghi chú"], "Xe của vợ");
  assert.equal(rows[1]["Loại xe"], "—", "a type no longer in the active catalogue is shown as unknown");
  assert.equal(rows[1]["Ghi chú"], "—");
  root.unmount();
});
