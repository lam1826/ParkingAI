import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";


test("đổi kỳ báo cáo xóa dữ liệu cũ và hiển thị loading đến khi kỳ mới hoàn tất", async () => {
  const source = await readFile(
    new URL("../src/pages/Report/ReportPage.jsx", import.meta.url),
    "utf8",
  );

  assert.match(source, /const \[loading, setLoading\] = useState\(true\)/);
  assert.match(source, /setLoading\(true\)[\s\S]*setRevenue\(null\)[\s\S]*setTraffic\(\[\]\)/);
  assert.match(source, /\.finally\([\s\S]*setLoading\(false\)/);
  assert.match(source, /if \(loading\) return <CircularProgress \/>/);
});
