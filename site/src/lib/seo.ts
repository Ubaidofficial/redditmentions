// Small helpers for titles, descriptions and summaries, so search snippets stay within the lengths
// Google usually shows (roughly 60 characters for a title, 155-160 for a description).

/** Shorten text at a word boundary and add an ellipsis if it is longer than max. */
export function clip(text: string, max: number): string {
  const t = text.replace(/\s+/g, ' ').trim();
  if (t.length <= max) return t;
  const cut = t.slice(0, max - 1);
  const at = cut.lastIndexOf(' ');
  return (at > max * 0.6 ? cut.slice(0, at) : cut).replace(/[\s,;:.·-]+$/, '') + '…';
}

/** The first candidate that fits within max characters, else the last one clipped. */
export function firstFit(candidates: string[], max: number): string {
  return candidates.find((c) => c.length <= max) ?? clip(candidates[candidates.length - 1], max);
}

/** "a", "a and b", "a, b and c" */
export function joinList(items: string[]): string {
  if (items.length <= 1) return items.join('');
  return `${items.slice(0, -1).join(', ')} and ${items[items.length - 1]}`;
}

/** Lower-case a summary label such as "Excellent Value for Money" for use inside a sentence. */
export function phrase(title: string): string {
  return title.trim().replace(/[.!]+$/, '').toLowerCase();
}

/** The year of the newest comments, e.g. "2026" from "2026-06-20". */
export function dataYear(commentsThrough: string): string {
  return String(commentsThrough).slice(0, 4);
}

/** "Jun 2026" from "2026-06-20". */
export function monthYear(date: string): string {
  const m = /^(\d{4})-(\d{2})/.exec(String(date || ''));
  if (!m) return String(date || '');
  return `${['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'][Number(m[2]) - 1]} ${m[1]}`;
}

/** "25 Nov 2026" from "2026-11-25". */
export function longDate(date: string): string {
  const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(String(date || ''));
  if (!m) return String(date || '');
  return `${Number(m[3])} ${monthYear(date)}`;
}

/**
 * The second product's name as people type it in a comparison search, with the words it shares with the
 * first dropped: "Garmin Instinct 2" vs "Garmin Instinct 3" -> "3"; "Anker Soundcore Liberty 4 NC" vs
 * "Anker Soundcore Liberty 4 Pro" -> "Liberty 4 Pro"; "Miele Classic C1" vs "Miele CX1" -> "CX1".
 * Different brands keep the full name.
 */
export function shortVs(a: string, b: string): string {
  const A = a.split(/\s+/), B = b.split(/\s+/);
  let k = 0;
  while (k < Math.min(A.length, B.length) - 1 && A[k].toLowerCase() === B[k].toLowerCase()) k++;
  if (k === 0) return b;
  const rest = B.slice(k);
  // A bare model number reads naturally on its own when the first name also ends in one ("Instinct 2 vs 3",
  // "Forerunner 955 vs 965"), not after a suffix ("Liberty 3 Pro vs 5" becomes "vs Liberty 5" below).
  if (rest.length === 1 && /^\d+$/.test(rest[0]) && A.length === k + 1 && /^\d+$/.test(A[k])) return rest[0];
  // A single word with no model number needs its brand to make sense ("Zoe Terra Double vs Zoe Tour").
  if (k === 1 && rest.length === 1 && !/\d/.test(rest[0])) return b;
  // Otherwise start from the product family: the shared word before the first shared word with a digit
  // ("Liberty" in "Liberty 4 Pro"), else the last shared word ("Qrevo S"), but never the brand alone.
  const firstDigit = A.slice(0, k).findIndex((w) => /\d/.test(w));
  let from = firstDigit > 0 ? firstDigit - 1 : k - 1;
  if (from === 0 && k > 1) from = 1;
  if (from === 0) return rest.join(' ');
  return B.slice(from).join(' ');
}

/** A product name as people search it: without a trailing " Series" or a bracketed note ("(49-inch)"). */
export function searchName(name: string): string {
  return name.replace(/\s*\([^)]*\)\s*/g, ' ').replace(/\s+Series$/i, '').replace(/\s+/g, ' ').trim();
}

/**
 * The most-discussed subreddits across a set of products, from each product's { name, redditors } list.
 * Returns names without the "r/" prefix, most Redditors first.
 */
export function topSubreddits(products: any[], n = 3): string[] {
  const tally = new Map<string, number>();
  for (const p of products) for (const s of p.subreddits ?? []) tally.set(s.name, (tally.get(s.name) ?? 0) + (s.redditors ?? 0));
  return [...tally.entries()].sort((a, b) => b[1] - a[1]).slice(0, n).map(([name]) => name);
}
