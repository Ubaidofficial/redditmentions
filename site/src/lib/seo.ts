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
