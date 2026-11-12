#!/usr/bin/env python3
"""
Build the website's data files from the CSVs that extract.py wrote to output/.
Run from the project root, after extract.py:

    python3 scripts/build_site_data.py

Writes site/src/data/generated/categories.json and one <category>.json per site
category. That folder is gitignored: the data stays on your machine and is
baked into the static site when you build it.

What it does to the raw archive data:
  * keeps the 6 launch categories (edit CATEGORIES below to change them) and
    merges related ones (baby strollers + travel strollers)
  * merges duplicate products ("Joolz Aer+" vs "Joolz AER+", "eero eero Max 7")
  * recomputes positive/neutral/negative from the opinion rows, one vote per
    Redditor per product, instead of trusting the archived summary counts
  * ranks by the Wilson lower bound of the approval rate (positive = 1, neutral = 0.5,
    negative = 0), and drops products with fewer than --min-opinions Redditors
  * keeps a few short quotes per product (preferring ones that end cleanly) with the
    link to the original comment, and never writes Reddit usernames
  * stores the Amazon product id (ASIN) only, never the old affiliate tag
"""
import argparse, csv, json, math, os, re, sys, unicodedata
from collections import Counter, defaultdict

csv.field_size_limit(min(sys.maxsize, 2**31 - 1))

CATEGORIES = [
    {"slug": "robot-vacuums", "name": "Robot Vacuums", "members": ["robot-vacuum"]},
    {"slug": "baby-strollers", "name": "Baby Strollers", "members": ["baby-stroller", "travel-stroller"]},
    {"slug": "fitness-trackers", "name": "Fitness Trackers", "members": ["fitness-tracker"]},
    {"slug": "ultrawide-monitors", "name": "Ultrawide Monitors", "members": ["ultrawide-monitor"]},
    {"slug": "wireless-earbuds", "name": "Wireless Earbuds", "members": ["wireless-earbuds"]},
    {"slug": "vacuum-cleaners", "name": "Vacuum Cleaners", "members": ["vacuum-cleaner"]},
]

SENT = {"positive": "positive", "pos": "positive", "1": "positive",
        "neutral": "neutral", "0": "neutral",
        "negative": "negative", "neg": "negative", "-1": "negative"}


def norm(s):
    """Lowercase ascii words only; '+' becomes 'plus' so Aer+ and Aer stay different."""
    s = unicodedata.normalize("NFKD", s or "").replace("+", " plus ").replace("&", " and ")
    s = "".join(ch for ch in s if not unicodedata.combining(ch))
    return re.sub(r"[^a-z0-9]+", " ", s.lower()).strip()


def product_key(brand, name):
    b, n = norm(brand), norm(name)
    if b and n.startswith(b + " "):
        n = n[len(b) + 1:]
    return f"{b}|{n}"


def display_name(brand, name):
    if brand and norm(name).startswith(norm(brand)):
        return name.strip()
    return f"{brand} {name}".strip()


def slugify(s):
    return norm(s).replace(" ", "-")[:80].strip("-") or "product"


def wilson(pos, n, z=1.96):
    if n <= 0:
        return 0.0
    p = pos / n
    d = 1 + z * z / n
    c = p + z * z / (2 * n)
    m = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    return max(0.0, (c - m) / d)


def num(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def asin_of(url):
    m = re.search(r"/dp/([A-Z0-9]{10})", url or "")
    return m.group(1) if m else None


def read(folder, name):
    path = os.path.join(folder, name)
    if not os.path.exists(path):
        sys.exit(f"missing {path} - run extract.py first")
    with open(path, encoding="utf-8", newline="") as f:
        yield from csv.DictReader(f)


def pick_quotes(cands, sentiment, limit):
    """Most specific, informative quotes of one sentiment; one per Redditor, no repeats."""
    chosen, seen_users, seen_text = [], set(), set()
    # Some archived quotes are cut off mid-sentence: prefer ones that end cleanly, then the most specific.
    clean = lambda t: t.rstrip().endswith((".", "!", "?", '"', "'", ")", "\u201d"))
    pool = sorted((c for c in cands if c[2] == sentiment), key=lambda c: (not clean(c[3]), -c[0], -len(c[3])))
    for spec, user, _s, text, sub, date, url in pool:
        key = text.lower()
        if user in seen_users or key in seen_text:
            continue
        seen_users.add(user)
        seen_text.add(key)
        chosen.append({"text": text, "sentiment": sentiment, "subreddit": sub, "date": date, "url": url})
        if len(chosen) == limit:
            break
    return chosen


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--data", default="output", help="folder with the CSVs from extract.py")
    ap.add_argument("--out", default=os.path.join("site", "src", "data", "generated"))
    ap.add_argument("--min-opinions", type=int, default=15, help="fewest Redditors for a product to be ranked")
    ap.add_argument("--top", type=int, default=60, help="most products per category")
    ap.add_argument("--categories-json", help="optional JSON file replacing the built-in category list")
    a = ap.parse_args()

    cats = json.load(open(a.categories_json, encoding="utf-8")) if a.categories_json else CATEGORIES
    member_to_site = {m: c for c in cats for m in c["members"]}

    # ---- products (merge duplicates) --------------------------------------
    groups, model_group = {}, {}
    for r in read(a.data, "models.csv"):
        c = member_to_site.get(r["category_slug"])
        if not c:
            continue
        key = (c["slug"], product_key(r["brand_name"], r["model_name"]))
        g = groups.setdefault(key, {"best": -1, "brand": "", "name": "", "asin": None, "price": None,
                                    "users": defaultdict(list), "points": {}, "quotes": []})
        n = int(num(r["user_opinion_count"]) or 0)
        if n > g["best"]:
            g["best"], g["brand"], g["name"] = n, r["brand_name"], r["model_name"]
        asin, price = asin_of(r["amazon_url"]), num(r["lowest_price"])
        if asin and (g["asin"] is None or (price is not None and (g["price"] is None or price < g["price"]))):
            g["asin"], g["price"] = asin, price
        model_group[(r["category_slug"], r["model_slug"])] = key
    print(f"{len(model_group):,} archived products -> {len(groups):,} after merging duplicates", flush=True)

    # ---- opinions (one vote per Redditor per product; quotes) -----------
    through, rows = "", 0
    for r in read(a.data, "opinions.csv"):
        key = model_group.get((r["category_slug"], r["model_slug"]))
        if not key:
            continue
        rows += 1
        if rows % 100000 == 0:
            print(f"  {rows:,} opinion rows read", flush=True)
        g = groups[key]
        user = r["reddit_username"] or r["opinion_id"]
        s = SENT.get(str(r["sentiment"]).strip().lower(), "neutral")
        g["users"][user].append(s)
        date = (r["comment_date"] or "")[:10]
        if date > through:
            through = date
        if r["quotes"] and r["comment_permalink"]:
            spec = num(r["specificity"]) or 0.0
            for q in r["quotes"].split(" || "):
                q = q.strip()
                if 50 <= len(q) <= 240:
                    g["quotes"].append((spec, user, s, q, r["subreddit"], date, r["comment_permalink"]))
    print(f"{rows:,} opinion rows used; newest comment {through}", flush=True)

    # ---- like / dislike summaries -------------------------------------------
    for r in read(a.data, "summary_points.csv"):
        key = model_group.get((r["category_slug"], r["model_slug"]))
        title = (r["title"] or "").strip()
        if not key or not title:
            continue
        kind = "likes" if r["type"] == "likes" else "dislikes"
        count = int(num(r["likes_count" if kind == "likes" else "dislikes_count"]) or 0)
        entry = groups[key]["points"].setdefault((kind, title.lower()), [title, 0])
        entry[1] += count

    # ---- rank and write ---------------------------------------------------------
    os.makedirs(a.out, exist_ok=True)
    for old in os.listdir(a.out):
        if old.endswith(".json"):
            os.remove(os.path.join(a.out, old))
    meta_cats = []
    for c in cats:
        ranked = []
        for key, g in groups.items():
            if key[0] != c["slug"]:
                continue
            counts = Counter()
            for sl in g["users"].values():
                top = Counter(sl).most_common()
                counts["neutral" if len(top) > 1 and top[0][1] == top[1][1] else top[0][0]] += 1
            n = sum(counts.values())
            if n < a.min_opinions:
                continue
            pos, neu, neg = counts["positive"], counts["neutral"], counts["negative"]
            likes = sorted(((t, k) for (kind, _), (t, k) in g["points"].items() if kind == "likes" and k > 0), key=lambda x: -x[1])[:4]
            dislikes = sorted(((t, k) for (kind, _), (t, k) in g["points"].items() if kind == "dislikes" and k > 0), key=lambda x: -x[1])[:4]
            ranked.append({
                "name": display_name(g["brand"], g["name"]), "brand": g["brand"], "opinions": n,
                "positive": pos, "neutral": neu, "negative": neg,
                "share_positive": round(100 * pos / n), "share_negative": round(100 * neg / n),
                "score": round(100 * wilson(pos + 0.5 * neu, n)), "_s": wilson(pos + 0.5 * neu, n),
                "asin": g["asin"],
                "likes": [{"title": t, "count": k} for t, k in likes],
                "dislikes": [{"title": t, "count": k} for t, k in dislikes],
                "quotes": pick_quotes(g["quotes"], "positive", 3) + pick_quotes(g["quotes"], "negative", 2),
            })
        ranked.sort(key=lambda p: (-p["_s"], -p["opinions"]))
        ranked = ranked[: a.top]
        used = set()
        for i, p in enumerate(ranked, 1):
            p.pop("_s")
            slug, base, k = slugify(p["name"]), slugify(p["name"]), 2
            while slug in used:
                slug, k = f"{base}-{k}", k + 1
            used.add(slug)
            p["rank"], p["slug"] = i, slug
        with open(os.path.join(a.out, c["slug"] + ".json"), "w", encoding="utf-8") as f:
            json.dump({"slug": c["slug"], "name": c["name"], "products": ranked}, f, ensure_ascii=False, separators=(",", ":"))
        meta_cats.append({"slug": c["slug"], "name": c["name"], "products": len(ranked),
                          "opinions": sum(p["opinions"] for p in ranked),
                          "top_pick": ranked[0]["name"] if ranked else None})
        print(f"  {c['name']:<22} {len(ranked):>3} ranked products, top: {ranked[0]['name'] if ranked else '-'}")

    meta_cats = [m for m in meta_cats if m["products"] > 0]
    with open(os.path.join(a.out, "categories.json"), "w", encoding="utf-8") as f:
        json.dump({"fixture": False, "comments_through": through, "min_opinions": a.min_opinions,
                   "categories": meta_cats}, f, ensure_ascii=False, indent=1)
    print(f"wrote {len(meta_cats)} categories to {a.out}")


if __name__ == "__main__":
    main()
