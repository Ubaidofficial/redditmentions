// Pure logic for the release plan: which pages are submitted for indexing on a given day. No file or env access, so it works
// both in astro.config.mjs (sitemap) and in bundled pages (robots meta, markdown, llms.txt) and always gives the same answer.
const topic = (slug) => slug.replace(/^\/+|\/+$/g, '').replace(/^best-/, '').replace(/-reddit$/, '');
const DAY = 86400000;
const utcMidnight = (d) => Date.UTC(d.getUTCFullYear(), d.getUTCMonth(), d.getUTCDate());

/** Small deterministic hash, so "5-10 a day" varies day to day but is identical on every build of the same date. */
function fnv(str) {
  let h = 2166136261;
  for (let i = 0; i < str.length; i++) { h ^= str.charCodeAt(i); h = Math.imul(h, 16777619); }
  return h >>> 0;
}

/** How many queued pages are released on this calendar day (UTC date "YYYY-MM-DD"). */
export function dailyCount(cfg, dateStr) {
  const { perDayMin = 5, perDayMax = 10 } = cfg.schedule || {};
  return perDayMin + (fnv('release:' + dateStr) % (perDayMax - perDayMin + 1));
}

/** Number of queued pages released by `now`: day 0 (startDate) releases none; each later day releases dailyCount. */
export function releasedQueueCount(cfg, now = new Date()) {
  if (!cfg.schedule || !cfg.schedule.startDate) return 0;
  const start = Date.parse(cfg.schedule.startDate + 'T00:00:00Z');
  const days = Math.max(0, Math.floor((utcMidnight(now) - start) / DAY));
  let n = 0;
  for (let d = 1; d <= days; d++) n += dailyCount(cfg, new Date(start + d * DAY).toISOString().slice(0, 10));
  return Math.min(n, (cfg.queue || []).length);
}

export function releasedTopics(cfg, now = new Date()) {
  const queue = cfg.queue || [];
  return [...cfg.categories, ...queue.slice(0, releasedQueueCount(cfg, now))].map(topic);
}

export function makeIsLaunchPath(cfg, now = new Date()) {
  const paths = new Set(cfg.paths);
  const topics = new Set(releasedTopics(cfg, now));
  const products = new Set((cfg.products || []).map((p) => p.replace(/\/+$/, '') + '/'));
  /** pathname such as "/best-robot-vacuums-reddit/" or "/" -> is it released? */
  return (pathname) => {
    const p = pathname.endsWith('/') ? pathname : pathname + '/';
    if (paths.has(p) || products.has(p)) return true;
    const parts = p.split('/').filter(Boolean);
    return parts.length === 1 && topics.has(topic(parts[0]));
  };
}

/** Day-by-day plan for the next `days` days from `from` (a Date): which topics go live each day. */
export function planReleases(cfg, from = new Date(), days = 14) {
  const queue = cfg.queue || [];
  const out = [];
  let released = releasedQueueCount(cfg, from);
  for (let i = 0; i <= days; i++) {
    const day = new Date(utcMidnight(from) + i * DAY);
    const date = day.toISOString().slice(0, 10);
    const total = releasedQueueCount(cfg, day);
    out.push({ date, newToday: queue.slice(i === 0 ? total : released, total), liveTotal: cfg.paths.length + cfg.categories.length + total });
    released = total;
  }
  return out;
}

/** The release date to use: PUBLIC_RELEASE_DATE=YYYY-MM-DD pins it (testing, or rebuilding a past day), otherwise today in UTC. */
export function releaseDate(envValue) {
  return envValue && /^\d{4}-\d{2}-\d{2}$/.test(envValue) ? new Date(envValue + 'T12:00:00Z') : new Date();
}
