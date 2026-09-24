// Copy the user-approved reference styling, scoped to the authenticated app.
import { readFile, writeFile, mkdir } from 'node:fs/promises';
import postcss from 'postcss';
const base = new URL('../', import.meta.url);
const sources = ['style.css', 'core.css'];
let output = '/* Generated from the approved parking-simple prototype. Keep its visual authority. */\n';
for (const name of sources) {
  const css = postcss.parse(await readFile(new URL(`prototypes/parking-simple/${name}`, base), 'utf8'));
  css.walkRules(rule => {
    if (rule.parent.type === 'atrule' && /keyframes$/.test(rule.parent.name)) return;
    rule.selector = rule.selector.split(',').map(part => {
      const selector = part.trim();
      // The original preview uses native links. MUI links rendered as buttons
      // own their variant foreground (including contained and disabled states).
      // Keep the original specificity so native primary/navigation links still
      // receive their own foreground rather than the generic anchor blue.
      if (selector === 'a') return '.prototype-ui a:where(:not(.MuiButtonBase-root))';
      return [':root', 'body'].includes(selector) ? '.prototype-ui' : `.prototype-ui ${selector}`;
    }).join(',');
  });
  output += `\n/* ${name} */\n${css.toString()}\n`;
}
await mkdir(new URL('src/styles/', base), { recursive: true });
await writeFile(new URL('src/styles/prototype-reference.css', base), output.trimEnd() + '\n');
console.log('Approved prototype styles copied with application scope.');
