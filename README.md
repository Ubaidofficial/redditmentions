# redditmentions

Research toolkit for **redditrecs.com**, a site (2024–2026) that ranked products by
analysing Reddit comments. It shut down on 2 Nov 2026. These scripts recover its archived
pages from the Wayback Machine and turn them into spreadsheets, to study how the site was
structured before building something similar.

## What was found

- **7,597 archived pages**: 5,724 product ("model") pages, 902 filter / "best for X" pages,
  461 brand pages, 54 category pages and 456 other pages
- **44 product categories** (action cameras, air purifiers, espresso machines, robot vacuums, …)
- Each product page embeds its full data as JSON (`__NUXT_DATA__`): every Reddit comment used,
  with username, subreddit, thread, date and permalink, plus sentiment counts, like/dislike
  summaries with quotes, Amazon prices and "best for" use-case definitions

## Usage

Run on your own computer (needs direct access to web.archive.org), Python 3.8+:

```bash
pip3 install requests beautifulsoup4
```

Download pages into `pages/` (resumable; Ctrl+C is safe):

```bash
caffeinate -i python3 scrape_fast.py --skip-brand     # macOS: caffeinate keeps the Mac awake
```

Options: `--workers N` (default 4), `--gap S` (minimum seconds between requests, default 0.5),
`--skip-brand` (brand pages are downloaded last anyway).

Turn downloaded pages into CSVs in `output/` (can run while downloading):

```bash
python3 extract.py
```

| File | Contents |
|---|---|
| `categories.csv` | the 44 categories |
| `models.csv` | one row per product: brand, opinion count, sentiment, lowest price, Amazon link |
| `opinions.csv` | every Reddit comment with permalink, subreddit, date, extracted quote |
| `summary_points.csv` | like/dislike summaries with quotes |
| `use_cases.csv` | "best for X" definitions and top picks |
| `listings.csv` | all price listings |

Category, filter and brand pages are saved as decoded JSON in `output/json/` until their
format is added to the extractor.

Summarise the data (which categories had the most Reddit discussion, top products,
subreddits, use cases):

```bash
python3 analyze.py
```

Writes `output/report.md`, `category_summary.csv`, `top_products.csv`, `subreddits.csv`
and a compact `report_summary.json`. Product scores are a Wilson lower bound on the
positive/negative split, our own ranking rather than RedditRecs' original order.

Recover RedditRecs' own ranking order (#1, #2, #3 ...):

```bash
python3 rankings.py
```

Writes `output/rankings.csv` (every list with its ranked products), `ranking_lists.csv`
(one row per list), `category_meta.csv` (Reddit users and threads analysed per category)
and `use_case_evidence.csv` (Reddit snippets behind each "best for" use case). Rankings
come from the filter pages and from the overall top 5 embedded in series pages; category
and `/lists` pages were rendered in the browser, so their archived copies hold no rankings.

`python3 inspect_pages.py` writes `output/page_shapes.json`, a small map of how category,
filter, series and list pages are structured (used to build the ranking extractor).

## Notes

- Only snapshots taken **before 2026-11-02** are used. After that date every URL returned a
  "has shut down" page.
- archive.org throttles fast clients; the downloader backs off automatically. If it is
  throttled constantly, stop it, wait 30–60 minutes and restart with `--gap 1` or `--workers 2`.
- Amazon links contain the original site's affiliate tag (`redditrecs-g-20`); replace it if
  links are ever reused.
- The Reddit comments belong to their authors, and the summaries and rankings are the original
  site's work. Use the data for research; republishing it as-is carries copyright risk.
- Reddit announced in Sept 2026 that its public API will close by March 2027, so a new site
  will need a licensed data source.

## Curating the rankings

`scripts/curation.json` holds the editable rules the data builder applies: `exclude` drops products that
are years old, and `families` merges variants of one product line into a single entry (and can rename
long retailer titles). Each rule is a regular expression tested against the product's normalised name.
After a run the builder prints "possible duplicates" it could not merge, so you can add rules for them.
Entries that combine several products show "Includes N other variants" and list them on their page.

Products merged by a `families` rule also redirect from their old web addresses to the merged page, so links and
search results keep working. `distinct` lists products the duplicate check flags that are really separate models
(for example a Pro and a non-Pro version), so the build stops reporting them.

`rename` gives one product a shorter display name. Its old web address then redirects to the new one
automatically (the builder writes `site/public/_redirects`, which Cloudflare reads), so existing links and
search results keep working. After a run the builder also lists any product names over 50 characters, so you
can add `rename` rules for the ones that read badly.

## Website (AskTheSubs)

`site/` is a static [Astro](https://astro.build) site, served by Cloudflare Workers with static assets
(`site/wrangler.jsonc`). The brand name, tagline, disclaimer and affiliate settings live in
`site/src/config.ts`.

Build the data for the six launch categories (robot vacuums, baby strollers, fitness trackers,
ultrawide monitors, wireless earbuds, vacuum cleaners) from the CSVs in `output/`:

```bash
python3 scripts/build_site_data.py
```

This merges duplicate products, recomputes sentiment from the opinion rows (one vote per Redditor),
ranks by a confidence score, keeps a few short quotes with links to the original comments and writes
`site/src/data/generated/`. That folder is gitignored, so the data stays on your machine.
Without it the site builds from a clearly marked sample fixture and is set to `noindex`.

```bash
cd site
npm install
npm run dev        # preview at http://localhost:4321
npm run build      # static output in site/dist
npm run deploy     # build, then deploy with wrangler (needs `npx wrangler login` once)
```

Environment variables (set in `site/.env` or the build environment):

- The Amazon Associates tag is **not** an environment variable: it is the one line in
  `site/affiliate-tag.mjs` (currently `reddit-mentions-20`), so a stray `.env` value cannot change it.
  Every Amazon link uses it, is marked `rel="sponsored"`, and the affiliate disclosure is shown.
  **Publishing stops if any Amazon link in the built site is missing the tag, carries a different one, or
  the old archive tag `redditrecs-g-20` appears anywhere**: the check is `site/scripts/check-amazon-links.mjs`,
  run by `npm run deploy` and `./scripts/publish.sh` (run it alone with `cd site && npm run check:amazon`
  after a build).
- `PUBLIC_NOINDEX=true`: keep search engines out (previews).
- `PUBLIC_PRODUCT_IMAGES=true`: show the Amazon-hosted product photos stored in the data. Off by default
  (the site shows a drawn illustration per category instead). Use it for noindex previews only, and
  switch to Amazon's official image links once your Associates account is approved: check the Associates
  Program Operating Agreement before showing Amazon's images on a live site.
- More photos: the data builder also asks Amazon for the picture of any product that has an Amazon id but no
  archived photo, and keeps it only if a real 500x500 JPEG comes back. It prints how many photos came from the
  archive and how many from Amazon by product id; answers are remembered in `output/asin_photos.json`.
  `python3 scripts/build_site_data.py --no-asin-photos` skips this, `--refresh-asin-photos` asks again. This uses an
  older Amazon image address that is not documented and could stop working; products then fall back to the
  drawn illustration. The same Associates-terms question as for the other photos applies.

## Indexing and comparison pages

`site/src/lib/indexing.mjs` decides which pages search engines may index, for both the page tags and the sitemap:

- **Thin product pages** (fewer than 40 Redditors, or fewer than 3 usable quotes) are built and linked but carry
  `noindex, follow` and never go in the sitemap. Change the thresholds there.
- **Comparison pages** (`/<category>/compare/<a>-vs-<b>/`) are built only for pairs Reddit actually compares: at least
  5 Redditors and 3 threads in common, and either a quote that names both products or 15+ shared Redditors, but
  not pairs where 70% or more of the smaller product's Redditors are shared (the archive cannot tell those apart; the
  build lists them so you can merge true duplicates). Each
  product keeps its 6 strongest pairs (`build_comparisons` in `scripts/build_site_data.py`). They are `noindex` until
  their path is added to `INDEXED_COMPARISONS`, which also puts them in the sitemap, so they can be released in batches.

## Page dates, structured data and llms.txt

- **Page dates.** `build_site_data.py` fingerprints the data each page shows and records the day it last changed in
  `output/page_dates.json` (history, on your machine) and `site/src/data/generated/page_dates.json` (for the site). A page's
  date moves only when its data changes, so rebuilding unchanged data keeps the old dates. That date is used for the
  sitemap's `<lastmod>`, the "Updated" line on ranking, product and comparison pages, and `dateModified` in structured
  data. Search engines ignore `<lastmod>` when it is just the build date, which is why it is not used. Template-only
  changes do not move the dates. Pages with no recorded date (for example `/contact/`) get no `<lastmod>`.
- **Structured data.** `site/src/layouts/Base.astro` puts one connected graph on every page (Organization, WebSite and the
  page itself with its date). Pages add their own FAQ, breadcrumb and item-list nodes through the `jsonld` prop and set
  `pageType` (`CollectionPage` for rankings, `AboutPage`, `ContactPage`). There is deliberately no `Product` /
  `AggregateRating` markup: Google's review-snippet rules require ratings collected from users on your own site, and
  these scores come from Reddit.
- **`/llms.txt`** (`site/src/pages/llms.txt.ts`) is a plain-text guide for AI assistants: what the site is, how rankings
  work, and links to each ranking, its top 10 indexable products and the released comparisons. It is built from the
  same data, so it stays current. Whether a given assistant reads it is not something we can confirm.

## Publishing

On your own machine, from the project root:

```bash
./scripts/publish.sh
```

It pulls the latest code, rebuilds the data, installs dependencies and deploys. Put your preview flags
in `site/.env` (gitignored) so they are used on every deploy:

```
PUBLIC_NOINDEX=true
PUBLIC_PRODUCT_IMAGES=true
```

To go live, set `PUBLIC_NOINDEX=false` (or delete the line) and publish again. First time only:
`cd site && npx wrangler login`.
