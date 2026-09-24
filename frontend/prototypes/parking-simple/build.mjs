// Build the shareable prototype. No application bundle or production files touched.
import { readFile, writeFile } from 'node:fs/promises';
const base = new URL('./', import.meta.url);
let html = await readFile(new URL('shell.html', base), 'utf8');
for (const [marker, file] of [['STYLE', 'style.css'], ['CORE_STYLE', 'core.css'], ['ENGINE', 'engine.js'], ['ANALYTICS', 'analytics.js'], ['REPORTS', 'reports.js'], ['ADMIN', 'admin.js'], ['CORE', 'core.js'], ['AUTH', 'auth.js'], ['GUIDE', 'guide.js'], ['CHAT', 'chat.js'], ['APP', 'app.js']]) {
  const source = await readFile(new URL(file, base), 'utf8');
  html = html.replace(`/* DEMO_${marker} */`, () => '/* Prototype, in-memory only. */\n' + '/* source: ' + file + ' */\n' + source);
}
await writeFile(new URL('index.html', base), html, 'utf8');
console.log('Built standalone index.html (' + Buffer.byteLength(html) + ' bytes). Open directly or serve this directory.');
