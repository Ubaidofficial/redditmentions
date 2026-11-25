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
    // Batch 4 (2026-11-25): batches 2-3 were indexed within days, while Search Console's URL inspection reported 80
    // other product pages as "unknown to Google". Ranks 2-5 in every category, the most-discussed products not yet
    // listed, the second product of each released comparison, and products matching searches in Search Console.
    '/baby-strollers/bumbleride-indie/', // #2
    '/baby-strollers/guava-family-roam-crossover-stroller/', // #3
    '/baby-strollers/bumbleride-indie-twin/', // #5
    '/baby-strollers/bob-gear-revolution/', // 496 Redditors
    '/baby-strollers/bugaboo-butterfly-series/', // 461 Redditors; in a released comparison
    '/baby-strollers/thule-urban-glide/', // 349 Redditors
    '/fitness-trackers/garmin-forerunner-955/', // #2; in a released comparison
    '/fitness-trackers/amazfit-bip-6/', // #3
    '/fitness-trackers/garmin-instinct-3/', // #4; in a released comparison
    '/fitness-trackers/garmin-instinct-2/', // #5; in a released comparison
    '/fitness-trackers/garmin-forerunner-965/', // 568 Redditors
    '/robot-vacuums/roborock-qrevo-s/', // #2
    '/robot-vacuums/roborock-q5/', // #3
    '/robot-vacuums/roborock-qx-revo/', // #4
    '/robot-vacuums/roborock-qrevo-curv-series/', // #5
    '/robot-vacuums/roborock-s8/', // 422 Redditors
    '/robot-vacuums/dreame-l40/', // 354 Redditors; in a released comparison
    '/ultrawide-monitors/dell-ultrasharp-40-u4025qw/', // #3
    '/ultrawide-monitors/lg-39gx950b/', // #4
    '/ultrawide-monitors/lg-45gr75dc-b/', // #5
    '/ultrawide-monitors/samsung-odyssey-oled-g9/', // 691 Redditors
    '/ultrawide-monitors/samsung-odyssey-neo-g9-g95nc/', // 635 Redditors
    '/vacuum-cleaners/sebo-d-professional/', // #2
    '/vacuum-cleaners/sebo-airbelt-k/', // #3
    '/vacuum-cleaners/sebo-felix/', // #4
    '/vacuum-cleaners/sebo-automatic-x/', // #5
    '/vacuum-cleaners/miele-compact-c2/', // 866 Redditors
    '/vacuum-cleaners/miele-guard/', // 806 Redditors
    '/vacuum-cleaners/numatic-international-henry-canister-series/', // 685 Redditors
    '/vacuum-cleaners/kenmore-400-series/', // shown in Search for "kenmore 400 series"
    '/wireless-earbuds/anker-soundcore-v20i/', // #2
    '/wireless-earbuds/noble-audio-fokus-rex5/', // #3
    '/wireless-earbuds/oneplus-buds-4/', // #6; searched as "oneplus buds pro 4 reddit"
    '/wireless-earbuds/anker-soundcore-liberty-4-pro/', // in a released comparison
    '/wireless-earbuds/anker-soundcore-aeroclip/', // searched as "soundcore aeroclip 2", "freeclip 2 vs aeroclip 2"
    '/wireless-earbuds/anker-soundcore-liberty-5/', // searched as "soundcore liberty 5 pro"
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
    if (!f.endsWith('.json') || f === 'categories.json' || f === 'page_dates.json' || f.endsWith('.comparisons.json')) continue;
    const cat = JSON.parse(readFileSync(new URL(f, GEN), 'utf8'));
    for (const p of cat.products ?? []) if (isThinProduct(p)) THIN.add(`${SITE_URL}/${cat.slug}/${p.slug}/`);
  }
}
// The day each page's content last changed (scripts/build_site_data.py), used as the sitemap's <lastmod>.
// Pages with no recorded date get no <lastmod> rather than the build date, which search engines learn to ignore.
const DATES_FILE = new URL('page_dates.json', GEN);
const PAGE_DATES = existsSync(DATES_FILE) ? JSON.parse(readFileSync(DATES_FILE, 'utf8')) : {};
const withLastmod = (item) => {
  const date = PAGE_DATES[new URL(item.url).pathname];
  return date ? { ...item, lastmod: date } : item;
};

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
  integrations: [sitemap({ filter: inSitemap, serialize: withLastmod })],
});
