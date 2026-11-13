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
- Amazon links in the archive contain the original site's affiliate tag (`redditrecs-g-20`); the site builder keeps only the ASIN, and the deploy check fails if that tag ever appears. Replace it if
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

- Amazon Associates tag: fixed in `site/affiliate-tag.mjs` (`reddit-mentions-20`); there is no environment override. Every buy link is
  built in one place (`buyUrl()` in `site/src/config.ts`), carries `rel="sponsored nofollow noopener"`, and links only to
  `https://www.amazon.com/dp/<ASIN>?tag=...`. `npm run deploy` runs `site/scripts/check-affiliate-links.mjs` first and refuses to deploy
  if any Amazon link in the built site lacks the tag or has a different one, or if the old redditrecs tag appears anywhere
  (`npm run check:links` runs it by hand). The builder validates every ASIN (10 characters, A-Z/0-9) so dirty source data cannot
  produce a broken link. The disclosure "As an Amazon Associate I earn from qualifying purchases." is in the footer, next to the buy
  buttons and on the method page; check it against the current Associates Operating Agreement.
- `PUBLIC_NOINDEX=true`: keep search engines out (previews).
- `PUBLIC_PRODUCT_IMAGES=true`: show the Amazon-hosted product photos stored in the data. Off by default
  (the site shows a drawn illustration per category instead). Use it for noindex previews only, and
  switch to Amazon's official image links once your Associates account is approved: check the Associates
  Program Operating Agreement before showing Amazon's images on a live site.

### Indexing while the site is new: a daily release plan

Only a few pages are submitted to search engines at first, then a few more each day. `site/launch-pages.json` holds the plan:
`paths` and `categories` are live from day 0 (8 pages: home, method, 6 categories), and `queue` (about 335 topics, sorted by
monthly search volume of the plain "best X" query) is released in order, **5-10 per release day** (a different number each day,
but identical on every build of the same date). For the first `schedule.everyOtherDayForFirstDays` days (10) after
`schedule.startDate` pages go live every other day; after that, every day. The released set is computed from the build date (UTC), so you only need to
rebuild and deploy once a day:

```bash
./scripts/publish.sh
```

- `node scripts/release-plan.mjs 14` prints today's plan and the next 14 days. `PUBLIC_RELEASE_DATE=YYYY-MM-DD` previews any date.
- If you skip days, the next deploy releases everything due by then (catch-up). To avoid a big batch, deploy daily.
- The sitemap (`/sitemap-index.xml`), the `index`/`noindex` robots tags, the Markdown files and `llms.txt` all use the same released
  set, so they cannot disagree. Pages not yet released are published but `noindex, follow`, because a sitemap alone would not stop
  search engines indexing pages they find through links.
- Reorder `queue` or add/remove topics freely (slugs without `best-` / `-reddit`). `heldOut` lists finance, insurance, software-service,
  health-device and safety topics that are not queued; add them by hand if you want them.
- `PUBLIC_INDEX_PAGES=all` in `site/.env` indexes everything at once; `PUBLIC_NOINDEX=true` overrides all of it (previews).

### Automating the daily release (macOS)

The release plan only advances when the site is rebuilt and deployed, and the site data lives only on your machine (it is not on
GitHub), so the automation runs on your Mac as a launchd job that wakes every hour:

```bash
scripts/install-daily-release.sh              # install and start
scripts/install-daily-release.sh status       # state, last deploy, last log lines
touch site/.release-paused                    # pause (delete the file to resume)
scripts/install-daily-release.sh uninstall
```

Each wake-up does nothing until a new UTC day has started, then runs `npm run deploy` (build, affiliate-link check, deploy) at most
once per UTC day and checks the live sitemap and home-page robots tag against `scripts/release-plan.mjs`. If the Mac was asleep at
midnight UTC it runs at the next wake-up; a failed deploy is retried the next hour. It skips (and sends a macOS notification) when the
project has uncommitted changes or the site data is missing. It does not `git pull` or rebuild the data: it deploys the code as it is on
disk. Log: `~/.askthesubs/release.log`. Requirements: the Mac must be awake sometime after 00:00 UTC, `wrangler login` must have been done
once, and the project folder must be readable by background jobs (macOS may block jobs from reading Desktop or Documents until bash is
given Full Disk Access, or the project is moved elsewhere).

### Markdown versions and llms.txt

Every released page has a Markdown copy at its address plus `.md` (for example `/best-robot-vacuums-reddit.md`), built from the same
data and wording as the HTML page. `/llms.txt` follows the llmstxt.org convention (title, summary, links), and `/llms-full.txt` holds
all released pages in one file. The `.md` files and `llms-full.txt` are sent with `X-Robots-Tag: noindex` (`site/public/_headers`) so
they do not compete with the HTML pages. llms.txt is a proposed convention, not a standard, and there is no evidence that search
engines use it for ranking.

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
