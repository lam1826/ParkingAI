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

test("CrudPage includes its default page size in pageSizeOptions", () => {
  const crudPage = readFileSync(
    fileURLToPath(new URL("../src/components/common/CrudPage.jsx", import.meta.url)),
    "utf8",
  );

  assert.match(crudPage, /pageSizeOptions=\{\[10, 25, 50, 100\]\}/);
});

test("CrudPage focuses the first text field when its dialog opens", () => {
  const crudPage = readFileSync(
    fileURLToPath(new URL("../src/components/common/CrudPage.jsx", import.meta.url)),
    "utf8",
  );

  assert.match(crudPage, /firstTextFieldName\s*=\s*fields\.find/);
  assert.match(crudPage, /autoFocus=\{field\.name === firstTextFieldName\}/);
  assert.match(crudPage, /name=\{field\.name\}/);
});
