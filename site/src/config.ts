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
// .env value cannot put a different tag on the site. scripts/check-amazon-links.mjs verifies the built output before every deploy.
import { AMAZON_TAG as TAG } from '../affiliate-tag.mjs';
export const AMAZON_TAG: string = TAG;

/** True only for a real Amazon product id (10 characters, A-Z and 0-9). */
export const isAsin = (v: unknown): v is string => typeof v === 'string' && /^[A-Z0-9]{10}$/.test(v);

// Google Tag Manager container for askthesubs.com (Google's "Install manually" code for it). Set
// PUBLIC_GTM_ID to another container, or to an empty value to switch tracking off.
export const GTM_ID: string = import.meta.env.PUBLIC_GTM_ID ?? 'GTM-PX4Q6TN2';

// Set PUBLIC_NOINDEX=true to keep search engines out (previews, staging).
export const NOINDEX: boolean = import.meta.env.PUBLIC_NOINDEX === 'true';

export function buyUrl(asin: string): string {
  return `https://www.amazon.com/dp/${asin}` + (AMAZON_TAG ? `?tag=${encodeURIComponent(AMAZON_TAG)}` : '');
}

// Show Amazon-hosted product photos. Off by default: use it for noindex previews, and switch to
// Amazon's official image links once your Associates account is approved (check the agreement).
export const SHOW_IMAGES: boolean = import.meta.env.PUBLIC_PRODUCT_IMAGES === 'true';
