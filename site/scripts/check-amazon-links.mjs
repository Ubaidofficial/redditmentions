// Runs after the build and before every deploy. Reads site/dist and checks every Amazon link:
//   * it carries the Associates tag from PUBLIC_AMAZON_TAG (env var or site/.env)
//   * it is marked rel="sponsored"
//   * no link carries a different tag (for example a stale one from archived data)
// If the tag is missing, the deploy stops, so untagged links can never go live by accident.
// Preview builds (PUBLIC_NOINDEX=true) only warn.
import { readFileSync, readdirSync, existsSync, statSync } from 'node:fs';
import { join, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';

const root = join(dirname(fileURLToPath(import.meta.url)), '..');

function fromDotEnv(name) {
  const file = join(root, '.env');
  if (!existsSync(file)) return '';
  for (const line of readFileSync(file, 'utf8').split('\n')) {
    const m = line.match(/^\s*([A-Z0-9_]+)\s*=\s*(.*?)\s*$/);
    if (m && m[1] === name) return m[2].replace(/^["']|["']$/g, '');
  }
  return '';
}
const env = (name) => (process.env[name] ?? fromDotEnv(name) ?? '').trim();

const tag = env('PUBLIC_AMAZON_TAG');
const preview = env('PUBLIC_NOINDEX') === 'true';

function* htmlFiles(dir) {
  for (const f of readdirSync(dir)) {
    const p = join(dir, f);
    if (statSync(p).isDirectory()) yield* htmlFiles(p);
    else if (f.endsWith('.html')) yield p;
  }
}

const dist = join(root, 'dist');
if (!existsSync(dist)) { console.error('check-amazon-links: dist/ not found. Run the build first.'); process.exit(1); }

const anchor = /<a\b[^>]*\bhref="([^"]*)"[^>]*>/g;
let total = 0, ok = 0;
const problems = [];
for (const file of htmlFiles(dist)) {
  const html = readFileSync(file, 'utf8');
  for (const m of html.matchAll(anchor)) {
    let url;
    try { url = new URL(m[1].replace(/&amp;/g, '&')); } catch { continue; }
    if (!/(^|\.)(amazon\.[a-z.]+|amzn\.to|a\.co)$/i.test(url.hostname)) continue;
    // A link to amazon.com that is not a product link (for example the home page) is still affiliate-able, so it is checked too.
    total++;
    const rel = (m[0].match(/\brel="([^"]*)"/) || [, ''])[1];
    const page = file.slice(dist.length);
    const t = url.searchParams.get('tag');
    if (!tag) problems.push(`${page}: no PUBLIC_AMAZON_TAG is set, so ${url.pathname} is untagged`);
    else if (t !== tag) problems.push(`${page}: ${url.pathname} has tag "${t ?? '(none)'}", expected "${tag}"`);
    else if (!rel.split(/\s+/).includes('sponsored')) problems.push(`${page}: ${url.pathname} is tagged but not marked rel="sponsored"`);
    else ok++;
  }
}

if (total === 0) { console.log('check-amazon-links: no Amazon links in this build.'); process.exit(0); }
if (!problems.length) { console.log(`check-amazon-links: all ${total} Amazon links carry tag "${tag}" and rel="sponsored".`); process.exit(0); }

const shown = problems.slice(0, 8).map((p) => '  - ' + p).join('\n');
const more = problems.length > 8 ? `\n  ...and ${problems.length - 8} more` : '';
console.error(`check-amazon-links: ${problems.length} of ${total} Amazon links are not tagged correctly:\n${shown}${more}`);
if (!tag) console.error('\nSet your Associates tag in site/.env, for example:\n  PUBLIC_AMAZON_TAG=yourtag-20\nand publish again.');
if (preview) { console.error('\nPUBLIC_NOINDEX=true (preview build): continuing anyway.'); process.exit(0); }
process.exit(1);
