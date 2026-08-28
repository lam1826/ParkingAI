import assert from "node:assert/strict";
import test from "node:test";

import {
  normalizePublicApiUrl,
  serializeRuntimeConfig,
} from "../scripts/write-runtime-config.mjs";


test("runtime config requires a normalized HTTPS API URL", () => {
  assert.equal(
    normalizePublicApiUrl(" https://api.example.vn/v1/ "),
    "https://api.example.vn/v1",
  );
  for (const value of [
    "",
    "http://api.example.vn",
    "https://user:secret@api.example.vn",
    "https://api.example.vn?debug=true",
    "https://api.example.vn/#fragment",
  ]) {
    assert.throws(() => normalizePublicApiUrl(value));
  }
});


test("runtime config serialization is valid JavaScript data", () => {
  assert.equal(
    serializeRuntimeConfig("https://api.example.vn"),
    'globalThis.__PARKINGAI_CONFIG__ = Object.freeze({ API_URL: "https://api.example.vn" });\n',
  );
});
