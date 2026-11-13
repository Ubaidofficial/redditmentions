import { defineConfig } from 'astro/config';
import sitemap from '@astrojs/sitemap';
import { loadEnv } from 'vite';
import { makeConfigIsLaunchPath } from './launch.mjs';

// PUBLIC_INDEX_PAGES: "launch" (default) lists only the pages in launch-pages.json in the sitemap and marks every
// other page noindex,follow; "all" lists and indexes every page. Set it in site/.env (see README).
const env = loadEnv(process.env.NODE_ENV || 'production', process.cwd(), 'PUBLIC_');
const indexAll = (process.env.PUBLIC_INDEX_PAGES || env.PUBLIC_INDEX_PAGES) === 'all';
const isLaunchPath = makeConfigIsLaunchPath(process.env.PUBLIC_RELEASE_DATE || env.PUBLIC_RELEASE_DATE);

// Fully static site: no adapter needed. Cloudflare Workers serves ./dist (see wrangler.jsonc).
export default defineConfig({
  site: 'https://askthesubs.com',
  output: 'static',
  trailingSlash: 'always',
  integrations: [sitemap({ filter: (page) => indexAll || isLaunchPath(new URL(page).pathname) })],
});
