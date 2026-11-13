// Pure logic: which pages belong to the launch set. No file access, so it works both in astro.config.mjs and in bundled pages.
const topic = (slug) => slug.replace(/^\/+|\/+$/g, '').replace(/^best-/, '').replace(/-reddit$/, '');

export function makeIsLaunchPath(cfg) {
  const paths = new Set(cfg.paths);
  const categories = new Set(cfg.categories.map(topic));
  const products = new Set(cfg.products.map((p) => p.replace(/\/+$/, '') + '/'));
  /** pathname such as "/best-robot-vacuums-reddit/" or "/" -> is it in the launch set? */
  return (pathname) => {
    const p = pathname.endsWith('/') ? pathname : pathname + '/';
    if (paths.has(p) || products.has(p)) return true;
    const parts = p.split('/').filter(Boolean);
    return parts.length === 1 && categories.has(topic(parts[0]));
  };
}
