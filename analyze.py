#!/usr/bin/env python3
"""
Summarise the extracted RedditRecs data so we can decide which categories to
launch first. Run after extract.py:

    python3 analyze.py

Reads output/*.csv and writes:
    output/report.md              human-readable report (open in any text editor / VS Code)
    output/category_summary.csv   one row per category with all metrics
    output/top_products.csv       top 10 products per category
    output/subreddits.csv         subreddit usage overall and per category
    output/report_summary.json    compact numbers (small enough to paste or send)
"""
import csv, json, math, os, statistics, sys
from collections import Counter, defaultdict

OUT = "output"
csv.field_size_limit(min(sys.maxsize, 2**31 - 1))


def read(name):
    path = os.path.join(OUT, name)
    if not os.path.exists(path):
        sys.exit(f"missing {path} - run extract.py first")
    with open(path, encoding="utf-8", newline="") as f:
        yield from csv.DictReader(f)


def num(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def wilson_lower(pos, total, z=1.96):
    """Lower bound of the 95% confidence interval for the share of positive
    opinions. Rewards products that are both liked and widely discussed."""
    if total <= 0:
        return 0.0
    p = pos / total
    d = 1 + z * z / total
    c = p + z * z / (2 * total)
    m = z * math.sqrt(p * (1 - p) / total + z * z / (4 * total * total))
    return (c - m) / d


def main():
    cats = {r["category_slug"]: r["category_name"] for r in read("categories.csv")}

    # ---- products -------------------------------------------------------
    models = defaultdict(list)
    for r in read("models.csv"):
        models[r["category_slug"]].append(r)

    # ---- opinions (large file: stream it) -------------------------------
    op_rows = Counter(); op_ids = defaultdict(set); users = defaultdict(set)
    subs_cat = defaultdict(Counter); subs_all = Counter(); years = defaultdict(Counter)
    latest = {}; sentiments = defaultdict(Counter)
    for r in read("opinions.csv"):
        c = r["category_slug"]
        op_rows[c] += 1
        op_ids[c].add(r["opinion_id"])
        if r["reddit_username"]:
            users[c].add(r["reddit_username"])
        if r["subreddit"]:
            subs_cat[c][r["subreddit"]] += 1
            subs_all[r["subreddit"]] += 1
        d = r["comment_date"][:10]
        if d:
            years[c][d[:4]] += 1
            if d > latest.get(c, ""):
                latest[c] = d
        sentiments[c][r["sentiment"] or "unknown"] += 1

    use_cases = Counter(r["category_slug"] for r in read("use_cases.csv"))
    use_case_rows = list(read("use_cases.csv"))

    # ---- per-category summary --------------------------------------------
    summary = []
    for c in sorted(set(cats) | set(models)):
        ms = models.get(c, [])
        prices = [p for p in (num(m["lowest_price"]) for m in ms) if p]
        with_amazon = sum(1 for m in ms if m["amazon_url"])
        recent = sum(n for y, n in years[c].items() if y >= "2025")
        total_dated = sum(years[c].values())
        summary.append({
            "category_slug": c,
            "category_name": cats.get(c, c),
            "products": len(ms),
            "opinion_rows": op_rows[c],
            "unique_opinions": len(op_ids[c]),
            "unique_reddit_users": len(users[c]),
            "subreddits": len(subs_cat[c]),
            "top_subreddits": ", ".join(f"r/{s}" for s, _ in subs_cat[c].most_common(3)),
            "share_comments_2025_or_later": round(recent / total_dated, 2) if total_dated else None,
            "latest_comment": latest.get(c),
            "use_cases": use_cases[c],
            "products_with_amazon_link": with_amazon,
            "median_price_usd": round(statistics.median(prices), 2) if prices else None,
            "positive_share": round(sentiments[c]["positive"] / max(1, sum(sentiments[c].values())), 2),
        })
    summary.sort(key=lambda s: s["unique_reddit_users"], reverse=True)

    def write_csv(name, rows):
        if not rows:
            return
        with open(os.path.join(OUT, name), "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
            w.writeheader(); w.writerows(rows)

    write_csv("category_summary.csv", summary)

    # ---- top products per category ----------------------------------------
    top_rows = []
    for c, ms in models.items():
        scored = []
        for m in ms:
            pos, neu, neg = (int(num(m[k]) or 0) for k in ("positive", "neutral", "negative"))
            n = int(num(m["user_opinion_count"]) or 0)
            scored.append((wilson_lower(pos, pos + neg), n, pos, neu, neg, m))
        scored.sort(key=lambda t: (t[0], t[1]), reverse=True)
        for rank, (score, n, pos, neu, neg, m) in enumerate(scored[:10], 1):
            top_rows.append({"category_slug": c, "rank": rank, "brand": m["brand_name"], "product": m["model_name"],
                             "score": round(score, 3), "opinions": n, "positive": pos, "neutral": neu,
                             "negative": neg, "lowest_price": m["lowest_price"], "amazon_url": m["amazon_url"]})
    write_csv("top_products.csv", top_rows)

    sub_rows = [{"subreddit": s, "category_slug": "ALL", "comments": n} for s, n in subs_all.most_common(200)]
    for c, cnt in subs_cat.items():
        sub_rows += [{"subreddit": s, "category_slug": c, "comments": n} for s, n in cnt.most_common(10)]
    write_csv("subreddits.csv", sub_rows)

    # ---- markdown report --------------------------------------------------
    all_years = Counter()
    for c in years:
        all_years.update(years[c])
    L = []
    L.append("# RedditRecs archive - data report\n")
    L.append(f"- Categories: **{len(summary)}**")
    L.append(f"- Products: **{sum(s['products'] for s in summary):,}**")
    L.append(f"- Opinion rows: **{sum(op_rows.values()):,}** "
             f"(unique opinions: {sum(len(v) for v in op_ids.values()):,})")
    L.append(f"- Distinct subreddits: **{len(subs_all):,}**")
    L.append(f"- Comments by year: " + ", ".join(f"{y}: {n:,}" for y, n in sorted(all_years.items())))
    L.append("\nScore in the product tables = lower bound of the 95% confidence interval for the share of "
             "positive vs negative opinions (Wilson score). It favours products that are both liked and "
             "widely discussed. This is our own ranking, not RedditRecs' original order.\n")

    L.append("## Categories ranked by Reddit discussion (unique users)\n")
    L.append("| # | Category | Users | Opinions | Products | Subreddits | 2025+ share | Median $ | Use cases | Top subreddits |")
    L.append("|---|---|---|---|---|---|---|---|---|---|")
    for i, s in enumerate(summary, 1):
        L.append(f"| {i} | {s['category_name']} | {s['unique_reddit_users']:,} | {s['unique_opinions']:,} | "
                 f"{s['products']} | {s['subreddits']} | {s['share_comments_2025_or_later']} | "
                 f"{s['median_price_usd']} | {s['use_cases']} | {s['top_subreddits']} |")

    L.append("\n## Top 30 subreddits overall\n")
    L.append("| Subreddit | Comments |")
    L.append("|---|---|")
    for s, n in subs_all.most_common(30):
        L.append(f"| r/{s} | {n:,} |")

    L.append("\n## Top 5 products per category\n")
    by_cat = defaultdict(list)
    for r in top_rows:
        by_cat[r["category_slug"]].append(r)
    for s in summary:
        rows = by_cat.get(s["category_slug"], [])[:5]
        if not rows:
            continue
        L.append(f"### {s['category_name']}\n")
        L.append("| # | Product | Score | Opinions | + / ~ / - | Price |")
        L.append("|---|---|---|---|---|---|")
        for r in rows:
            L.append(f"| {r['rank']} | {r['brand']} {r['product']} | {r['score']} | {r['opinions']} | "
                     f"{r['positive']} / {r['neutral']} / {r['negative']} | {r['lowest_price'] or '-'} |")
        L.append("")

    L.append("## \"Best for\" use cases per category\n")
    uc_by_cat = defaultdict(list)
    for u in use_case_rows:
        uc_by_cat[u["category_slug"]].append(u)
    for s in summary:
        ucs = uc_by_cat.get(s["category_slug"])
        if ucs:
            L.append(f"- **{s['category_name']}** ({len(ucs)}): " + "; ".join(u["use_case_name"] for u in ucs))

    with open(os.path.join(OUT, "report.md"), "w", encoding="utf-8") as f:
        f.write("\n".join(L) + "\n")

    compact = {
        "totals": {"categories": len(summary), "products": sum(s["products"] for s in summary),
                   "opinion_rows": sum(op_rows.values()),
                   "unique_opinions": sum(len(v) for v in op_ids.values()),
                   "subreddits": len(subs_all), "comments_by_year": dict(sorted(all_years.items()))},
        "categories": summary,
        "top_subreddits": subs_all.most_common(30),
        "top3_per_category": {c: [f"{r['brand']} {r['product']} ({r['opinions']} opinions, score {r['score']})"
                                  for r in rows[:3]] for c, rows in by_cat.items()},
    }
    with open(os.path.join(OUT, "report_summary.json"), "w", encoding="utf-8") as f:
        json.dump(compact, f, indent=1, ensure_ascii=False)

    print(f"categories: {len(summary)}   products: {compact['totals']['products']:,}   "
          f"opinion rows: {compact['totals']['opinion_rows']:,}   subreddits: {len(subs_all):,}")
    print("wrote output/report.md, category_summary.csv, top_products.csv, subreddits.csv, report_summary.json")
    print("\nTop 10 categories by unique Reddit users:")
    for s in summary[:10]:
        print(f"  {s['category_name']:<30} {s['unique_reddit_users']:>7,} users  {s['products']:>4} products  "
              f"latest comment {s['latest_comment']}")


if __name__ == "__main__":
    main()
