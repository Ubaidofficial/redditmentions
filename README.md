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

## Second source: redrecs.com

`redrecs_scrape.py` crawls redrecs.com's sitemap politely (one request at a time, robots.txt honoured, `/api/` skipped)
and saves each ranking page's structured data to `output/redrecs/` (gitignored): ranks, products, ASINs, positive /
neutral / negative comment counts, and the Reddit threads each list read.

```bash
python3 redrecs_scrape.py            # resumable
python3 redrecs_scrape.py --refresh  # re-fetch pages saved before thread URLs were captured
```

`scripts/merge_sources.py` merges it with the redditrecs archive into `output/merged/products.csv` and a
`match_report.json` (only ~150 products match; the two sources are mostly complementary). Nothing is averaged or
summed: sentiment methods differ (median gap ~10 points) and redrecs comments carry no permalink, so they cannot be
de-duplicated. Pass `--rt-opinions output/opinions.csv` to add per-Redditor sentiment, recency and subreddit spread.

`scripts/build_site_data.py` uses both sources automatically when `output/redrecs/` exists: every redditrecs category
becomes a site category, matched redrecs products get a "second opinion" block, and unmatched redrecs lists become
"comment-level" topics ranked by our own confidence score. Redrecs' written text is never copied. Skip the second
source with `--redrecs ""`. Page URLs follow `--url-style reddit` (default, `/best-robot-vacuums-reddit/`); use
`--url-style plain` for `/best-robot-vacuums/`. OpenSEO data showed plain "best X" queries with 30-70x the volume of "best X reddit".

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

- `PUBLIC_AMAZON_TAG`: your Amazon Associates tag. Leave unset until the account is approved; buy
  links are then plain, non-affiliate links and no affiliate disclosure is shown.
- `PUBLIC_NOINDEX=true`: keep search engines out (previews).
- `PUBLIC_PRODUCT_IMAGES=true`: show the Amazon-hosted product photos stored in the data. Off by default
  (the site shows a drawn illustration per category instead). Use it for noindex previews only, and
  switch to Amazon's official image links once your Associates account is approved: check the Associates
  Program Operating Agreement before showing Amazon's images on a live site.

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
