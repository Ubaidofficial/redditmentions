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
  * folds variants of one product family into a single entry, using the product families
    (series) RedditRecs defined, which extract.py saves in output/json
  * stores the Amazon-hosted product photo link (never a copy of the photo); the site only
    shows photos when PUBLIC_PRODUCT_IMAGES=true
  * stores the Amazon product id (ASIN) only, never the old affiliate tag; the link goes to the
    most-discussed variant that has an Amazon listing

Second source (--redrecs, default output/redrecs when it exists; see redrecs_scrape.py):
  * every redditrecs category in categories.csv becomes a site category (the 6 launch ones keep their names);
  * a redrecs product matched by ASIN (or brand + model inside a topic proven by ASIN matches) is attached to the
    redditrecs product as `second_opinion` (comment counts, approval, score). The two sources are never summed or
    averaged: their sentiment methods differ and redrecs comments carry no permalink, so they cannot be de-duplicated;
  * redrecs lists that match no redditrecs category become their own categories (source "redrecs", unit "comments").
    These are ranked by OUR confidence score (Wilson lower bound) rather than redrecs' own order, hold no quotes,
    and show the Reddit threads the analysis read;
  * redrecs' written text (summaries, comment snippets) is never copied.
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


GROUP_NAMES = {
    "home-kitchen": "Home & Kitchen", "beauty-skincare": "Beauty & Skincare", "health-wellness": "Health & Wellness",
    "tech": "Tech", "entertainment": "Entertainment", "food": "Food", "outdoor": "Outdoor", "pets": "Pets",
    "fitness": "Fitness", "apps-tools": "Apps & Tools", "fashion": "Fashion", "local": "Local", "health-beauty": "Beauty & Skincare",
}

def norm(s):
    """Lowercase ascii words only; '+' becomes 'plus' so Aer+ and Aer stay different."""
    s = re.sub("[\u2122\u00ae\u00a9\u2120]", "", s or "")  # TM, (R), (C), SM: NFKD would turn the TM sign into "tm"
    s = unicodedata.normalize("NFKD", s).replace("+", " plus ").replace("&", " and ")
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


URL_STYLE = "reddit"


def page_slug(base):
    """Public URL slug. style "reddit": /best-robot-vacuums-reddit/ (chosen); style "plain": /best-robot-vacuums/.
    OpenSEO data (Nov 2026) showed plain "best X" queries with 30-70x the volume of "best X reddit"."""
    base = re.sub(r"^best-", "", base)
    base = re.sub(r"-reddit$", "", base)
    return f"best-{base}-reddit" if URL_STYLE == "reddit" else f"best-{base}"


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


def load_series(folder):
    """(category, model slug) -> (brand, series name), from the decoded series pages that
    extract.py saved in <folder>/json. RedditRecs grouped variants of one product family into
    a series (e.g. Miele Complete C3 variants), so we use its grouping instead of guessing."""
    jdir = os.path.join(folder, "json")
    found = {}
    if not os.path.isdir(jdir):
        return found
    for fn in os.listdir(jdir):
        if "__series__" not in fn or not fn.endswith(".json"):
            continue
        try:
            with open(os.path.join(jdir, fn), encoding="utf-8") as f:
                d = json.load(f)
        except (OSError, ValueError):
            continue
        parts = (d.get("path") or "").strip("/").split("/") if isinstance(d, dict) else []
        if len(parts) != 3 or parts[1] != "series":  # skips junk URLs that were archived with extra path parts
            continue
        for k, v in (d.get("data") or {}).items():
            if k.startswith("series-pageData-") and isinstance(v, dict):
                sd = v.get("seriesData") or {}
                if not sd.get("name"):
                    continue
                for m in sd.get("models") or []:
                    if isinstance(m, dict) and m.get("slug"):
                        found[(parts[0], m["slug"])] = (sd.get("brand_name") or "", sd["name"])
    return found


def plural_name(name):
    return name.strip()


def list_topic_name(title):
    """'Best 3D Printers - From Ender to Prusa' -> '3D Printers'."""
    t = re.split(r"\s+[-\u2013\u2014:|]\s+", (title or "").strip())[0]
    t = re.sub(r"^best\s+", "", t, flags=re.I).strip()
    return t[:1].upper() + t[1:]


def load_redrecs(folder):
    """Ranking pages saved by redrecs_scrape.py -> list of dicts, one per list."""
    out = []
    if not folder or not os.path.isdir(folder):
        return out
    for fn in sorted(os.listdir(folder)):
        if not fn.endswith(".json"):
            continue
        try:
            with open(os.path.join(folder, fn), encoding="utf-8") as f:
                r = json.load(f)
        except (OSError, ValueError):
            continue
        if r.get("kind") != "analysis":
            continue
        a = r["data"]["analysis"]
        out.append({"slug": a["slug"], "title": a.get("title") or a["slug"], "group": a.get("category") or "",
                    "products": r["data"].get("products") or [], "threads": r.get("source_urls") or []})
    return out


def rr_counts(p):
    return (int(p.get("positiveMentions") or 0), int(p.get("neutralMentions") or 0), int(p.get("negativeMentions") or 0))


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
    ap.add_argument("--min-opinions", type=int, default=25, help="fewest Redditors for a product to be ranked")
    ap.add_argument("--top", type=int, default=40, help="most products per category")
    ap.add_argument("--categories-json", help="optional JSON file replacing the built-in category list")
    ap.add_argument("--opinions", help="path to opinions.csv (default: <data>/opinions.csv); a slimmed file without the quotes column also works")
    ap.add_argument("--redrecs", default="output/redrecs", help="folder with redrecs_scrape.py output ('' to skip the second source)")
    ap.add_argument("--url-style", choices=["reddit", "plain"], default="reddit",
                    help="reddit: /best-robot-vacuums-reddit/ (default); plain: /best-robot-vacuums/")
    ap.add_argument("--skip-groups", default="entertainment,local",
                    help="redrecs groups left out because they are not shoppable products (movies, local services); '' keeps all")
    ap.add_argument("--min-products", type=int, default=3, help="fewest ranked products for a category page to be published")
    ap.add_argument("--rr-min", type=int, default=25, help="fewest comments for a redrecs-only product to be ranked")
    ap.add_argument("--all-categories", action=argparse.BooleanOptionalAction, default=True,
                    help="also build every other category in categories.csv (default on)")
    a = ap.parse_args()

    global URL_STYLE
    URL_STYLE = a.url_style
    cats = json.load(open(a.categories_json, encoding="utf-8")) if a.categories_json else CATEGORIES
    if a.all_categories and not a.categories_json and os.path.exists(os.path.join(a.data, "categories.csv")):
        have = {m for c in cats for m in c["members"]}
        for r in read(a.data, "categories.csv"):
            if r["category_slug"] not in have:
                nm = r["category_name"] or r["category_slug"]
                cats.append({"slug": slugify(nm), "name": nm, "members": [r["category_slug"]]})  # plural, like the launch six
    member_to_site = {m: c for c in cats for m in c["members"]}

    # ---- products (merge duplicates) --------------------------------------
    series = load_series(a.data)
    groups, model_group, in_series = {}, {}, 0
    for r in read(a.data, "models.csv"):
        c = member_to_site.get(r["category_slug"])
        if not c:
            continue
        sv = series.get((r["category_slug"], r["model_slug"]))
        key = (c["slug"], ("series|" + product_key(*sv)) if sv else product_key(r["brand_name"], r["model_name"]))
        g = groups.setdefault(key, {"best": -1, "brand": "", "name": "", "asin": None, "asin_n": -1, "img": None, "img_n": -1, "is_series": False,
                                    "users": defaultdict(list), "points": {}, "quotes": [], "subs": set(), "asins": set()})
        n = int(num(r["user_opinion_count"]) or 0)
        if sv:
            g["is_series"], g["brand"], g["name"] = True, sv[0], sv[1]
            in_series += 1
        elif n > g["best"]:
            g["best"], g["brand"], g["name"] = n, r["brand_name"], r["model_name"]
        # buy link: the most-discussed variant that has an Amazon listing
        asin = asin_of(r["amazon_url"])
        if asin:
            g["asins"].add(asin)
        if asin and n >= g["asin_n"]:
            g["asin"], g["asin_n"] = asin, n
        # photo: only Amazon-hosted listing images (other retailers' images are not ours to point to);
        # the most-discussed variant that has one
        img = (r.get("img_url") or "").strip()
        if img.startswith("https://m.media-amazon.com/") and n >= g["img_n"]:
            g["img"], g["img_n"] = img, n
        model_group[(r["category_slug"], r["model_slug"])] = key
    print(f"{len(model_group):,} archived products -> {len(groups):,} after merging duplicates "
          f"({in_series:,} folded into {sum(1 for g in groups.values() if g['is_series']):,} product families)", flush=True)

    # ---- opinions (one vote per Redditor per product; quotes) -----------
    through, rows = "", 0
    op_rows = read(os.path.dirname(a.opinions) or ".", os.path.basename(a.opinions)) if a.opinions else read(a.data, "opinions.csv")
    for r in op_rows:
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
        if r["subreddit"]:
            g["subs"].add(r["subreddit"])
        date = (r["comment_date"] or "")[:10]
        if date > through:
            through = date
        if r.get("quotes") and r["comment_permalink"]:
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
    rr_lists = load_redrecs(a.redrecs) if a.redrecs else []
    rr_by_asin, rr_votes = {}, defaultdict(Counter)
    for L in rr_lists:
        for rp in L["products"]:
            if rp.get("asin"):
                cur = rr_by_asin.get(rp["asin"])
                if cur is None or sum(rr_counts(rp)) > sum(rr_counts(cur[1])):
                    rr_by_asin[rp["asin"]] = (L, rp)
    for key, g in groups.items():
        for asin in g["asins"]:
            if asin in rr_by_asin:
                rr_votes[rr_by_asin[asin][0]["slug"]][key[0]] += 1
    # a redrecs list is "the same topic" as a site category once two of its products matched by ASIN
    list_cat = {sl: v.most_common(1)[0][0] for sl, v in rr_votes.items() if sum(v.values()) >= 2}
    rr_by_name = defaultdict(dict)
    for L in rr_lists:
        cslug = list_cat.get(L["slug"])
        for rp in L["products"]:
            if cslug:
                rr_by_name[cslug].setdefault(product_key(rp.get("brand"), rp["name"]), (L, rp))
    cat_group = {}
    for sl, cslug in list_cat.items():
        g0 = next((L["group"] for L in rr_lists if L["slug"] == sl), "")
        cat_group.setdefault(cslug, Counter())[g0] += 1

    def second_opinion(cat_slug, asins, pk):
        hit = None
        for asin in asins:
            cand = rr_by_asin.get(asin)
            if cand and (hit is None or sum(rr_counts(cand[1])) > sum(rr_counts(hit[1]))):
                hit = cand
        hit = hit or rr_by_name[cat_slug].get(pk)
        if not hit:
            return None
        pos, neu, neg = rr_counts(hit[1])
        n = pos + neu + neg
        if n < 10:
            return None
        img = (hit[1].get("imageUrl") or "").strip()
        return {"comments": n, "share_positive": round(100 * pos / n), "share_negative": round(100 * neg / n),
                "score": round(100 * wilson(pos + 0.5 * neu, n)), "rank": hit[1].get("rank"), "of": len(hit[0]["products"]),
                "_img": img if img.startswith("https://m.media-amazon.com/") else None}

    meta_cats, all_subs = [], set()
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
                "asin": g["asin"], "image": g["img"], "_subs": g["subs"], "_asins": g["asins"],
                "_pk": product_key(g["brand"], g["name"]),
                "likes": [{"title": t, "count": k} for t, k in likes],
                "dislikes": [{"title": t, "count": k} for t, k in dislikes],
                "quotes": pick_quotes(g["quotes"], "positive", 3) + pick_quotes(g["quotes"], "negative", 2),
            })
        ranked.sort(key=lambda p: (-p["_s"], -p["opinions"]))
        ranked = ranked[: a.top]
        used = set()
        for i, p in enumerate(ranked, 1):
            p.pop("_s")
            all_subs |= p.pop("_subs")
            so = second_opinion(c["slug"], p.pop("_asins"), p.pop("_pk")) if rr_lists else None
            if so:
                img = so.pop("_img", None)
                if img and not p["image"]:  # fill a missing photo from the second source (Amazon-hosted only)
                    p["image"] = img
                p["second_opinion"] = so
            slug, base, k = slugify(p["name"]), slugify(p["name"]), 2
            while slug in used:
                slug, k = f"{base}-{k}", k + 1
            used.add(slug)
            p["rank"], p["slug"] = i, slug
        gk = cat_group.get(c["slug"])
        group = GROUP_NAMES.get(gk.most_common(1)[0][0], "Tech") if gk else "Tech & Gear"
        with open(os.path.join(a.out, page_slug(c["slug"]) + ".json"), "w", encoding="utf-8") as f:
            json.dump({"slug": page_slug(c["slug"]), "name": c["name"], "source": "redditrecs", "unit": "Redditors",
                       "group": group, "products": ranked}, f, ensure_ascii=False, separators=(",", ":"))
        meta_cats.append({"slug": page_slug(c["slug"]), "name": c["name"], "source": "redditrecs", "unit": "Redditors",
                          "group": group,
                          "products": len(ranked),
                          "opinions": sum(p["opinions"] for p in ranked),
                          "top_pick": ranked[0]["name"] if ranked else None})
        print(f"  {c['name']:<22} {len(ranked):>3} ranked products, top: {ranked[0]['name'] if ranked else '-'}")


    # ---- redrecs-only topics: comment-level rankings, ranked by OUR confidence score ----------
    used_slugs = {m["slug"] for m in meta_cats} | {page_slug(c["slug"]) for c in cats}
    n_rr_cats = n_rr_dropped = 0
    skip = {g.strip() for g in a.skip_groups.split(",") if g.strip()}
    n_skipped = 0
    for L in rr_lists:
        if L["group"] in skip:
            n_skipped += 1
            continue
        if L["slug"] in list_cat:
            n_rr_dropped += sum(1 for rp in L["products"] if sum(rr_counts(rp)) >= a.rr_min)
            continue
        ranked = []
        for rp in L["products"]:
            pos, neu, neg = rr_counts(rp)
            n = pos + neu + neg
            if n < a.rr_min:
                continue
            img = (rp.get("imageUrl") or "").strip()
            ranked.append({
                "name": display_name(rp.get("brand") or "", rp["name"]), "brand": rp.get("brand") or "", "opinions": n,
                "positive": pos, "neutral": neu, "negative": neg,
                "share_positive": round(100 * pos / n), "share_negative": round(100 * neg / n),
                "score": round(100 * wilson(pos + 0.5 * neu, n)), "_s": wilson(pos + 0.5 * neu, n),
                "asin": rp.get("asin") or None, "image": img if img.startswith("https://m.media-amazon.com/") else None,
                "likes": [], "dislikes": [], "quotes": [],
            })
        if len(ranked) < a.min_products:
            continue
        ranked.sort(key=lambda p: (-p["_s"], -p["opinions"]))
        ranked = ranked[: a.top]
        name = list_topic_name(L["title"])
        slug = base = page_slug(slugify(name))
        k = 2
        while slug in used_slugs:
            slug, k = f"{base}-{k}", k + 1
        used_slugs.add(slug)
        used = set()
        for i, p in enumerate(ranked, 1):
            p.pop("_s")
            ps, pb, kk = slugify(p["name"]), slugify(p["name"]), 2
            while ps in used:
                ps, kk = f"{pb}-{kk}", kk + 1
            used.add(ps)
            p["rank"], p["slug"] = i, ps
        threads = list(dict.fromkeys(u for u in L["threads"] if "/comments/" in u))[:12]
        group = GROUP_NAMES.get(L["group"], L["group"].replace("-", " ").title() or "Other")
        with open(os.path.join(a.out, slug + ".json"), "w", encoding="utf-8") as f:
            json.dump({"slug": slug, "name": name, "source": "redrecs", "unit": "comments", "group": group,
                       "threads_total": len(L["threads"]), "threads": threads, "products": ranked},
                      f, ensure_ascii=False, separators=(",", ":"))
        meta_cats.append({"slug": slug, "name": name, "source": "redrecs", "unit": "comments", "group": group,
                          "products": len(ranked), "opinions": sum(p["opinions"] for p in ranked),
                          "top_pick": ranked[0]["name"]})
        n_rr_cats += 1
    if rr_lists:
        print(f"  redrecs: {n_rr_cats} comment-level topics added; {len(list_cat)} lists matched a redditrecs category "
              f"(used as second opinions; {n_rr_dropped} further products there were not shown); "
              f"{n_skipped} non-shopping lists skipped ({a.skip_groups})")

    meta_cats = [m for m in meta_cats if m["products"] >= max(1, a.min_products)]
    with open(os.path.join(a.out, "categories.json"), "w", encoding="utf-8") as f:
        json.dump({"fixture": False, "comments_through": through, "min_opinions": a.min_opinions, "rr_min": a.rr_min,
                   "stats": {"products": sum(m["products"] for m in meta_cats),
                             "opinions": sum(m["opinions"] for m in meta_cats if m["unit"] == "Redditors"),
                             "comments": sum(m["opinions"] for m in meta_cats if m["unit"] == "comments"),
                             "topics": len(meta_cats), "subreddits": len(all_subs)},
                   "categories": meta_cats}, f, ensure_ascii=False, indent=1)
    print(f"wrote {len(meta_cats)} categories to {a.out}")


if __name__ == "__main__":
    main()
