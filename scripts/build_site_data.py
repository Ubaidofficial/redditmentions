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
  * for products that have an Amazon id but no archived photo, asks Amazon's image server for the picture of that
    id and keeps it only if a real JPEG comes back (Amazon returns a blank placeholder for ids it has no picture
    for). Answers are remembered in <data>/asin_photos.json; --no-asin-photos turns this off, --refresh-asin-photos
    asks again. The build prints how many photos came from where.
  * stores the Amazon product id (ASIN) only, never the old affiliate tag; the link goes to the
    most-discussed variant that has an Amazon listing
"""
import argparse, csv, json, math, os, re, sys, unicodedata, urllib.request
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor

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


# The ".01.LZZZZZZZ.jpg" form returns the 500x500 picture; other size options on this endpoint return a 160x160 thumbnail.
ASIN_PHOTO = "https://m.media-amazon.com/images/P/{asin}.01.LZZZZZZZ.jpg"


def fetch_asin_photo(asin):
    """Ask Amazon's image server for a product's picture by its id. Returns (url or None, definitive).
    A real picture is a JPEG of more than 2 KB: for ids it does not know, Amazon returns a tiny blank placeholder.
    `definitive` is False after a network error, so those answers are not remembered."""
    url = ASIN_PHOTO.format(asin=asin)
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=20) as r:
            ok = r.status == 200 and r.headers.get("content-type", "").startswith("image/")
            data = r.read() if ok else b""
        return (url if ok and len(data) > 2000 and data[:2] == b"\xff\xd8" else None), True
    except urllib.error.HTTPError as e:
        return None, e.code in (403, 404)
    except Exception:
        return None, False


def fill_asin_photos(ranked, cache, workers=8):
    """Give products that have an Amazon id but no photo in the archive the picture Amazon serves for that id.
    Answers are cached in `cache` (asin -> url or None) so later runs do not ask again. Returns how many were filled."""
    todo = sorted({p["asin"] for p in ranked if not p["image"] and p["asin"] and p["asin"] not in cache})
    if todo:
        with ThreadPoolExecutor(workers) as ex:
            for asin, (url, definitive) in zip(todo, ex.map(fetch_asin_photo, todo)):
                if definitive:
                    cache[asin] = url
    filled = 0
    for p in ranked:
        if not p["image"] and p["asin"] and cache.get(p["asin"]):
            p["image"] = cache[p["asin"]]
            p["_by_asin"] = True
            filled += 1
    return filled


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


# Words that say nothing about which product a comment means ("pro", "robot", "vacuum" ...).
GENERIC = set("""a an and the of for with in to by on new gen series edition model version plus pro max ultra mini lite air
plus se s x xl one two black white red blue grey gray silver green pink wireless bluetooth true earbuds earbud earphones
headphones buds noise cancelling canceling anc robot vacuum vacuums cleaner cleaners mop mopping self empty emptying base
station cordless corded stick upright canister bagless bagged handheld stroller strollers pram jogging travel system
lightweight double twin single monitor monitors gaming curved ultrawide inch hz hdr oled led ips qd smart watch watches
tracker trackers fitness gps band sport active complete""".split())


def product_terms(brand, names):
    """(model words, brand words) used to tell whether a comment is about this product."""
    btoks = set(norm(brand).split())
    model = set()
    for n in names:
        for t in norm(n).split():
            if t not in btoks and t not in GENERIC and (len(t) >= 3 or any(ch.isdigit() for ch in t) and len(t) >= 2):
                model.add(t)
    return model, {t for t in btoks if len(t) >= 3 and t not in GENERIC}


def relevance(text, thread, terms):
    """2 = names the model, 1 = names the brand or sits in a thread about the model, 0 = neither."""
    model, brand = terms
    words = set(norm(text).split())
    if words & model:
        return 2
    if words & brand or set(norm(thread or "").split()) & model:
        return 1
    return 0


def pick_quotes(cands, sentiment, limit, terms=(set(), set()), exclude=(), min_any=2):
    """Quotes of one sentiment that are clearly about this product, then the cleanest and most specific;
    one per Redditor, no repeats. Comments that never name the product (or its brand, or sit in a thread about it)
    are used only to reach min_any quotes, so general advice does not crowd out comments about the product."""
    chosen, seen_users, seen_text = [], set(), {t.lower() for t in exclude}
    # Some archived quotes are cut off mid-sentence: prefer ones that end cleanly, then the most specific.
    clean = lambda t: t.rstrip().endswith((".", "!", "?", '"', "'", ")", "\u201d"))
    pool = sorted((c for c in cands if c[2] == sentiment),
                  key=lambda c: (-relevance(c[3], c[7], terms), not clean(c[3]), -c[0], -len(c[3])))
    for spec, user, _s, text, sub, date, url, thread in pool:
        if terms[0] and len(chosen) >= min_any and relevance(text, thread, terms) == 0:
            break
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


def stance(sentiments):
    """One Redditor's overall stance from all their opinions (a tie counts as neutral)."""
    top = Counter(sentiments).most_common()
    return "neutral" if len(top) > 1 and top[0][1] == top[1][1] else top[0][0]


def tally(dated):
    """One vote per Redditor: (redditors, positive, neutral, negative) from (date, user, sentiment) rows."""
    by_user = defaultdict(list)
    for _d, u, s in dated:
        by_user[u].append(s)
    c = Counter(stance(v) for v in by_user.values())
    return sum(c.values()), c["positive"], c["neutral"], c["negative"]


def product_extras(g, through, terms):
    """Per-product evidence for the page: where it is discussed, how opinion moved over time, the date range."""
    subs = sorted(((sub, len(u)) for sub, u in g["sub_users"].items() if sub), key=lambda x: (-x[1], x[0].lower()))[:6]
    threads = sorted(g["threads"].values(), key=lambda t: (-len(t["users"]), t["title"]))
    # Threads about this product first (title names the model), then the biggest.
    threads = sorted(threads, key=lambda t: -(1 if set(norm(t["title"]).split()) & terms[0] else 0))[:5]
    years = defaultdict(list)
    for d, u, s in g["dated"]:
        years[d[:4]].append((d, u, s))
    timeline = []
    for y in sorted(years):
        n, pos, neu, neg = tally(years[y])
        if n >= 5:
            timeline.append({"year": y, "redditors": n, "share_positive": round(100 * pos / n), "share_negative": round(100 * neg / n)})
    recent = None
    if through and len(through) == 10:
        cutoff = f"{int(through[:4]) - 1}{through[4:]}"
        n, pos, neu, neg = tally([x for x in g["dated"] if x[0] > cutoff])
        if n >= 5:
            recent = {"since": cutoff, "redditors": n, "share_positive": round(100 * pos / n), "share_negative": round(100 * neg / n)}
    dates = sorted(d for d, _u, _s in g["dated"])
    return {
        "subreddits": [{"name": s_, "redditors": n} for s_, n in subs],
        "threads": [{"title": t["title"][:160], "subreddit": t["subreddit"], "url": t["url"], "redditors": len(t["users"])}
                    for t in threads if t["title"]],
        "timeline": timeline,
        "recent": recent,
        "first_date": dates[0] if dates else None,
        "last_date": dates[-1] if dates else None,
    }


# Comparison pages exist only for pairs Reddit actually compares: products discussed by the same Redditors in the
# same threads. Each product keeps its strongest partners, so the site does not fill up with "every X vs every Y".
MIN_SHARED_REDDITORS = 5
MIN_SHARED_THREADS = 3
MAX_COMPARISONS_PER_PRODUCT = 6
# If most of one product's Redditors are also counted for the other, the archive's opinions cannot tell the two apart
# (typically brand-wide comments attached to every model), so a head-to-head would be meaningless.
MAX_SHARED_SHARE = 0.7
STOP = set("a an and the of for with in to by on".split())


def name_words(p):
    """Words of a product's name without its brand ("Anker Soundcore Liberty 4 NC" -> soundcore, liberty, 4, nc)."""
    return {t for t in norm(p["name"]).split() if t not in set(norm(p.get("brand") or "").split()) and t not in STOP}


def names_other(text, other_only, shared_base):
    """True if a comment names the other product: one of the words only the other product's name has, plus (when
    the two share a model line, like 'liberty') a word of that line, so 'pro' alone is not enough."""
    words = set(norm(text).split())
    if not words & other_only:
        return False
    base = {w for w in shared_base if not w.isdigit() and len(w) >= 3}
    return not base or bool(words & base)


def comparative_quotes(g, other_only, shared_base, about_slug, limit):
    """Quotes from one product's opinions that also name the other product."""
    if not other_only:
        return []
    clean = lambda t: t.rstrip().endswith((".", "!", "?", '"', "'", ")", "\u201d"))
    pool = sorted((q for q in g["quotes"] if q[2] in ("positive", "negative") and names_other(q[3], other_only, shared_base)),
                  key=lambda q: (not clean(q[3]), -q[0], -len(q[3])))
    out, seen_u, seen_t = [], set(), set()
    for spec, user, sent, text, sub, date, url, thread in pool:
        if user in seen_u or text.lower() in seen_t or not url:
            continue
        seen_u.add(user)
        seen_t.add(text.lower())
        q = {"text": text, "sentiment": sent, "about": about_slug, "subreddit": sub, "date": date, "url": url}
        if thread:
            q["thread"] = thread[:140]
        out.append(q)
        if len(out) == limit:
            break
    return out


def build_comparisons(ranked):
    """Pairs of ranked products that Reddit discusses together, with head-to-head evidence."""
    users = [set(p["_g"]["users"]) for p in ranked]
    threads = [set(p["_g"]["threads"]) for p in ranked]
    cand = []
    for i in range(len(ranked)):
        for j in range(i + 1, len(ranked)):
            su, st = users[i] & users[j], threads[i] & threads[j]
            if len(su) >= MIN_SHARED_REDDITORS and len(st) >= MIN_SHARED_THREADS:
                cand.append((len(su), len(st), i, j, su, st))
    cand.sort(key=lambda c: (-c[0], -c[1], c[2], c[3]))
    per = defaultdict(int)
    out, overlapping = [], []
    for n_su, n_st, i, j, su, st in cand:
        if n_su >= MAX_SHARED_SHARE * min(len(users[i]), len(users[j])):
            overlapping.append((ranked[i]["name"], ranked[j]["name"], n_su, min(len(users[i]), len(users[j]))))
            continue
        if per[i] >= MAX_COMPARISONS_PER_PRODUCT or per[j] >= MAX_COMPARISONS_PER_PRODUCT:
            continue
        A, B = ranked[i], ranked[j]
        ga, gb = A["_g"], B["_g"]
        wa, wb = name_words(A), name_words(B)
        quotes = (comparative_quotes(ga, wb - wa, wa & wb, A["slug"], 3)
                  + comparative_quotes(gb, wa - wb, wa & wb, B["slug"], 3))
        seen = set()
        quotes = [q for q in quotes if not (q["text"].lower() in seen or seen.add(q["text"].lower()))]
        # A page needs real comparative evidence: quotes that name both, or a solid shared audience.
        if not quotes and n_su < 15:
            continue
        per[i] += 1
        per[j] += 1
        sa = Counter(stance(ga["users"][u]) for u in su)
        sb = Counter(stance(gb["users"][u]) for u in su)
        prefer_a = sum(1 for u in su if stance(ga["users"][u]) == "positive" and stance(gb["users"][u]) == "negative")
        prefer_b = sum(1 for u in su if stance(gb["users"][u]) == "positive" and stance(ga["users"][u]) == "negative")
        shared = []
        for k in st:
            ta, tb = ga["threads"][k], gb["threads"][k]
            shared.append({"title": ta["title"][:160], "subreddit": ta["subreddit"], "url": ta["url"],
                           "redditors": len(ta["users"] | tb["users"])})
        shared.sort(key=lambda t: (-t["redditors"], t["title"]))
        x, y = sorted([A["slug"], B["slug"]])
        out.append({
            "slug": f"{x}-vs-{y}", "a": x, "b": y,
            "shared_redditors": n_su, "shared_threads": n_st,
            "h2h": {A["slug"]: {"positive": sa["positive"], "neutral": sa["neutral"], "negative": sa["negative"]},
                    B["slug"]: {"positive": sb["positive"], "neutral": sb["neutral"], "negative": sb["negative"]},
                    "prefer": {A["slug"]: prefer_a, B["slug"]: prefer_b}},
            "quotes": quotes,
            "threads": [t for t in shared if t["title"]][:5],
        })
    out.sort(key=lambda c: (-c["shared_redditors"], c["slug"]))
    if overlapping:
        print(f"    {len(overlapping)} pairs share most of their Redditors (no comparison page; the archive may have attached "
              f"the same comments to both; merge them in scripts/curation.json if they are one product):")
        for a_, b_, n, m in sorted(overlapping, key=lambda x: -x[2] / x[3])[:8]:
            print(f"       {a_[:38]} | {b_[:38]}  ({n} of {m})")
    return out


def point_entry(g, kind, title, count):
    """A praised/criticised point, with one supporting Reddit quote linked to its comment when one can be found."""
    entry = {"title": title, "count": count}
    wanted = [q.lower() for q in g["point_quotes"].get((kind, title.lower()), [])]
    if wanted:
        by_text = {}
        for spec, user, s, text, sub, date, url, thread in g["quotes"]:
            by_text.setdefault(text.lower(), (text, sub, date, url))
        for w in wanted:
            hit = by_text.get(w) or next((v for k, v in by_text.items() if w and (w in k or k in w) and min(len(w), len(k)) >= 40), None)
            if hit and hit[3]:
                entry["quote"] = {"text": hit[0], "subreddit": hit[1], "date": hit[2], "url": hit[3]}
                break
    return entry


def tidy_name(s):
    """Remove trademark signs and accidentally repeated words ("Soundcore Soundcore A20i")."""
    s = re.sub("[\u2122\u00ae\u00a9\u2120]", "", s or "")
    s = re.sub(r"\b([A-Za-z]{3,})(\s+\1\b)+", r"\1", s, flags=re.I)
    return re.sub(r"\s+", " ", s).strip()


def load_curation(path):
    """Editable rules (scripts/curation.json): products to drop, and product families to merge."""
    empty = {"exclude": [], "families": [], "rename": [], "distinct": []}
    if not path or not os.path.exists(path):
        return empty
    with open(path, encoding="utf-8") as f:
        d = json.load(f)
    out = {k: [dict(r, _re=re.compile(r["match"])) for r in d.get(k, [])] for k in ("exclude", "families", "rename")}
    # 'distinct': products the duplicate check flags that are really separate models; listed so it stops flagging them.
    out["distinct"] = [dict(r, _res=[re.compile(m) for m in r["match"]]) for r in d.get("distinct", [])]
    return out


def known_distinct(rules, category, names):
    """True if one 'distinct' rule covers every name in a group the duplicate check flagged."""
    normed = [norm(n) for n in names]
    return any(r["category"] == category and all(any(x.search(n) for x in r["_res"]) for n in normed) for r in rules)


def first_rule(rules, category, normed):
    for r in rules:
        if r["category"] == category and r["_re"].search(normed):
            return r
    return None


def new_group(brand, name):
    return {"best": -1, "brand": brand, "name": name, "asin": None, "asin_n": -1, "img": None, "img_n": -1,
            "is_series": True, "users": defaultdict(list), "points": {}, "quotes": [], "subs": set(), "members": [], "threads": {},
            "sub_users": defaultdict(set), "dated": [], "point_quotes": defaultdict(list)}


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
    for sub, users in g["sub_users"].items():
        t["sub_users"][sub] |= users
    t["dated"].extend(g["dated"])
    for k, qs in g["point_quotes"].items():
        t["point_quotes"][k].extend(qs)
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
    ap.add_argument("--no-asin-photos", action="store_true",
                    help="do not ask Amazon for pictures of products that have an Amazon id but no archived photo")
    ap.add_argument("--refresh-asin-photos", action="store_true", help="forget remembered answers and ask Amazon again")
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
                                    "users": defaultdict(list), "points": {}, "quotes": [], "subs": set(), "members": [], "threads": {},
                                    "sub_users": defaultdict(set), "dated": [], "point_quotes": defaultdict(list)})
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
            g["sub_users"][r["subreddit"]].add(user)
        date = (r["comment_date"] or "")[:10]
        if date > through:
            through = date
        if re.match(r"\d{4}-\d{2}-\d{2}$", date):
            g["dated"].append((date, user, s))
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
        for q in (r.get("top_quotes") or "").split(" || "):
            if q.strip():
                groups[key]["point_quotes"][(kind, title.lower())].append(q.strip())

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
            # The member's own address (and its renamed one, if a rename rule covered it) redirects to the family page.
            olds = kept[fkey].setdefault("old_slugs", [])
            olds.append(slugify(tidy_name(display_name(g["brand"], g["name"]))))
            ren = first_rule(cur["rename"], key[0], normed)
            if ren:
                olds.append(slugify(tidy_name(display_name(ren.get("brand") or g["brand"], ren["name"]))))
                olds.extend(ren.get("previous_slugs") or [])
            for old in fam.get("previous_slugs") or []:
                if old not in olds:
                    olds.append(old)
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
    photo_cache_path = os.path.join(a.data, "asin_photos.json")
    photo_cache = {}
    if not a.refresh_asin_photos and os.path.exists(photo_cache_path):
        try:
            photo_cache = json.load(open(photo_cache_path, encoding="utf-8"))
        except (OSError, ValueError):
            photo_cache = {}
    photo_totals = {"products": 0, "archive": 0, "asin": 0}
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
            terms = product_terms(g["brand"], [shown_name] + [m[1] for m in g["members"]])
            extra = product_extras(g, through, terms)
            ranked.append({
                "name": shown_name, "brand": g["brand"], "opinions": n, "variants": variants,
                "positive": pos, "neutral": neu, "negative": neg,
                "share_positive": round(100 * pos / n), "share_negative": round(100 * neg / n),
                "score": round(100 * wilson(pos + 0.5 * neu, n)), "_s": wilson(pos + 0.5 * neu, n),
                "asin": g["asin"], "image": g["img"], "_subs": g["subs"], "_threads": g["threads"], "_old_slugs": g.get("old_slugs") or [],
                "_g": g, "_terms": terms,
                "likes": [point_entry(g, "likes", t, k) for t, k in likes],
                "dislikes": [point_entry(g, "dislikes", t, k) for t, k in dislikes],
                "quotes": (pos_q := pick_quotes(g["quotes"], "positive", 6, terms))
                          + pick_quotes(g["quotes"], "negative", 4, terms, exclude=[q["text"] for q in pos_q]),
                **extra,
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
        by_asin = 0 if a.no_asin_photos else fill_asin_photos(ranked, photo_cache)
        for p in ranked:
            p.pop("_by_asin", None)
        comparisons = build_comparisons(ranked)
        for p in ranked:
            p.pop("_g", None)
            p.pop("_terms", None)
        photo_totals["products"] += len(ranked)
        photo_totals["asin"] += by_asin
        photo_totals["archive"] += sum(1 for p in ranked if p["image"]) - by_asin
        lines = {}
        for p in ranked:
            toks = norm(p["name"]).split()
            btoks = norm(p["brand"]).split()
            if toks[: len(btoks)] == btoks:
                toks = toks[len(btoks):]
            lines.setdefault((norm(p["brand"]), tuple(toks[:2])), []).append(p["name"])
        maybe = [v for v in lines.values() if len(v) > 1 and not known_distinct(cur["distinct"], c["slug"], v)]
        if maybe:
            print(f"  possible duplicates in {c['name']} (add a rule to scripts/curation.json if they are one product):")
            for v in maybe[:12]:
                print("     - " + " | ".join(x[:40] for x in v))
        with open(os.path.join(a.out, c["slug"] + ".json"), "w", encoding="utf-8") as f:
            top_threads = sorted(pooled.values(), key=lambda t: (-len(t["users"]), t["title"]))[:10]
            discussions = {"total": len(pooled),
                           "top": [{"title": t["title"][:160], "subreddit": t["subreddit"], "url": t["url"],
                                    "redditors": len(t["users"])} for t in top_threads]}
            json.dump({"slug": c["slug"], "name": c["name"], "discussions": discussions, "products": ranked,
                       "comparisons": comparisons},
                      f, ensure_ascii=False, separators=(",", ":"))
        meta_cats.append({"slug": c["slug"], "name": c["name"], "products": len(ranked),
                          "opinions": sum(p["opinions"] for p in ranked),
                          "top_pick": ranked[0]["name"] if ranked else None,
                          # photo for the category card: the best-ranked product (of the top 5) that has one
                          "top_image": next((p["image"] for p in ranked[:5] if p.get("image")), None)})
        print(f"  {c['name']:<22} {len(ranked):>3} ranked products, {len(comparisons)} comparisons, "
              f"{sum(1 for p in ranked if p['image'])} with a photo, "
              f"top: {ranked[0]['name'] if ranked else '-'}")

    meta_cats = [m for m in meta_cats if m["products"] > 0]
    with open(os.path.join(a.out, "categories.json"), "w", encoding="utf-8") as f:
        json.dump({"fixture": False, "comments_through": through, "min_opinions": a.min_opinions,
                   "stats": {"products": sum(m["products"] for m in meta_cats),
                             "opinions": sum(m["opinions"] for m in meta_cats), "subreddits": len(all_subs)},
                   "categories": meta_cats}, f, ensure_ascii=False, indent=1)
    print(f"wrote {len(meta_cats)} categories to {a.out}")
    if not a.no_asin_photos:
        os.makedirs(a.data, exist_ok=True)
        with open(photo_cache_path, "w", encoding="utf-8") as f:
            json.dump(photo_cache, f, indent=0)
    pt = photo_totals
    print(f"photos: {pt['archive'] + pt['asin']} of {pt['products']} ranked products "
          f"({pt['archive']} from the archive, {pt['asin']} from Amazon by product id; the rest show an illustration)")

    # Old addresses of renamed and merged products -> new ones (Cloudflare reads _redirects from the site root).
    # Never redirect an address that is a live product page, and write each old address once.
    live = {(m["slug"], p["slug"]) for m in meta_cats
            for p in json.load(open(os.path.join(a.out, m["slug"] + ".json"), encoding="utf-8"))["products"]}
    seen_r, kept_r = set(), []
    for cat_slug, old, new in redirects:
        if (cat_slug, old) not in live and (cat_slug, old) not in seen_r:
            seen_r.add((cat_slug, old))
            kept_r.append((cat_slug, old, new))
    redirects = kept_r
    os.makedirs(os.path.dirname(a.redirects), exist_ok=True)
    with open(a.redirects, "w", encoding="utf-8") as f:
        for cat_slug, old, new in redirects:
            f.write(f"/{cat_slug}/{old}/ /{cat_slug}/{new}/ 301\n")
    print(f"wrote {len(redirects)} redirects for renamed and merged products to {a.redirects}")
    if long_names:
        print(f"\n{len(long_names)} product names are over 50 characters. Add a 'rename' rule for the ones that read badly:")
        for cat_slug, name in long_names[:25]:
            print(f"  [{cat_slug}] {name}")


if __name__ == "__main__":
    main()
