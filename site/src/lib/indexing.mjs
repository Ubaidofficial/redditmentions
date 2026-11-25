// Which pages search engines may index. Used by the pages (robots meta tag) and by astro.config.mjs (sitemap),
// so the two can never disagree. Thin pages are still built and linked; they carry "noindex, follow".

/** Fewest Redditors for a product page to be indexed. */
export const MIN_REDDITORS_TO_INDEX = 40;
/** Fewest usable quotes for a product page to be indexed. */
export const MIN_QUOTES_TO_INDEX = 3;

/** A product page with too little evidence to be worth a search result on its own. */
export function isThinProduct(p) {
  return (p.opinions ?? 0) < MIN_REDDITORS_TO_INDEX || (p.quotes?.length ?? 0) < MIN_QUOTES_TO_INDEX;
}

// Comparison pages ("X vs Y") are released in batches like the rest of the site: only the pairs listed here are
// indexable and go in the sitemap; every other comparison page is built with "noindex, follow".
// Paths look like '/robot-vacuums/compare/dreame-l40-vs-roborock-s8/'.
export const INDEXED_COMPARISONS = new Set([
  // Batch 1 (2026-11-25): pairs with at least one indexed product, real head-to-head evidence and under 70% shared
  // Redditors (see MAX_SHARED_SHARE in scripts/build_site_data.py).
  '/fitness-trackers/compare/garmin-forerunner-255-vs-garmin-forerunner-955/', // 243 Redditors discussed both
  '/fitness-trackers/compare/garmin-instinct-2-vs-garmin-instinct-3/', // 228
  '/wireless-earbuds/compare/anker-soundcore-liberty-4-nc-vs-anker-soundcore-liberty-4-pro/', // 122
  '/baby-strollers/compare/bugaboo-butterfly-series-vs-joolz-aer/', // 63
  '/robot-vacuums/compare/dreame-l40-vs-mova-p10-pro-ultra/', // 34
]);
