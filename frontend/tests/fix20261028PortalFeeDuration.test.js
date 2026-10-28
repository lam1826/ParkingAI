// Fix 28/10/2026, lane FB, item B-15 (3): the same stay read "0 giờ 35 phút" in the
// customer fee lookup but "34 phút" for staff. The customer view now uses the staff
// formatter (formatParkingDuration, as in OperationsPanel/CheckoutDialog) and the
// server's whole-minute truncation (checkout_service: int(seconds / 60)).
import test from "node:test";
import assert from "node:assert/strict";
import { fakeApi, findAll, fire, h, loadReal, R, settle, stub, STUBS, textOf } from "./fix20261005IntegrationHarness.js";
import { formatParkingDuration } from "../src/pages/ParkingSession/sessionPresentation.js";

// The fee page also draws the parking illustration, which the shared prototype stub lacks.
const PROTOTYPE = stub("fix20261028-fees-prototype", `
export function PageHeader({ title }) { return createElement("header", null, createElement("h1", null, title)); }
export function PrototypeIcon() { return null; }
export function WorkspaceTabs() { return null; }
export function ParkingIllustration() { return null; }
`);
const CHECK_IN = "2026-10-28T10:00:00.654321+07:00";

async function lookup(serverNow, checkIn = CHECK_IN) {
  fakeApi.setHandler(async (method, url) => {
    if (method === "get" && url === "/api/v2/sites") return [{ id: 1, name: "Bãi trung tâm" }];
    if (method === "get" && url === "/api/v2/catalog/vehicle-types") return { items: [{ id: 2, name: "Ô tô", requires_plate: true }] };
    if (method === "get" && url === "/api/v2/sites/1/availability") return { site_id: 1, slots: [{ id: 5, vehicle_type_id: 2, available_now: false }] };
    if (method === "post" && url === "/api/v2/me/fee-lookup") return {
      session: { id: "s-1", license_plate: "51A-123.45", vehicle_type_id: 2, check_in_time: checkIn, status: "active" },
      payment_status: { session_id: "s-1", session_status: "active", enabled: false, supported: true, gross_fee: 10000, online_paid: 0, balance_due: 10000, server_now: serverNow, message: "" },
      access: { kind: "owned", expires_at: null } };
    throw new Error(`unexpected ${method} ${url}`);
  });
  const { default: CustomerFees } = await loadReal("pages/Expansion/CustomerFees.jsx", { "pages/Expansion/SessionFeePayment.jsx": STUBS.empty, "components/common/PrototypeUI.jsx": PROTOTYPE });
  const root = R.createRoot();
  root.render(h(CustomerFees));
  await settle(root);
  fire(findAll(root, (node) => node.type === "input" && node.props.id === "customer-plate")[0], "onChange", { target: { value: "51A-123.45" } });
  fire(findAll(root, (node) => node.type === "select" && node.props.id === "customer-type")[0], "onChange", { target: { value: "2" } });
  await settle(root);
  fire(findAll(root, (node) => node.type === "form")[0], "onSubmit");
  await settle(root);
  const line = findAll(root, (node) => node.props?.className === "fee-line" && textOf(node).startsWith("Thời gian gửi"))[0];
  assert.ok(line, "the stay duration is shown");
  const text = textOf(line).replace(/^Thời gian gửi/, "");
  root.unmount();
  return text;
}

test("B-15 (3) the customer sees the stay in the staff's compact format", async () => {
  // 34 min 59.3 s: the server's quote truncates to 34 whole minutes.
  assert.equal(await lookup("2026-10-28T10:34:59.987654+07:00"), "34 phút");
  assert.equal(await lookup("2026-10-28T10:34:59.987654+07:00"), formatParkingDuration(34));
  assert.equal(await lookup("2026-10-28T11:05:01+07:00"), "1 giờ 5 phút");
  assert.equal(await lookup("2026-10-28T12:00:30+07:00"), "2 giờ");
  assert.equal(await lookup("2026-10-28T10:00:30+07:00"), "Dưới 1 phút");
});

test("B-15 (3) a check-in without an offset is Vietnam business time; a clock behind check-in is not negative", async () => {
  assert.equal(await lookup("2026-10-28T03:35:00Z", "2026-10-28T10:00:00"), "35 phút");
  assert.equal(await lookup("2026-10-28T09:59:00+07:00"), "Dưới 1 phút");
});

test("B-15 (3) the shared helper truncates like the server and formats like the staff view", async () => {
  const { stayDuration } = await import("../src/pages/Expansion/customerFlow.js");
  assert.equal(stayDuration(CHECK_IN, "2026-10-28T10:35:00.653+07:00"), "34 phút", "a millisecond short of 35 minutes is still 34");
  assert.equal(stayDuration(CHECK_IN, "2026-10-28T10:35:00.654+07:00"), "35 phút");
  assert.equal(stayDuration("2026-10-28T10:00:00", "2026-10-28T11:00:00+07:00"), "1 giờ");
  assert.equal(stayDuration(CHECK_IN, "not a time"), "Đang cập nhật");
});
