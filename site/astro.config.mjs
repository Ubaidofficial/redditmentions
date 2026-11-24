import { defineConfig } from 'astro/config';
import sitemap from '@astrojs/sitemap';

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
  ].map((path) => SITE_URL + path),
);

// Fully static site: no adapter needed. Cloudflare Workers serves ./dist (see wrangler.jsonc).
export default defineConfig({
  site: SITE_URL,
  output: 'static',
  trailingSlash: 'always',
  integrations: [sitemap({ filter: (page) => SITEMAP_ALLOWLIST === null || SITEMAP_ALLOWLIST.has(page) })],
});
