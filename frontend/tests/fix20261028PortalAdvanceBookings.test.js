// Fix 28/10/2026, lane FB:
//   B-15 (2) cancelling an advance booking asks for confirmation first, and a
//            cancelled/expired (or used) booking leaves the "Lịch sắp đến" section
//            for its own "Đặt chỗ đã kết thúc" section (review round 1: not a
//            sub-block of the upcoming section, and the empty hint names
//            self-declared bookings only, since granted reservations share the section);
//   R2-01    the customer list tolerates bookings whose session_id and slot data are
//            withheld, and shows the status the server returns ("Đã hủy" can now
//            appear without the customer cancelling).
// Runs the REAL ReservationsPage under the shared harness (fake HTTP client).
import test from "node:test";
import assert from "node:assert/strict";
import { buttonsNamed, fakeApi, findAll, fire, h, loadReal, R, settle, stub, textOf } from "./fix20261005IntegrationHarness.js";

const AUTH = stub("fix20261028-bookings-auth", `export const AuthContext = createContext({ user: { role: "customer" } });`);

// Serialized like GET /api/v2/me/advance-bookings after R2-01: no session_id key.
const booking = (id, status, extra = {}) => ({ id, site_id: 1, slot_id: 5, license_plate: `51A-000.0${id.slice(1)}`, vehicle_type_id: 2,
  start_at: "2026-10-29T08:00:00+07:00", end_at: "2026-10-29T10:00:00+07:00", arrival_deadline: "2026-10-29T08:15:00+07:00",
  status, created_at: "2026-10-28T08:00:00+07:00", slot_name: "A-01", ...extra });

async function renderBookings(rows, { reservations = null } = {}) {
  const state = { rows: rows.map((row) => ({ ...row })), cancels: [] };
  fakeApi.setHandler(async (method, url, params) => {
    if (method === "get" && url === "/api/v2/sites") return [{ id: 1, name: "Bãi trung tâm" }];
    if (method === "get" && url === "/api/v2/catalog/vehicle-types") return { items: [{ id: 2, name: "Ô tô", requires_plate: true }] };
    if (method === "get" && url === "/api/v2/sites/1/availability") return { site_id: 1, slots: [{ id: 5, vehicle_type_id: 2, available_now: true }] };
    if (method === "get" && url === "/api/v2/me/profile") return { linked: reservations !== null };
    if (method === "get" && url === "/api/v2/me/reservations") return { items: reservations.filter((row) => !params?.status || row.status === params.status) };
    if (method === "get" && url === "/api/v2/me/waitlist") return { items: [] };
    if (method === "get" && url === "/api/v2/me/advance-bookings") return { items: state.rows, total: state.rows.length, limit: 25, offset: 0 };
    const cancel = url.match(/^\/api\/v2\/me\/advance-bookings\/([^/]+)\/cancel$/);
    if (method === "post" && cancel) {
      state.cancels.push(decodeURIComponent(cancel[1]));
      const row = state.rows.find((item) => item.id === decodeURIComponent(cancel[1]));
      row.status = "cancelled";
      return { ...row };
    }
    throw new Error(`unexpected ${method} ${url}`);
  });
  const { default: ReservationsPage } = await loadReal("pages/Expansion/ReservationsPage.jsx", { "context/AuthContext.jsx": AUTH });
  const root = R.createRoot();
  root.render(h(ReservationsPage));
  await settle(root);
  return { root, state };
}

/** The page section whose own heading (h2) is `title`. */
const sectionTitled = (root, title) => findAll(root, (node) => node.type === "section"
  && findAll({ tree: node }, (child) => child.type === "h2" && textOf(child).trim() === title).length)[0];
const bookingRows = (section) => section ? findAll({ tree: section }, (node) => String(node.props?.className || "").split(" ").includes("booking-row")) : [];

/** Booking rows of the "Lịch sắp đến" section and of the separate "Đặt chỗ đã kết thúc" section. */
function lists(root) {
  const upcomingSection = sectionTitled(root, "Lịch sắp đến");
  assert.ok(upcomingSection, "the upcoming section is rendered");
  const finishedSection = sectionTitled(root, "Đặt chỗ đã kết thúc");
  assert.ok(!finishedSection || !findAll({ tree: upcomingSection }, (node) => node === finishedSection).length, "finished bookings are not inside 'Lịch sắp đến'");
  return { upcoming: bookingRows(upcomingSection), finished: bookingRows(finishedSection), upcomingSection, finishedSection };
}

test("B-15 (2) cancelled, expired and used bookings are not listed under 'Lịch sắp đến'", async () => {
  const { root } = await renderBookings([booking("b1", "confirmed"), booking("b2", "cancelled"), booking("b3", "expired"), booking("b4", "arrived")]);
  const { upcoming, finished, upcomingSection, finishedSection } = lists(root);
  assert.deepEqual(upcoming.map((row) => textOf(row).includes("51A-000.01")), [true], "only the live hold is upcoming");
  assert.ok(finishedSection, "finished bookings get their own 'Đặt chỗ đã kết thúc' section");
  assert.doesNotMatch(textOf(upcomingSection), /Đã hủy|Hết hạn|Đã đến|51A-000\.0[234]/, "no finished booking appears under 'Lịch sắp đến'");
  const plates = ["51A-000.02", "51A-000.03", "51A-000.04"];
  assert.deepEqual(finished.map((row) => plates.find((plate) => textOf(row).includes(plate))), plates, "finished bookings keep the server order");
  finished.forEach((row, index) => assert.ok(textOf(row).includes(["Đã hủy", "Hết hạn", "Đã đến"][index]), "the server status label is shown"));
  assert.equal(finished.flatMap((row) => findAll({ tree: row }, (node) => node.type === "button")).length, 0, "a finished booking offers no cancel");
  root.unmount();
});

test("B-15 (2) cancelling asks for confirmation; 'Giữ lại' sends nothing, 'Xác nhận hủy' sends one request", async () => {
  const { root, state } = await renderBookings([booking("b1", "confirmed"), booking("b2", "confirmed", { slot_name: "A-02" })]);
  const firstRow = () => lists(root).upcoming.find((row) => textOf(row).includes("51A-000.01"));
  fire(findAll({ tree: firstRow() }, (node) => node.type === "button" && textOf(node).trim() === "Hủy")[0], "onClick");
  await settle(root);
  assert.deepEqual(state.cancels, [], "the first click only asks for confirmation");
  assert.match(textOf(firstRow()), /Hủy đặt chỗ này\?/);
  assert.equal(buttonsNamed(root, "Xác nhận hủy").length, 1, "only the chosen booking asks");

  fire(buttonsNamed(root, "Giữ lại")[0], "onClick");
  await settle(root);
  assert.deepEqual(state.cancels, []);
  assert.equal(buttonsNamed(root, "Xác nhận hủy").length, 0, "keeping the booking closes the question");

  fire(findAll({ tree: firstRow() }, (node) => node.type === "button" && textOf(node).trim() === "Hủy")[0], "onClick");
  await settle(root);
  fire(buttonsNamed(root, "Xác nhận hủy")[0], "onClick");
  await settle(root);
  assert.deepEqual(state.cancels, ["b1"], "exactly one cancel request for the confirmed booking");
  const after = lists(root);
  assert.deepEqual(after.upcoming.map((row) => textOf(row).includes("51A-000.02")), [true], "the cancelled booking left the upcoming list");
  assert.ok(after.finished.some((row) => textOf(row).includes("51A-000.01") && textOf(row).includes("Đã hủy")));
  assert.match(textOf(root.tree), /Đã hủy đặt chỗ\./);
  root.unmount();
});

test("R2-01 bookings without session or slot data render with the server status and no dangling slot claim", async () => {
  const withheld = (row) => { const copy = { ...row }; delete copy.slot_id; copy.slot_name = null; return copy; };
  const { root } = await renderBookings([withheld(booking("b1", "confirmed")), withheld(booking("b2", "cancelled")),
    withheld(booking("b3", "expired")), withheld(booking("b4", "arrived"))]);
  const { upcoming, finished } = lists(root);
  assert.equal(upcoming.length, 1);
  assert.match(textOf(upcoming[0]), /Vị trí phù hợp đã được giữ/, "a live hold without a slot name still says a slot is held");
  assert.equal(finished.length, 3);
  for (const row of finished) {
    assert.doesNotMatch(textOf(row), /đã được giữ/, "a finished booking never claims a held slot");
    assert.doesNotMatch(textOf(row), /undefined|null|NaN/);
  }
  assert.equal(findAll(root, (node) => node.type === "a" && /session/i.test(String(node.props.href || ""))).length, 0, "no link to a withheld session");
  root.unmount();
});

test("R2-01 an unknown status from the server is shown as is, not as a live hold", async () => {
  const { root } = await renderBookings([booking("b1", "released")]);
  const { upcoming, finished } = lists(root);
  assert.equal(upcoming.length, 0);
  assert.equal(finished.length, 1);
  assert.match(textOf(finished[0]), /released/);
  root.unmount();
});

test("B-15 (2) a live granted reservation is never contradicted by the 'nothing upcoming' hint", async () => {
  const reservation = { id: 9, license_plate: "51A-999.99", site_name: "Bãi trung tâm", slot_name: "B-02", status: "confirmed",
    start_at: "2026-10-29T08:00:00+07:00", arrival_deadline: "2026-10-29T08:15:00+07:00", order_id: null };
  const { root } = await renderBookings([booking("b1", "cancelled")], { reservations: [reservation] });
  const { upcomingSection, finished } = lists(root);
  const text = textOf(upcomingSection);
  assert.match(text, /51A-999\.99/, "the granted reservation is upcoming");
  assert.doesNotMatch(text, /Không có đặt chỗ sắp đến/, "the hint does not claim nothing is upcoming");
  assert.match(text, /Không có đặt chỗ tự khai báo sắp đến\./, "the hint names self-declared bookings only");
  assert.doesNotMatch(text, /51A-000\.01/, "the cancelled declaration is not under 'Lịch sắp đến'");
  assert.equal(finished.length, 1);
  root.unmount();
});

test("B-15 (2) the pager of a full page sits with the finished bookings", async () => {
  const rows = [booking("b1", "confirmed"), ...Array.from({ length: 24 }, (_, index) => booking(`c${index + 10}`, "cancelled"))];
  const { root } = await renderBookings(rows);
  const { upcoming, finished, upcomingSection, finishedSection } = lists(root);
  assert.equal(upcoming.length, 1);
  assert.equal(finished.length, 24);
  assert.equal(buttonsNamed({ tree: finishedSection }, "Trang sau").length, 1, "the history section pages the list");
  assert.equal(buttonsNamed({ tree: upcomingSection }, "Trang sau").length, 0);
  root.unmount();
});
