import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

import {
  buildParkingSearchParams,
  mapParkingSearchResponse,
  requestParkingSessionSearch,
} from "../src/pages/ParkingSession/services/parkingSessionSearch.js";


test("buildParkingSearchParams giữ filter ngày và chuyển page UI sang API 1-based", () => {
  assert.deepEqual(buildParkingSearchParams({
    status: "completed",
    licensePlate: " 30A-123.45 ",
    dateFrom: "2026-08-01",
    dateTo: "2026-08-31",
    zoneId: 2,
    vehicleTypeId: 3,
    page: 2,
    pageSize: 25,
  }), {
    status: "completed",
    license_plate: "30A-123.45",
    date_from: "2026-08-01T00:00:00",
    date_to: "2026-08-31T23:59:59.999999",
    zone_id: 2,
    vehicle_type_id: 3,
    page: 3,
    size: 25,
  });
});


test("buildParkingSearchParams từ chối khoảng ngày đảo", () => {
  assert.throws(
    () => buildParkingSearchParams({ dateFrom: "2026-08-31", dateTo: "2026-08-01" }),
    /Ngày bắt đầu không được sau ngày kết thúc/,
  );
});


test("mapParkingSearchResponse bảo toàn total và metadata phân trang lớn hơn 100", () => {
  const result = mapParkingSearchResponse({
    total: 137,
    page: 3,
    size: 25,
    items: [{
      session_id: "session-51",
      vehicle: { license_plate: "30A-123.45" },
      slot_name: "A-01",
      zone_name: "Khu A",
      check_in_time: "2026-08-01T08:00:00",
      check_out_time: null,
      duration_minutes: 150,
      parking_fee: 0,
      status: "active",
    }],
  });

  assert.equal(result.total, 137);
  assert.equal(result.page, 2);
  assert.equal(result.pageSize, 25);
  assert.equal(result.items.length, 1);
  assert.equal(result.items[0].id, "session-51");
  assert.equal(result.items[0].parking_slot.slot_number, "A-01 (Khu A)");
  assert.equal(result.items[0].durationMinutes, 150);
});


test("requestParkingSessionSearch gọi đúng API một lần và trả metadata server", async () => {
  const calls = [];
  const apiClient = {
    async get(url, options) {
      calls.push({ url, options });
      return {
        data: {
          total: 101,
          page: 2,
          size: 50,
          items: [],
        },
      };
    },
  };

  const result = await requestParkingSessionSearch(apiClient, {
    status: "active",
    dateFrom: "2026-08-01",
    dateTo: "2026-08-02",
    page: 1,
    pageSize: 50,
  });

  assert.deepEqual(calls, [{
    url: "/parking/search",
    options: {
      params: {
        status: "active",
        date_from: "2026-08-01T00:00:00",
        date_to: "2026-08-02T23:59:59.999999",
        page: 2,
        size: 50,
      },
    },
  }]);
  assert.deepEqual(result, {
    items: [],
    total: 101,
    page: 1,
    pageSize: 50,
  });
});

test("ticket id is an explicit exact filter and never overwrites the plate", () => {
  assert.deepEqual(buildParkingSearchParams({ sessionId: " stay-id ", licensePlate: "30A-12345", status: "cancelled" }),
    { page: 1, size: 10, session_id: "stay-id", license_plate: "30A-12345", status: "cancelled" });
  assert.equal("session_id" in buildParkingSearchParams({ sessionId: "  " }), false);
});

test("history mapping keeps frozen billing facts and leaves old history explicitly missing", () => {
  const basis = { policy_version: "entry-v1", unit_price: 10000, billable_blocks: 2 };
  const prepaid = { order_id: "order", amount: 30000, payment_mode: "demo" };
  const { items } = mapParkingSearchResponse({ items: [
    { session_id: "new", status: "completed", parking_fee: 20000, billing_basis: basis, prepaid, monthly_coverage_end: "2026-09-17" },
    { session_id: "old", status: "completed", parking_fee: 5000 },
  ] });
  assert.equal(items[0].billing_basis, basis);
  assert.equal(items[0].prepaid, prepaid);
  assert.equal(items[0].parkingFee, 20000);
  assert.equal(items[0].monthly_coverage_end, "2026-09-17");
  assert.equal(items[1].billing_basis, null);
  assert.equal(items[1].prepaid, null);
  assert.equal(items[1].monthly_coverage_end, null);
  assert.equal(items[1].parkingFee, 5000);
});


test("ParkingSession wiring có date filter, reset page và DataGrid server-side", async () => {
  const [hookSource, pageSource, tableSource] = await Promise.all([
    readFile(new URL("../src/pages/ParkingSession/hooks/useParkingSession.js", import.meta.url), "utf8"),
    readFile(new URL("../src/pages/ParkingSession/ParkingSessionPage.jsx", import.meta.url), "utf8"),
    readFile(new URL("../src/pages/ParkingSession/components/SessionTable.jsx", import.meta.url), "utf8"),
  ]);

  for (const token of ["dateFrom", "dateTo", "pageSize", "setPage(0)"]) {
    assert.ok(hookSource.includes(token), `Hook phải wire ${token}`);
  }
  assert.match(pageSource, /type="date"/);
  assert.ok(pageSource.includes("Từ ngày"));
  assert.ok(pageSource.includes("Đến ngày"));
  assert.ok(tableSource.includes('paginationMode="server"'));
  assert.ok(tableSource.includes("paginationModel"));
  assert.ok(tableSource.includes("onPaginationModelChange"));
});
