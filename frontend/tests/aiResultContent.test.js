import test from "node:test";
import assert from "node:assert/strict";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import AIResultContent from "../src/components/ai/AIResultContent.js";

const render = (content) => renderToStaticMarkup(createElement(AIResultContent, { content }));

test("AI reports render headings, paragraphs, emphasis and real lists without modifying saved content", () => {
  const report = Object.freeze({ content: "# Lưu lượng\n\nCó **12 lượt** và *2 chỗ trống*.\n\n- Ca sáng\n- Ca chiều\n\n1. Mở làn\n2. Kiểm tra vé" });
  const original = report.content;
  const html = render(report.content);
  assert.match(html, /<h3>Lưu lượng<\/h3>/);
  assert.match(html, /<strong>12 lượt<\/strong>/);
  assert.match(html, /<em>2 chỗ trống<\/em>/);
  assert.match(html, /<ul>/); assert.match(html, /<ol>/); assert.match(html, /<li>Ca sáng<\/li>/);
  assert.equal(report.content, original);
  assert.doesNotMatch(html, /<h1>|\*\*12 lượt\*\*/);
});

test("remote images, raw HTML and active links cannot load or execute from AI output", () => {
  const html = render("![tracking](https://outside.invalid/pixel.png)\n\n[Hướng dẫn](https://outside.invalid) và [thử](javascript:alert%281%29)\n\n<script>alert('unsafe')</script>\n\n<iframe src='https://outside.invalid/embed'></iframe>\n\n<img src=x onerror=alert(1)>");
  assert.doesNotMatch(html, /<(?:img|script|iframe|a)\b/i);
  assert.doesNotMatch(html, /outside\.invalid|onerror=|javascript:|alert\(/);
  assert.match(html, /Hướng dẫn/);
  assert.match(html, /thử/);
});

test("unsupported formatting remains plain text and no raw HTML renderer is introduced", () => {
  const html = render("> Ghi chú\n\n`<button onclick=alert(1)>`\n\n<https://outside.invalid/help>");
  assert.match(html, /Ghi chú/);
  assert.match(html, /&lt;button onclick=alert\(1\)&gt;/);
  assert.match(html, /https:\/\/outside.invalid\/help/);
  assert.doesNotMatch(html, /<(?:button|blockquote|code|a)\b/);
});

test("empty and missing AI results are harmless", () => {
  for (const content of ["", undefined, null]) assert.doesNotThrow(() => render(content));
});
