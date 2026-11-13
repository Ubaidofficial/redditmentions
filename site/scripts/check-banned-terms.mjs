#!/usr/bin/env node
// Fails (exit 1) if any built file mentions a name we never want on the site. Run automatically before deploy;
// run by hand with: npm run check:content
import { readdirSync, readFileSync, statSync } from 'node:fs';
import { join } from 'node:path';
import { fileURLToPath } from 'node:url';

const dist = fileURLToPath(new URL('../dist/', import.meta.url));
const BANNED = /red[ _.\-]?dit[ _.\-]?recs|red[ _.\-]?recs|redrecs|redditrecs|reddit[ _-]recs/i;
const EXT = /\.(html|md|txt|xml|json|js|css|mjs|svg|webmanifest)$/;

function* walk(d) {
  for (const n of readdirSync(d)) {
    const p = join(d, n);
    if (statSync(p).isDirectory()) yield* walk(p); else if (EXT.test(n)) yield p;
  }
}
try { statSync(dist); } catch { console.error('dist/ not found: run the build first'); process.exit(2); }
let files = 0; const bad = [];
for (const f of walk(dist)) {
  files++;
  const t = readFileSync(f, 'utf8');
  const m = t.match(BANNED);
  if (m) bad.push(`${f.slice(dist.length)}: "...${t.slice(Math.max(0, m.index - 40), m.index + m[0].length + 40).replace(/\s+/g, ' ')}..."`);
}
if (bad.length) { console.error(`Content check FAILED: banned name in ${bad.length} file(s):\n  ` + bad.slice(0, 20).join('\n  ')); process.exit(1); }
console.log(`Content check passed: no banned names in ${files} built files.`);
