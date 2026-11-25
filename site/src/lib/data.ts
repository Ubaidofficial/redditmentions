// Reads the generated data (site/src/data/generated/*.json, built from your own machine by
// scripts/build_site_data.py). If it is missing, falls back to a clearly marked fixture so the
// site still builds for development. Fixture builds are never indexable.
const generated = import.meta.glob('../data/generated/*.json', { eager: true, import: 'default' }) as Record<string, any>;
const fixture = import.meta.glob('../data/fixture/*.json', { eager: true, import: 'default' }) as Record<string, any>;

const hasGenerated = Object.keys(generated).some((k) => k.endsWith('/categories.json'));
const files = hasGenerated ? generated : fixture;

export const usingFixture = !hasGenerated;

function load(name: string): any {
  const key = Object.keys(files).find((k) => k.endsWith('/' + name + '.json'));
  if (!key) throw new Error(`Missing data file: ${name}.json`);
  return files[key];
}

export const meta = load('categories');
export const categories: any[] = meta.categories;
export function getCategory(slug: string): any {
  return load(slug);
}

// The day each page's content last changed ({ "/robot-vacuums/": "2026-11-25", ... }), written by
// scripts/build_site_data.py. Missing for the sample fixture and for older data builds: pages then show no date.
const datesKey = Object.keys(files).find((k) => k.endsWith('/page_dates.json'));
export const pageDates: Record<string, string> = datesKey ? files[datesKey] : {};

/** "YYYY-MM-DD" the page at this path last changed, or null if unknown. */
export function modifiedOn(path: string): string | null {
  return pageDates[path] ?? null;
}
