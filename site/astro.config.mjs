import { defineConfig } from 'astro/config';
import sitemap from '@astrojs/sitemap';

// Staged indexing: the sitemap started with only the home page and the category pages. By 2026-11-24 Google had
// indexed the home page, the methodology page and 5 of the 6 category pages, so the sitemap now lists every page
// (home, methodology, categories and all product pages). To go back to a short list, replace null with a Set of URLs.
const SITEMAP_ALLOWLIST = null;

// Fully static site: no adapter needed. Cloudflare Workers serves ./dist (see wrangler.jsonc).
export default defineConfig({
  site: 'https://askthesubs.com',
  output: 'static',
  trailingSlash: 'always',
  integrations: [sitemap({ filter: (page) => SITEMAP_ALLOWLIST === null || SITEMAP_ALLOWLIST.has(page) })],
});
