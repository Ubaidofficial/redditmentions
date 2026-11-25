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
  // Batch 2 (2026-11-25): every other comparison with measurable search demand (OpenSEO keyword metrics, US,
  // monthly searches for the short form people type) and two indexable products.
  '/fitness-trackers/compare/garmin-forerunner-955-vs-garmin-forerunner-965/', // "forerunner 955 vs 965" ~250
  '/fitness-trackers/compare/garmin-forerunner-255-vs-garmin-forerunner-965/', // ~20
  '/fitness-trackers/compare/garmin-forerunner-245-vs-garmin-forerunner-955/', // ~20
  '/fitness-trackers/compare/garmin-forerunner-245-vs-garmin-forerunner-965/', // ~20
  '/ultrawide-monitors/compare/samsung-odyssey-neo-g9-g95nc-vs-samsung-odyssey-oled-g9/', // "neo g9 vs oled g9" ~30
  '/ultrawide-monitors/compare/samsung-odyssey-g9-g95c-vs-samsung-odyssey-neo-g9-g95nc/', // "odyssey g9 vs neo g9" ~30
  '/ultrawide-monitors/compare/samsung-odyssey-g9-g95c-vs-samsung-odyssey-oled-g9/', // ~20
  '/robot-vacuums/compare/roborock-qrevo-pro-vs-roborock-qx-revo/', // ~20
  '/robot-vacuums/compare/roborock-qrevo-maxv-vs-roborock-qrevo-s/', // ~20
  '/robot-vacuums/compare/roborock-qrevo-curv-series-vs-roborock-qrevo-s/', // ~20
  '/robot-vacuums/compare/roborock-qrevo-curv-series-vs-roborock-qrevo-maxv/', // ~10
  '/robot-vacuums/compare/roborock-qrevo-s-vs-roborock-qx-revo/', // ~10
  '/vacuum-cleaners/compare/miele-classic-c1-vs-miele-cx1/', // ~20
  '/wireless-earbuds/compare/anker-soundcore-aerofit-2-vs-anker-soundcore-v20i/', // ~40
  '/wireless-earbuds/compare/anker-soundcore-liberty-4-pro-vs-anker-soundcore-space-a40/', // ~30
  '/wireless-earbuds/compare/anker-soundcore-liberty-3-pro-vs-anker-soundcore-liberty-4-pro/', // ~20
  '/baby-strollers/compare/bob-gear-revolution-vs-thule-urban-glide/', // ~10
  '/baby-strollers/compare/bugaboo-butterfly-series-vs-bugaboo-fox-5-renew/', // ~10
]);
