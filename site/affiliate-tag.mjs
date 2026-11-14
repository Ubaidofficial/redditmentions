// The one Amazon Associates tag for this site. Every buy link uses it (src/config.ts) and the deploy check
// (scripts/check-affiliate-links.mjs) fails the build if any Amazon link in the output has a different tag or none.
// To change it, edit this line only.
export const AMAZON_TAG = 'reddit-mentions-20';
