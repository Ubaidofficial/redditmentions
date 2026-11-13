// One place for the brand, so a rename is a one-file change.
export const SITE = {
  name: 'AskTheSubs',
  domain: 'askthesubs.com',
  url: 'https://askthesubs.com',
  tagline: "What Reddit's communities actually recommend, ranked.",
  description:
    'Product rankings built from what people say in Reddit communities, with a link to the original comment behind every quote.',
  disclaimer:
    'AskTheSubs is an independent site. It is not affiliated with, endorsed by, or sponsored by Reddit, Inc.',
};

// The Amazon Associates tag lives in one place (affiliate-tag.mjs); there is deliberately no environment override, so a stray
// .env value cannot put a different tag on the site. scripts/check-affiliate-links.mjs verifies the built output before deploy.
import { AMAZON_TAG as TAG } from '../affiliate-tag.mjs';
export const AMAZON_TAG: string = TAG;

// Set PUBLIC_NOINDEX=true to keep search engines out (previews, staging).
export const NOINDEX: boolean = import.meta.env.PUBLIC_NOINDEX === 'true';

// While the site is new only the pages in launch-pages.json are indexable; the rest are published but noindex,follow.
// Set PUBLIC_INDEX_PAGES=all to index everything.
export const INDEX_ALL: boolean = import.meta.env.PUBLIC_INDEX_PAGES === 'all';

/** True only for a real Amazon product id (10 characters, A-Z and 0-9). */
export const isAsin = (v: unknown): v is string => typeof v === 'string' && /^[A-Z0-9]{10}$/.test(v);

export function buyUrl(asin: string): string {
  return `https://www.amazon.com/dp/${asin}` + (AMAZON_TAG ? `?tag=${encodeURIComponent(AMAZON_TAG)}` : '');
}

// Show Amazon-hosted product photos. Off by default: use it for noindex previews, and switch to
// Amazon's official image links once your Associates account is approved (check the agreement).
export const SHOW_IMAGES: boolean = import.meta.env.PUBLIC_PRODUCT_IMAGES === 'true';
