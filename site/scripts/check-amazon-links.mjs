// Runs after the build and before every deploy. Reads site/dist and checks every Amazon link:
//   * it carries the Associates tag from affiliate-tag.mjs (the single source of truth)
//   * it is marked rel="sponsored"
//   * no link carries a different tag, and the old archive tag (redditrecs-g-20) appears nowhere
// Any problem stops the deploy, so an untagged or wrongly tagged link can never go live.
import { readFileSync, readdirSync, existsSync, statSync } from 'node:fs';
import { join, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';
import { AMAZON_TAG as tag } from '../affiliate-tag.mjs';

const root = join(dirname(fileURLToPath(import.meta.url)), '..');
const OLD_TAG = 'redditrecs-g-20';

function* htmlFiles(dir) {
  for (const f of readdirSync(dir)) {
    const p = join(dir, f);
    if (statSync(p).isDirectory()) yield* htmlFiles(p);
    else if (f.endsWith('.html')) yield p;
  }
}

const dist = join(root, 'dist');
if (!existsSync(dist)) { console.error('check-amazon-links: dist/ not found. Run the build first.'); process.exit(1); }

let oldTagFiles = 0;
const anchor = /<a\b[^>]*\bhref="([^"]*)"[^>]*>/g;
let total = 0, ok = 0;
const problems = [];
for (const file of htmlFiles(dist)) {
  const html = readFileSync(file, 'utf8');
  if (html.includes(OLD_TAG)) { oldTagFiles++; problems.push(`${file.slice(dist.length)}: contains the old archive tag ${OLD_TAG}`); }
  for (const m of html.matchAll(anchor)) {
    let url;
    try { url = new URL(m[1].replace(/&amp;/g, '&')); } catch { continue; }
    if (!/(^|\.)(amazon\.[a-z.]+|amzn\.to|a\.co)$/i.test(url.hostname)) continue;
    // A link to amazon.com that is not a product link (for example the home page) is still affiliate-able, so it is checked too.
    total++;
    const rel = (m[0].match(/\brel="([^"]*)"/) || [, ''])[1];
    const page = file.slice(dist.length);
    const t = url.searchParams.get('tag');
    if (t !== tag) problems.push(`${page}: ${url.pathname} has tag "${t ?? '(none)'}", expected "${tag}"`);
    else if (!rel.split(/\s+/).includes('sponsored')) problems.push(`${page}: ${url.pathname} is tagged but not marked rel="sponsored"`);
    else ok++;
  }
}

if (total === 0) { console.log('check-amazon-links: no Amazon links in this build.'); process.exit(0); }
if (!problems.length) { console.log(`check-amazon-links: all ${total} Amazon links carry tag "${tag}" and rel="sponsored"; no other tag anywhere.`); process.exit(0); }

const shown = problems.slice(0, 8).map((p) => '  - ' + p).join('\n');
const more = problems.length > 8 ? `\n  ...and ${problems.length - 8} more` : '';
console.error(`check-amazon-links: ${problems.length} problem(s) among ${total} Amazon links (every link must carry tag "${tag}"):\n${shown}${more}`);
process.exit(1);
