import { defineConfig } from 'astro/config';
import sitemap from '@astrojs/sitemap';

// Fully static site: no adapter needed. Cloudflare Workers serves ./dist (see wrangler.jsonc).
export default defineConfig({
  site: 'https://askthesubs.com',
  output: 'static',
  trailingSlash: 'always',
  integrations: [sitemap()],
});
