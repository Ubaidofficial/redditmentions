import { defineConfig } from 'astro/config';
import sitemap from '@astrojs/sitemap';
import { readFileSync, readdirSync, existsSync } from 'node:fs';
import { isThinProduct, INDEXED_COMPARISONS } from './src/lib/indexing.mjs';

// Staged indexing: only these URLs go in the sitemap, a few at a time, so each batch can be crawled and indexed
// before the next is added. To list every page, set SITEMAP_ALLOWLIST to null.
// This only limits the sitemap: every page stays crawlable through internal links.
const SITE_URL = 'https://askthesubs.com';
const SITEMAP_ALLOWLIST = new Set(
  [
    // Batch 1 (2026-11-16): home and category pages.
    '/',
    '/baby-strollers/',
    '/fitness-trackers/',
    '/robot-vacuums/',
    '/ultrawide-monitors/',
    '/vacuum-cleaners/',
    // Batch 2 (2026-11-24): wireless earbuds (already indexed through links) and six product pages chosen from
    // Search Console queries and Reddit volume.
    '/wireless-earbuds/',
    '/baby-strollers/out-n-about-nipper/', // #1 in the category with the most impressions
    '/baby-strollers/joolz-aer/', // most discussed stroller (671 Redditors)
    '/robot-vacuums/mova-p10-pro-ultra/', // #1; searched as "mova p10 pro ultra reddit"
    '/ultrawide-monitors/lg-ultragear-45gr65dc-b/', // #1; searched as "lg 45gr65dc-b review"
    '/wireless-earbuds/anker-soundcore-liberty-4-nc/', // searched as "liberty 4 nc", position 6
    '/wireless-earbuds/anker-soundcore-space-a40/', // #1 wireless earbuds
    // Batch 3 (2026-11-24): batch 2 was fully indexed within a day. The #1 product in the two categories that had no
    // product page listed, the most-discussed product in three categories, and one with search impressions.
    '/fitness-trackers/garmin-forerunner-255/', // #1 and the most-discussed top pick (722 Redditors)
    '/vacuum-cleaners/sebo-mechanical/', // #1 vacuum cleaner
    '/vacuum-cleaners/miele-complete-c3/', // most discussed vacuum (1,113 Redditors)
    '/fitness-trackers/garmin-fenix-7-series/', // most discussed fitness tracker (1,043 Redditors)
    '/ultrawide-monitors/lg-45gx950a-b/', // most discussed ultrawide (1,036 Redditors)
    '/wireless-earbuds/earfun-air-pro-4/', // "earfun" already gets impressions; 309 Redditors
    // Trust pages: who runs the site, how it makes money, how to reach it, how rankings are made.
    '/about/',
    '/contact/',
    '/methodology/',
  ].map((path) => SITE_URL + path),
);

// Thin product pages (see src/lib/indexing.mjs) never go in the sitemap, even if listed above or the list is null.
const THIN = new Set();
const GEN = new URL('./src/data/generated/', import.meta.url);
if (existsSync(GEN)) {
  for (const f of readdirSync(GEN)) {
    if (!f.endsWith('.json') || f === 'categories.json' || f.endsWith('.comparisons.json')) continue;
    const cat = JSON.parse(readFileSync(new URL(f, GEN), 'utf8'));
    for (const p of cat.products ?? []) if (isThinProduct(p)) THIN.add(`${SITE_URL}/${cat.slug}/${p.slug}/`);
  }
}
const inSitemap = (page) => {
  if (THIN.has(page)) return false;
  // Comparison pages: only the released ones.
  const path = page.replace(SITE_URL, '');
  if (/^\/[^/]+\/compare\//.test(path)) return INDEXED_COMPARISONS.has(path);
  return SITEMAP_ALLOWLIST === null || SITEMAP_ALLOWLIST.has(page);
};

// Fully static site: no adapter needed. Cloudflare Workers serves ./dist (see wrangler.jsonc).
export default defineConfig({
  site: SITE_URL,
  output: 'static',
  trailingSlash: 'always',
  integrations: [sitemap({ filter: inSitemap })],
});
