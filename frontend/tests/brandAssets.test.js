import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const read = (path) => readFile(new URL(path, import.meta.url), "utf8");

test("login and app shell use the approved shared PrototypeBrand SVG and browser retains its named favicon", async () => {
  const [indexHtml, loginSource, layoutSource, brandSource, markSource] =
    await Promise.all([
      read("../index.html"),
      read("../src/pages/Login/LoginPage.jsx"),
      read("../src/layouts/MainLayout.jsx"),
      read("../src/components/common/PrototypeUI.jsx"),
      read("../public/brand-mark.svg"),
    ]);

  assert.match(indexHtml, /href="\/brand-mark\.svg"/);
  assert.match(loginSource, /<PrototypeBrand\s*\/>/);
  assert.match(layoutSource, /<PrototypeBrand\s*\/>/);
  assert.match(brandSource, /export function PrototypeBrand\(/);
  assert.match(brandSource, /className="brand-mark" viewBox="0 0 38 40"/);
  assert.match(brandSource, /fill="#1767bd"/);
  assert.match(brandSource, /ParkingAI<small>Một bãi xe\. Mọi thứ rõ ràng\./);
  assert.match(markSource, /aria-label="ParkingAI"/);
});
