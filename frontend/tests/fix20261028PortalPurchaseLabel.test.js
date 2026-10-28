// Fix 28/10/2026, lane FB, item B-15 (1): in "Mua vé", the submit button named a
// monthly order ("Tạo đơn mua vé tháng") while "Vé giờ" was selected and no plan
// was chosen yet. The label must follow the selected product type.
import test from "node:test";
import assert from "node:assert/strict";
import { fakeApi, findAll, h, loadReal, R, settle, stub, textOf } from "./fix20261005IntegrationHarness.js";

// PortalPurchase reads its order flow through useSyncExternalStore; the shared
// harness runtime has no such hook, so this test adds a minimal one on top of it.
const REACT = stub("fix20261028-purchase-react", `
export * from "./runtime.mjs";
import { useEffect, useState } from "./runtime.mjs";
export function useSyncExternalStore(subscribe, getSnapshot) {
  const [, force] = useState(0);
  useEffect(() => subscribe(() => force((count) => count + 1)), [subscribe]);
  return getSnapshot();
}
`);

const vehicles = { data: [{ id: 7, license_plate: "51A-123.45", type_name: "Ô tô", vehicle_type_id: 2 }], loading: false, error: "", reload() {} };
const plans = { data: [
  { id: 11, name: "Tháng ô tô", product_kind: "monthly", duration_days: 30, price: 300000, vehicle_type_id: 2 },
  { id: 12, name: "Giờ ô tô", product_kind: "hourly", duration_minutes: 120, price: 30000, vehicle_type_id: 2, eligible_zones: [{ id: 3, name: "Khu A" }] },
  { id: 13, name: "Ngày ô tô", product_kind: "daily", duration_minutes: 1440, price: 90000, vehicle_type_id: 2, eligible_zones: [{ id: 3, name: "Khu A" }] },
], loading: false, error: "", reload() {} };

async function renderPurchase(initialKind) {
  fakeApi.setHandler(async (method, url) => { throw new Error(`unexpected ${method} ${url}`); });
  const { default: PortalPurchase } = await loadReal("pages/Expansion/PortalPurchase.jsx", { react: REACT });
  const root = R.createRoot();
  root.render(h(PortalPurchase, { vehicles, plans, demoPaymentsEnabled: false, onCreated() {}, onLocked() {}, visible: true, initialKind }));
  await settle(root);
  return root;
}
const submitButton = (root) => findAll(root, (node) => node.type === "button" && node.props.type === "submit")[0];
const field = (root, label) => findAll(root, (node) => node.type === "mui-textfield" && node.props.label === label)[0];

test("B-15 (1) with Vé giờ or Vé ngày selected and no plan yet, the disabled button does not offer a monthly order", async () => {
  for (const kind of ["hourly", "daily"]) {
    const root = await renderPurchase(kind);
    const button = submitButton(root);
    assert.equal(button.props.disabled, true, `${kind}: no plan chosen yet`);
    assert.equal(textOf(button).trim(), "Tạo đơn giữ chỗ", `${kind}: the label follows the selected product type`);
    root.unmount();
  }
});

test("B-15 (1) the label changes with the product type, before and after a plan is chosen", async () => {
  const root = await renderPurchase("monthly");
  assert.equal(textOf(submitButton(root)).trim(), "Tạo đơn mua vé tháng");
  field(root, "Loại vé").props.onChange({ target: { value: "hourly" } });
  await settle(root);
  assert.equal(textOf(submitButton(root)).trim(), "Tạo đơn giữ chỗ");
  field(root, "Xe sử dụng").props.onChange({ target: { value: 7 } });
  await settle(root);
  field(root, "Gói vé").props.onChange({ target: { value: 12 } });
  await settle(root);
  assert.equal(submitButton(root).props.disabled, false, "an hourly plan with a serving zone can be ordered");
  assert.equal(textOf(submitButton(root)).trim(), "Tạo đơn giữ chỗ");
  field(root, "Loại vé").props.onChange({ target: { value: "monthly" } });
  await settle(root);
  assert.equal(textOf(submitButton(root)).trim(), "Tạo đơn mua vé tháng");
  root.unmount();
});
