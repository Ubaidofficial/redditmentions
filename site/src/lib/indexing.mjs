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
export const INDEXED_COMPARISONS = new Set([]);
