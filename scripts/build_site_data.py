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
    link to the original comment and the title of its thread, and never writes Reddit usernames
  * lists the most-discussed Reddit threads behind each category ("discussions analyzed")
  * applies scripts/curation.json: drops products that are years old, shortens awkward product
    names ("rename", with an automatic redirect from the old address) and merges product families
    you define (Miele Complete C3 variants, Garmin Instinct 3 editions...), keeping a list of the
    variants that were combined. Edit that file to change the rules.
  * folds variants of one product family into a single entry, using the product families
    (series) RedditRecs defined, which extract.py saves in output/json
  * stores the Amazon-hosted product photo link (never a copy of the photo); the site only
    shows photos when PUBLIC_PRODUCT_IMAGES=true
  * stores the Amazon product id (ASIN) only, never the old affiliate tag; the link goes to the
    most-discussed variant that has an Amazon listing
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


def thread_url(permalink):
    """Reddit thread link from a comment permalink (/r/sub/comments/<id>/<slug>/<comment>/), or None."""
    m = re.search(r"(/r/[^/]+/comments/[a-z0-9]+(?:/[^/?#]*)?)", permalink or "", re.I)
    return "https://www.reddit.com" + m.group(1).rstrip("/") + "/" if m else None


def pick_quotes(cands, sentiment, limit):
    """Most specific, informative quotes of one sentiment; one per Redditor, no repeats."""
    chosen, seen_users, seen_text = [], set(), set()
    # Some archived quotes are cut off mid-sentence: prefer ones that end cleanly, then the most specific.
    clean = lambda t: t.rstrip().endswith((".", "!", "?", '"', "'", ")", "\u201d"))
    pool = sorted((c for c in cands if c[2] == sentiment), key=lambda c: (not clean(c[3]), -c[0], -len(c[3])))
    for spec, user, _s, text, sub, date, url, thread in pool:
        key = text.lower()
        if user in seen_users or key in seen_text:
            continue
        seen_users.add(user)
        seen_text.add(key)
        q = {"text": text, "sentiment": sentiment, "subreddit": sub, "date": date, "url": url}
        if thread:
            q["thread"] = thread[:140]
        chosen.append(q)
        if len(chosen) == limit:
            break
    return chosen


def tidy_name(s):
    """Remove trademark signs and accidentally repeated words ("Soundcore Soundcore A20i")."""
    s = re.sub("[\u2122\u00ae\u00a9\u2120]", "", s or "")
    s = re.sub(r"\b([A-Za-z]{3,})(\s+\1\b)+", r"\1", s, flags=re.I)
    return re.sub(r"\s+", " ", s).strip()


def load_curation(path):
    """Editable rules (scripts/curation.json): products to drop, and product families to merge."""
    empty = {"exclude": [], "families": [], "rename": []}
    if not path or not os.path.exists(path):
        return empty
    with open(path, encoding="utf-8") as f:
        d = json.load(f)
    return {k: [dict(r, _re=re.compile(r["match"])) for r in d.get(k, [])] for k in empty}


def first_rule(rules, category, normed):
    for r in rules:
        if r["category"] == category and r["_re"].search(normed):
            return r
    return None


def new_group(brand, name):
    return {"best": -1, "brand": brand, "name": name, "asin": None, "asin_n": -1, "img": None, "img_n": -1,
            "is_series": True, "users": defaultdict(list), "points": {}, "quotes": [], "subs": set(), "members": [], "threads": {}}


def merge_into(t, g):
    for u, lst in g["users"].items():
        t["users"][u].extend(lst)
    for k, (title, cnt) in g["points"].items():
        e = t["points"].setdefault(k, [title, 0])
        e[1] += cnt
    t["quotes"].extend(g["quotes"])
    for k, th in g["threads"].items():
        t["threads"].setdefault(k, {**th, "users": set()})["users"] |= th["users"]
    t["subs"] |= g["subs"]
    t["members"].extend(g["members"])
    if g["asin"] and g["asin_n"] >= t["asin_n"]:
        t["asin"], t["asin_n"] = g["asin"], g["asin_n"]
    if g["img"] and g["img_n"] >= t["img_n"]:
        t["img"], t["img_n"] = g["img"], g["img_n"]


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--data", default="output", help="folder with the CSVs from extract.py")
    ap.add_argument("--out", default=os.path.join("site", "src", "data", "generated"))
    ap.add_argument("--min-opinions", type=int, default=25, help="fewest Redditors for a product to be ranked")
    ap.add_argument("--top", type=int, default=40, help="most products per category")
    ap.add_argument("--categories-json", help="optional JSON file replacing the built-in category list")
    ap.add_argument("--redirects", default=os.path.join("site", "public", "_redirects"),
                    help="where to write redirects from old product addresses to renamed ones")
    ap.add_argument("--curation", default=os.path.join(os.path.dirname(os.path.abspath(__file__)), "curation.json"),
                    help="rules for dropping old products and merging product families")
    a = ap.parse_args()

    cats = json.load(open(a.categories_json, encoding="utf-8")) if a.categories_json else CATEGORIES
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
                                    "users": defaultdict(list), "points": {}, "quotes": [], "subs": set(), "members": [], "threads": {}})
        n = int(num(r["user_opinion_count"]) or 0)
        g["members"].append((n, tidy_name(display_name(r["brand_name"], r["model_name"]))))
        if sv:
            g["is_series"], g["brand"], g["name"] = True, sv[0], sv[1]
            in_series += 1
        elif n > g["best"]:
            g["best"], g["brand"], g["name"] = n, r["brand_name"], r["model_name"]
        # buy link: the most-discussed variant that has an Amazon listing
        asin = asin_of(r["amazon_url"])
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
        if r["subreddit"]:
            g["subs"].add(r["subreddit"])
        date = (r["comment_date"] or "")[:10]
        if date > through:
            through = date
        title = re.sub(r"\s+", " ", r.get("thread_title") or "").strip()
        if title and r["comment_permalink"]:
            turl = thread_url(r["comment_permalink"])
            th = g["threads"].setdefault(turl or (title.lower(), r["subreddit"]),
                                         {"title": title, "subreddit": r["subreddit"], "url": turl, "users": set()})
            th["users"].add(user)
        if r["quotes"] and r["comment_permalink"]:
            spec = num(r["specificity"]) or 0.0
            for q in r["quotes"].split(" || "):
                q = q.strip()
                if 50 <= len(q) <= 240:
                    g["quotes"].append((spec, user, s, q, r["subreddit"], date, r["comment_permalink"], title))
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

    # ---- curation: drop old products, merge product families ------------------------
    cur = load_curation(a.curation)
    kept, dropped, folded, renamed = {}, [], 0, 0
    for key, g in groups.items():
        normed = norm(tidy_name(display_name(g["brand"], g["name"])))
        if first_rule(cur["exclude"], key[0], normed):
            dropped.append(display_name(g["brand"], g["name"]))
            continue
        fam = first_rule(cur["families"], key[0], normed)
        if fam:
            fkey = (key[0], "family|" + norm(fam["name"]))
            if fkey not in kept:
                kept[fkey] = new_group(fam.get("brand") or g["brand"], fam["name"])
            merge_into(kept[fkey], g)
            folded += 1
        else:
            ren = first_rule(cur["rename"], key[0], normed)
            if ren:
                # Shorter display name; remember the old address so it can redirect to the new one.
                g["old_slugs"] = [slugify(tidy_name(display_name(g["brand"], g["name"])))] + list(ren.get("previous_slugs") or [])
                g["brand"], g["name"] = ren.get("brand") or g["brand"], ren["name"]
                renamed += 1
            kept[key] = g
    groups = kept
    if cur["exclude"] or cur["families"] or cur["rename"]:
        print(f"curation: dropped {len(dropped)} old products, merged {folded} listings into "
              f"{sum(1 for k in groups if k[1].startswith('family|'))} product families, "
              f"renamed {renamed}", flush=True)

    # ---- rank and write ---------------------------------------------------------
    os.makedirs(a.out, exist_ok=True)
    for old in os.listdir(a.out):
        if old.endswith(".json"):
            os.remove(os.path.join(a.out, old))
    meta_cats, all_subs, redirects, long_names = [], set(), [], []
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
            seen_v, variants = set(), []
            for _n, vname in sorted(g["members"], key=lambda m: -m[0]):
                if norm(vname) not in seen_v:
                    seen_v.add(norm(vname))
                    variants.append(vname)
            shown_name = tidy_name(display_name(g["brand"], g["name"]))
            variants = [v for v in variants if norm(v) != norm(shown_name)][:10] if len(seen_v) > 1 else []
            ranked.append({
                "name": shown_name, "brand": g["brand"], "opinions": n, "variants": variants,
                "positive": pos, "neutral": neu, "negative": neg,
                "share_positive": round(100 * pos / n), "share_negative": round(100 * neg / n),
                "score": round(100 * wilson(pos + 0.5 * neu, n)), "_s": wilson(pos + 0.5 * neu, n),
                "asin": g["asin"], "image": g["img"], "_subs": g["subs"], "_threads": g["threads"], "_old_slugs": g.get("old_slugs") or [],
                "likes": [{"title": t, "count": k} for t, k in likes],
                "dislikes": [{"title": t, "count": k} for t, k in dislikes],
                "quotes": pick_quotes(g["quotes"], "positive", 3) + pick_quotes(g["quotes"], "negative", 2),
            })
        ranked.sort(key=lambda p: (-p["_s"], -p["opinions"]))
        ranked = ranked[: a.top]
        used = set()
        pooled = {}
        for i, p in enumerate(ranked, 1):
            p.pop("_s")
            all_subs |= p.pop("_subs")
            for k, th in p.pop("_threads").items():
                pooled.setdefault(k, {**th, "users": set()})["users"] |= th["users"]
            slug, base, k = slugify(p["name"]), slugify(p["name"]), 2
            while slug in used:
                slug, k = f"{base}-{k}", k + 1
            used.add(slug)
            p["rank"], p["slug"] = i, slug
            for old_slug in p.pop("_old_slugs"):
                if old_slug != slug:
                    redirects.append((c["slug"], old_slug, slug))
            if len(p["name"]) > 50:
                long_names.append((c["slug"], p["name"]))
        lines = {}
        for p in ranked:
            toks = norm(p["name"]).split()
            btoks = norm(p["brand"]).split()
            if toks[: len(btoks)] == btoks:
                toks = toks[len(btoks):]
            lines.setdefault((norm(p["brand"]), tuple(toks[:2])), []).append(p["name"])
        maybe = [v for v in lines.values() if len(v) > 1]
        if maybe:
            print(f"  possible duplicates in {c['name']} (add a rule to scripts/curation.json if they are one product):")
            for v in maybe[:12]:
                print("     - " + " | ".join(x[:40] for x in v))
        with open(os.path.join(a.out, c["slug"] + ".json"), "w", encoding="utf-8") as f:
            top_threads = sorted(pooled.values(), key=lambda t: (-len(t["users"]), t["title"]))[:10]
            discussions = {"total": len(pooled),
                           "top": [{"title": t["title"][:160], "subreddit": t["subreddit"], "url": t["url"],
                                    "redditors": len(t["users"])} for t in top_threads]}
            json.dump({"slug": c["slug"], "name": c["name"], "discussions": discussions, "products": ranked},
                      f, ensure_ascii=False, separators=(",", ":"))
        meta_cats.append({"slug": c["slug"], "name": c["name"], "products": len(ranked),
                          "opinions": sum(p["opinions"] for p in ranked),
                          "top_pick": ranked[0]["name"] if ranked else None})
        print(f"  {c['name']:<22} {len(ranked):>3} ranked products, top: {ranked[0]['name'] if ranked else '-'}")

    meta_cats = [m for m in meta_cats if m["products"] > 0]
    with open(os.path.join(a.out, "categories.json"), "w", encoding="utf-8") as f:
        json.dump({"fixture": False, "comments_through": through, "min_opinions": a.min_opinions,
                   "stats": {"products": sum(m["products"] for m in meta_cats),
                             "opinions": sum(m["opinions"] for m in meta_cats), "subreddits": len(all_subs)},
                   "categories": meta_cats}, f, ensure_ascii=False, indent=1)
    print(f"wrote {len(meta_cats)} categories to {a.out}")

    # Old addresses of renamed products -> new ones (Cloudflare reads _redirects from the site root).
    os.makedirs(os.path.dirname(a.redirects), exist_ok=True)
    with open(a.redirects, "w", encoding="utf-8") as f:
        for cat_slug, old, new in redirects:
            f.write(f"/{cat_slug}/{old}/ /{cat_slug}/{new}/ 301\n")
    print(f"wrote {len(redirects)} redirects for renamed products to {a.redirects}")
    if long_names:
        print(f"\n{len(long_names)} product names are over 50 characters. Add a 'rename' rule for the ones that read badly:")
        for cat_slug, name in long_names[:25]:
            print(f"  [{cat_slug}] {name}")


if __name__ == "__main__":
    main()
