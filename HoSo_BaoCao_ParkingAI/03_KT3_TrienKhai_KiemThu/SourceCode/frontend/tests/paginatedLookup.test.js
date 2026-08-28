import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

import { requestAllOffsetPages } from "../src/services/paginatedLookup.js";


test("lookup tải hết dữ liệu vượt giới hạn 100 bản ghi của API", async () => {
  const allItems = Array.from({ length: 205 }, (_, index) => ({ id: index + 1 }));
  const calls = [];
  const apiClient = {
    async get(url, options) {
      calls.push({ url, params: options.params });
      const { skip, limit } = options.params;
      return { data: allItems.slice(skip, skip + limit) };
    },
  };

  const result = await requestAllOffsetPages(apiClient, "/api/v1/vehicles");

  assert.deepEqual(result, allItems);
  assert.deepEqual(calls, [
    { url: "/api/v1/vehicles", params: { skip: 0, limit: 100 } },
    { url: "/api/v1/vehicles", params: { skip: 100, limit: 100 } },
    { url: "/api/v1/vehicles", params: { skip: 200, limit: 100 } },
  ]);
});


test("lookup dừng ngay khi API trả trang rỗng", async () => {
  const calls = [];
  const apiClient = {
    async get(url, options) {
      calls.push({ url, params: options.params });
      return { data: [] };
    },
  };

  assert.deepEqual(await requestAllOffsetPages(apiClient, "/api/v1/customers"), []);
  assert.equal(calls.length, 1);
});

test("lookup giữ nguyên filter khi tải mọi trang nhật ký", async () => {
  const calls = [];
  const apiClient = {
    async get(url, config) {
      calls.push({ url, params: config.params });
      return { data: calls.length === 1 ? [{ id: 1 }] : [] };
    },
  };

  const rows = await requestAllOffsetPages(
    apiClient,
    "/api/v1/audit-logs",
    1,
    { action: "CHECK_IN", success: "true" },
  );

  assert.deepEqual(rows, [{ id: 1 }]);
  assert.deepEqual(calls, [
    {
      url: "/api/v1/audit-logs",
      params: { action: "CHECK_IN", success: "true", skip: 0, limit: 1 },
    },
    {
      url: "/api/v1/audit-logs",
      params: { action: "CHECK_IN", success: "true", skip: 1, limit: 1 },
    },
  ]);
});


test("mọi service collection dùng lookup phân trang thay vì chỉ lấy trang đầu", async () => {
  const [
    monthlySource,
    vehicleSource,
    customerSource,
    zoneSource,
    vehicleTypeSource,
    parkingSlotSource,
    priceConfigSource,
    roleSource,
    userSource,
  ] = await Promise.all([
    readFile(new URL("../src/pages/MonthlyPass/services/monthlyPassService.js", import.meta.url), "utf8"),
    readFile(new URL("../src/pages/Vehicle/services/vehicleService.js", import.meta.url), "utf8"),
    readFile(new URL("../src/pages/Customer/services/customerService.js", import.meta.url), "utf8"),
    readFile(new URL("../src/pages/Zone/services/zoneService.js", import.meta.url), "utf8"),
    readFile(new URL("../src/pages/VehicleType/services/vehicleTypeService.js", import.meta.url), "utf8"),
    readFile(new URL("../src/pages/ParkingSlot/parkingSlotService.js", import.meta.url), "utf8"),
    readFile(new URL("../src/pages/PriceConfig/services/priceConfigService.js", import.meta.url), "utf8"),
    readFile(new URL("../src/pages/Role/services/roleService.js", import.meta.url), "utf8"),
    readFile(new URL("../src/pages/User/services/userService.js", import.meta.url), "utf8"),
  ]);

  for (const source of [
    monthlySource,
    vehicleSource,
    customerSource,
    zoneSource,
    vehicleTypeSource,
    parkingSlotSource,
    priceConfigSource,
    roleSource,
    userSource,
  ]) {
    assert.match(source, /requestAllOffsetPages/);
  }

  assert.match(userSource, /requestAllOffsetPages\(api, "\/api\/v1\/users"\)/);
  assert.match(userSource, /requestAllOffsetPages\(api, "\/api\/v1\/roles"\)/);
  assert.match(
    vehicleSource,
    /getVehicleTypes:\s*async\s*\(\)\s*=>\s*requestAllOffsetPages\(api,\s*"\/api\/v1\/vehicle-types"\)/,
  );
});


test("trang vị trí và bảng giá lấy lookup qua service phân trang", async () => {
  const [parkingSlotPage, priceConfigPage] = await Promise.all([
    readFile(new URL("../src/pages/ParkingSlot/ParkingSlotPage.jsx", import.meta.url), "utf8"),
    readFile(new URL("../src/pages/PriceConfig/PriceConfigPage.jsx", import.meta.url), "utf8"),
  ]);

  assert.match(parkingSlotPage, /zoneService\.getAll\(\)/);
  assert.match(parkingSlotPage, /vehicleTypeService\.getAll\(\)/);
  assert.match(parkingSlotPage, /parkingSlotService\.getAll\(\)/);
  assert.doesNotMatch(parkingSlotPage, /limit:\s*500/);
  assert.doesNotMatch(parkingSlotPage, /import api from/);

  assert.match(priceConfigPage, /vehicleTypeService\.getAll\(\)/);
  assert.doesNotMatch(priceConfigPage, /import api from/);
});
