// Helpers for titles, descriptions, on-page copy and structured data.
// Everything here is built from the page's real data (products, scores, praised/criticised themes); there is no filler.
import { SITE } from '../config';
import { categories, getCategory } from './data';

export const YEAR = new Date().getFullYear();

/** "Robot Vacuums" -> "robot vacuums"; keeps acronyms such as "IEMs" or "VPN" as written. */
export const lower = (s: string) => (/[A-Z]{2,}/.test(s) ? s : s.toLowerCase());

/** First letter up, rest as written: "excessively noisy operation" -> "Excessively noisy operation". */
export const sentence = (s: string) => (s ? s.charAt(0).toUpperCase() + s.slice(1) : s);

/** Trim to a search-snippet length at a word boundary. */
export function clamp(s: string, max = 158) {
  if (s.length <= max) return s;
  return s.slice(0, max - 1).replace(/\s+\S*$/, '') + '…';
}

/** Product names that appear in more than one category, so their page titles can say which one. */
let ambiguous: Set<string> | null = null;
export function isAmbiguous(name: string) {
  if (!ambiguous) {
    const seen = new Map<string, number>();
    for (const c of categories) for (const p of getCategory(c.slug).products) seen.set(p.name.toLowerCase(), (seen.get(p.name.toLowerCase()) ?? 0) + 1);
    ambiguous = new Set([...seen.entries()].filter(([, n]) => n > 1).map(([k]) => k));
  }
  return ambiguous.has(name.toLowerCase());
}

/**
 * Pick the most informative title that fits: try each candidate in order (richest first) and return the first one
 * within `max` characters. Only if none fits is the last candidate cut at a word boundary.
 */
export function firstThatFits(candidates: string[], max = 66) {
  const ok = candidates.find((c) => c.length <= max);
  if (ok) return ok;
  const last = candidates[candidates.length - 1];
  return last.slice(0, max - 1).replace(/[\s,(/-]+\S*$/, '') + '…';
}

export const abs = (path: string) => new URL(path, SITE.url).toString();

/** Append the brand only when the whole title still fits a search result (~62 characters). */
export function withBrand(title: string, max = 62) {
  const full = `${title} | ${SITE.name}`;
  return full.length <= max ? full : title;
}

export function joinList(items: string[]) {
  if (items.length <= 1) return items.join('');
  return items.slice(0, -1).join(', ') + ' and ' + items[items.length - 1];
}

/** Brands that appear most often among the top products. */
export function topBrands(products: any[], n = 3, among = 10) {
  const c = new Map<string, number>();
  for (const p of products.slice(0, among)) {
    const b = (p.brand || '').trim();
    if (b) c.set(b, (c.get(b) ?? 0) + 1);
  }
  return [...c.entries()].sort((a, b) => b[1] - a[1]).slice(0, n).map(([b]) => b);
}

/** Most-mentioned praised / criticised qualities across a category (only where the data has them). */
export function themes(products: any[], kind: 'likes' | 'dislikes', n = 5) {
  const m = new Map<string, { title: string; count: number }>();
  for (const p of products) {
    for (const l of p[kind] ?? []) {
      const k = String(l.title).toLowerCase();
      const e = m.get(k) ?? { title: l.title, count: 0 };
      e.count += l.count;
      m.set(k, e);
    }
  }
  return [...m.values()].sort((a, b) => b.count - a.count).slice(0, n);
}

type Crumb = { name: string; url: string };
export const breadcrumbLd = (items: Crumb[]) => ({
  '@context': 'https://schema.org',
  '@type': 'BreadcrumbList',
  itemListElement: items.map((it, i) => ({ '@type': 'ListItem', position: i + 1, name: it.name, item: it.url })),
});

export const faqLd = (faq: { q: string; a: string }[]) => ({
  '@context': 'https://schema.org',
  '@type': 'FAQPage',
  mainEntity: faq.map((f) => ({ '@type': 'Question', name: f.q, acceptedAnswer: { '@type': 'Answer', text: f.a } })),
});

export const itemListLd = (name: string, items: { name: string; url: string }[]) => ({
  '@context': 'https://schema.org',
  '@type': 'ItemList',
  name,
  numberOfItems: items.length,
  itemListElement: items.map((it, i) => ({ '@type': 'ListItem', position: i + 1, name: it.name, url: it.url })),
});

export const webPageLd = (name: string, url: string, description: string) => ({
  '@context': 'https://schema.org',
  '@type': 'WebPage',
  name,
  url,
  description,
  isPartOf: { '@type': 'WebSite', name: SITE.name, url: SITE.url },
});
