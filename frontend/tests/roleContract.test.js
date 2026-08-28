import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

import { ROLE_LEVELS, hasMinimumRole } from "../src/constants/roles.js";


test("frontend dùng một role ladder chuẩn và role lạ fail closed", () => {
  assert.deepEqual(ROLE_LEVELS, {
    customer: 0,
    staff: 1,
    manager: 2,
    admin: 3,
  });
  assert.equal(hasMinimumRole("manager", "staff"), true);
  assert.equal(hasMinimumRole("unknown", "staff"), false);
});


test("trang vai trò là danh mục hệ thống chỉ đọc", async () => {
  const source = await readFile(
    new URL("../src/pages/Role/RolePage.jsx", import.meta.url),
    "utf8",
  );

  assert.match(source, /canEdit=\{false\}/);
  assert.match(source, /Vai trò hệ thống/);
});


test("manager nhìn thấy và mở được danh mục vai trò giống contract backend", async () => {
  const routes = await readFile(
    new URL("../src/routes/AppRoutes.jsx", import.meta.url),
    "utf8",
  );
  const layout = await readFile(
    new URL("../src/layouts/MainLayout.jsx", import.meta.url),
    "utf8",
  );

  assert.match(routes, /path="roles"[^\n]+minimumRole="manager"/);
  assert.match(layout, /text: "Vai trò"[^\n]+role: "manager"/);
});
