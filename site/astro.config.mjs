import { defineConfig } from 'astro/config';
import sitemap from '@astrojs/sitemap';

// Staged indexing: only these URLs go in the sitemap until they have been crawled and indexed.
// To open the rest of the site up later, set SITEMAP_ALLOWLIST to null (or add URLs to the list).
// Note this only limits the sitemap: every page stays crawlable through internal links.
const SITEMAP_ALLOWLIST = new Set([
  'https://askthesubs.com/',
  'https://askthesubs.com/baby-strollers/',
  'https://askthesubs.com/fitness-trackers/',
  'https://askthesubs.com/robot-vacuums/',
  'https://askthesubs.com/ultrawide-monitors/',
  'https://askthesubs.com/vacuum-cleaners/',
]);

// Fully static site: no adapter needed. Cloudflare Workers serves ./dist (see wrangler.jsonc).
export default defineConfig({
  site: 'https://askthesubs.com',
  output: 'static',
  trailingSlash: 'always',
  integrations: [sitemap({ filter: (page) => SITEMAP_ALLOWLIST === null || SITEMAP_ALLOWLIST.has(page) })],
});
