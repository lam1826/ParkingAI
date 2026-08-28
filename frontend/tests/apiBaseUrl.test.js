import assert from "node:assert/strict";
import test from "node:test";

import { resolveApiBaseUrl } from "../src/utils/apiBaseUrl.js";


test("runtime config wins so one artifact can be promoted", () => {
  assert.equal(
    resolveApiBaseUrl({
      runtimeUrl: " https://api.example.vn/ ",
      buildUrl: "https://build.invalid",
      locationOrigin: "https://app.example.vn",
    }),
    "https://api.example.vn",
  );
});

test("production never falls back to a visitor localhost", () => {
  assert.equal(
    resolveApiBaseUrl({ locationOrigin: "https://app.example.vn" }),
    "https://app.example.vn",
  );
});

test("development keeps the current local API default", () => {
  assert.equal(
    resolveApiBaseUrl({ isDevelopment: true }),
    "http://localhost:8000",
  );
});
