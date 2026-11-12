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

// Set PUBLIC_AMAZON_TAG (in site/.env or the build environment) only once you have an
// approved Amazon Associates account. Without it, buy links are plain, non-affiliate links.
export const AMAZON_TAG: string = import.meta.env.PUBLIC_AMAZON_TAG ?? '';

// Set PUBLIC_NOINDEX=true to keep search engines out (previews, staging).
export const NOINDEX: boolean = import.meta.env.PUBLIC_NOINDEX === 'true';

export function buyUrl(asin: string): string {
  return `https://www.amazon.com/dp/${asin}` + (AMAZON_TAG ? `?tag=${encodeURIComponent(AMAZON_TAG)}` : '');
}
