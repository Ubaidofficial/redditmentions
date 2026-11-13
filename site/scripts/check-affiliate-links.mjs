#!/usr/bin/env node
// Fails (exit 1) if any Amazon link in the built site lacks the site's Associates tag or carries another one,
// or if the old redditrecs tag shows up anywhere. Run automatically before deploy; run by hand with: npm run check:links
import { readdirSync, readFileSync, statSync } from 'node:fs';
import { join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { AMAZON_TAG } from '../affiliate-tag.mjs';

// fileURLToPath, not URL.pathname: pathname keeps spaces percent-encoded ("AI%20Projects"), which does not exist on disk.
const dist = fileURLToPath(new URL('../dist/', import.meta.url));
const EXT = /\.(html|md|txt|xml|json|js|css|mjs)$/;
const AMAZON_LINK = /https?:\/\/(?:[a-z0-9-]+\.)?(?:amazon\.[a-z.]+|amzn\.[a-z]+|a\.co)(?:[^\s"'<>)\\]*)/gi;
const ANY_TAG = /[?&;]tag=([A-Za-z0-9_-]+)/g;
const OLD_TAGS = ['redditrecs-g-20'];
const okLink = new RegExp(`^https://www\\.amazon\\.com/dp/[A-Z0-9]{10}\\?tag=${AMAZON_TAG}$`);

function* walk(d) {
  for (const n of readdirSync(d)) {
    const p = join(d, n);
    if (statSync(p).isDirectory()) yield* walk(p); else if (EXT.test(n)) yield p;
  }
}

let links = 0, files = 0, bad = [];
try { statSync(dist); } catch { console.error('dist/ not found: run the build first'); process.exit(2); }
for (const f of walk(dist)) {
  const text = readFileSync(f, 'utf8');
  files++;
  for (const m of text.matchAll(AMAZON_LINK)) {
    links++;
    const url = m[0].replace(/&amp;/g, '&');
    if (!okLink.test(url)) bad.push(`${f.slice(dist.length)}: ${url.slice(0, 140)}`);
  }
  for (const t of text.matchAll(ANY_TAG)) if (t[1] !== AMAZON_TAG) bad.push(`${f.slice(dist.length)}: other tag "${t[1]}"`);
  for (const old of OLD_TAGS) if (text.includes(old)) bad.push(`${f.slice(dist.length)}: contains old tag ${old}`);
}
if (bad.length) {
  console.error(`Affiliate link check FAILED (${bad.length} problem(s)):\n  ` + [...new Set(bad)].slice(0, 20).join('\n  '));
  process.exit(1);
}
console.log(`Affiliate link check passed: ${links} Amazon link(s) in ${files} files, all tagged ${AMAZON_TAG}; no other tags.`);
