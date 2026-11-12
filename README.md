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
