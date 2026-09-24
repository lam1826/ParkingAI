import assert from "node:assert/strict";
import { readdirSync, readFileSync } from "node:fs";
import test from "node:test";
import { fileURLToPath } from "node:url";


const sourceRoot = fileURLToPath(new URL("../src", import.meta.url));

function sourceFiles(directory) {
  return readdirSync(directory, { withFileTypes: true }).flatMap((entry) => {
    const path = `${directory}/${entry.name}`;
    if (entry.isDirectory()) return sourceFiles(path);
    return /\.(js|jsx)$/.test(entry.name) ? [path] : [];
  });
}

test("MUI layout props stay in sx instead of leaking to DOM", () => {
  const offenders = sourceFiles(sourceRoot).filter((path) => {
    const source = readFileSync(path, "utf8");
    return /\b(?:alignItems|justifyContent)=/.test(source);
  });

  assert.deepEqual(offenders, []);
});

test("compact catalog uses a native table and offers pagination without a DataGrid page-size warning", () => {
  const crudPage = readFileSync(
    fileURLToPath(new URL("../src/components/common/CrudPage.jsx", import.meta.url)),
    "utf8",
  );

  assert.doesNotMatch(crudPage, /@mui\/x-data-grid|<DataGrid|pageSizeOptions/);
  assert.match(crudPage, /<table\b/);
  assert.match(crudPage, /scope="col"/);
  assert.match(crudPage, /Trang trước/);
  assert.match(crudPage, /Trang sau/);
});

test("CrudPage focuses the first text or select field when its inline editor opens", () => {
  const crudPage = readFileSync(
    fileURLToPath(new URL("../src/components/common/CrudPage.jsx", import.meta.url)),
    "utf8",
  );

  assert.match(crudPage, /firstTextFieldName\s*=\s*fields\.find/);
  assert.match(crudPage, /autoFocus=\{field\.name === firstTextFieldName\}/);
  assert.match(crudPage, /name=\{field\.name\}/);
});
