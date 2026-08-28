import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const read = (path) => readFile(new URL(path, import.meta.url), "utf8");

test("shared ParkingAI brand mark is used by browser, login, and app shell", async () => {
  const [indexHtml, loginSource, layoutSource, logoSource, markSource] =
    await Promise.all([
      read("../index.html"),
      read("../src/pages/Login/LoginPage.jsx"),
      read("../src/layouts/MainLayout.jsx"),
      read("../src/components/brand/BrandLogo.jsx"),
      read("../public/brand-mark.svg"),
    ]);

  assert.match(indexHtml, /href="\/brand-mark\.svg"/);
  assert.match(loginSource, /<BrandLogo/);
  assert.match(layoutSource, /<BrandLogo/);
  assert.match(logoSource, /brand-mark\.svg/);
  assert.match(markSource, /aria-label="ParkingAI"/);
});
