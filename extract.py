#!/usr/bin/env python3
"""
Turn downloaded redditrecs.com pages (pages/*.html) into spreadsheets.

    python3 extract.py            # reads ./pages, writes ./output/*.csv

Model pages (/<category>/model/<product>) are fully parsed.
Every other page type (category, filter, brand) is saved as decoded JSON
in output/json/ so its format can be checked and added later.
"""
import csv, json, os, re, sys

# --- decoder for Nuxt's embedded page data (devalue format) ---

def unflatten(arr):
    cache = {}
    def h(i):
        if not isinstance(i, int) or isinstance(i, bool) or i >= len(arr):
            return i
        if i < 0:
            return {-1: None, -2: None, -3: float("nan"), -4: float("inf"), -5: float("-inf"), -6: -0.0}.get(i)
        if i in cache:
            return cache[i]
        v = arr[i]
        if isinstance(v, list):
            if v and isinstance(v[0], str) and v[0] in ("Reactive", "ShallowReactive", "Ref", "ShallowRef", "EmptyRef", "EmptyShallowRef"):
                out = h(v[1]) if len(v) > 1 else None
            elif v and isinstance(v[0], str) and v[0] == "Set":
                out = [h(x) for x in v[1:]]
            elif v and isinstance(v[0], str) and v[0] == "Map":
                out = {str(h(v[k])): h(v[k + 1]) for k in range(1, len(v), 2)}
            elif v and isinstance(v[0], str) and v[0] == "Date":
                out = v[1]
            elif v and isinstance(v[0], str) and v[0] in ("null", "BigInt", "RegExp"):
                out = v[1] if len(v) > 1 else None
            else:
                out = []
                cache[i] = out
                out.extend(h(x) for x in v)
                return out
        elif isinstance(v, dict):
            out = {}
            cache[i] = out
            for k, x in v.items():
                out[k] = h(x)
            return out
        else:
            out = v
        cache[i] = out
        return out
    return h(0)

def from_html(html):
    m = re.search(r'<script[^>]*id="__NUXT_DATA__"[^>]*>(.*?)</script>', html, re.S)
    return unflatten(json.loads(m.group(1))) if m else None
# ---------------------------------------------------------------

PAGES, OUT = "pages", "output"
os.makedirs(os.path.join(OUT, "json"), exist_ok=True)

def writer(name, cols):
    f = open(os.path.join(OUT, name), "w", newline="", encoding="utf-8")
    w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore")
    w.writeheader()
    return f, w

files = {}
def open_all():
    spec = {
        "categories.csv": ["category_id", "category_slug", "category_name", "product_term", "img_url"],
        "models.csv": ["category_slug", "model_id", "model_slug", "model_name", "brand_slug", "brand_name", "series",
                       "user_opinion_count", "positive", "neutral", "negative", "sort_index",
                       "lowest_price", "currency", "amazon_url", "img_url", "page_path"],
        "summary_points.csv": ["category_slug", "model_slug", "type", "title", "likes_count", "dislikes_count", "top_quotes"],
        "opinions.csv": ["category_slug", "model_slug", "opinion_id", "reddit_username", "sentiment", "specificity",
                         "use_case_relevance_score", "quotes", "subreddit", "thread_title", "comment_date",
                         "comment_permalink", "comment_text"],
        "listings.csv": ["category_slug", "model_slug", "seller", "price", "currency", "url", "is_prime_day_deal"],
        "use_cases.csv": ["category_slug", "use_case_id", "use_case_name", "ranking_slug", "ranking_title",
                          "top_product_name", "top_product_slug", "who_this_is_for", "key_needs", "prioritize", "deprioritize"],
    }
    for name, cols in spec.items():
        files[name] = writer(name, cols)

def row(name, d):
    files[name][1].writerow(d)

def main():
    open_all()
    seen_cats, seen_uc = set(), set()
    n_model = n_other = n_bad = 0
    names = sorted(f for f in os.listdir(PAGES) if f.endswith(".html"))
    print(f"reading {len(names)} pages...", flush=True)
    for i, fn in enumerate(names, 1):
        if i % 500 == 0:
            print(f"  {i}/{len(names)} pages processed", flush=True)
        try:
            kind = process(fn, seen_cats, seen_uc)
        except Exception as e:
            kind = "bad"
            if n_bad < 10:
                print(f"  skipped {fn[:70]}: {type(e).__name__}: {e}"[:160])
        if kind == "model": n_model += 1
        elif kind == "other": n_other += 1
        else: n_bad += 1
    for f, _ in files.values():
        f.close()
    print(f"model pages: {n_model}   other pages saved as JSON: {n_other}   unreadable/skipped: {n_bad}")
    for name in files:
        with open(os.path.join(OUT, name), encoding="utf-8") as f:
            print(f"  output/{name}: {sum(1 for _ in csv.reader(f)) - 1} rows")

def process(fn, seen_cats, seen_uc):
    """Parse one saved page. Returns "model", "other" or "bad"."""
    data = from_html(open(os.path.join(PAGES, fn), encoding="utf-8", errors="replace").read())
    if not isinstance(data, dict):
        return "bad"
    payload = data.get("data") if isinstance(data.get("data"), dict) else {}
    path = data.get("path", "")
    for c in payload.get("global-categories") or []:
        if c["slug"] not in seen_cats:
            seen_cats.add(c["slug"])
            row("categories.csv", {"category_id": c.get("id"), "category_slug": c["slug"], "category_name": c.get("display_name"),
                                   "product_term": c.get("product_term"), "img_url": c.get("img_url")})
    model_keys = [k for k in payload if k.startswith("model-pageData-")]
    if not model_keys:
        with open(os.path.join(OUT, "json", fn[:-5] + ".json"), "w", encoding="utf-8") as jf:
            json.dump(data, jf, indent=1, ensure_ascii=False, default=str)
        return "other"
    pd = payload[model_keys[0]]; m = pd["modelData"]
    cat = path.strip("/").split("/")[0]
    s = pd.get("sentimentScores") or {}
    listings = m.get("listings") or []
    cheapest = min(listings, key=lambda l: l.get("price") or 1e12) if listings else {}
    amazon = next((l["url"] for l in listings if (l.get("seller_site_name") or "").lower() == "amazon"), "")
    row("models.csv", {"category_slug": cat, "model_id": m.get("id"), "model_slug": m.get("slug"), "model_name": m.get("name"),
                       "brand_slug": m.get("brand_slug"), "brand_name": m.get("brand_name"), "series": m.get("series"),
                       "user_opinion_count": m.get("user_opinion_count"), "positive": s.get("positive"),
                       "neutral": s.get("neutral"), "negative": s.get("negative"), "sort_index": m.get("sort_index"),
                       "lowest_price": cheapest.get("price"), "currency": cheapest.get("currency"), "amazon_url": amazon,
                       "img_url": cheapest.get("img_url"), "page_path": path})
    for l in listings:
        row("listings.csv", {"category_slug": cat, "model_slug": m.get("slug"), "seller": l.get("seller_site_name"),
                             "price": l.get("price"), "currency": l.get("currency"), "url": l.get("url"),
                             "is_prime_day_deal": l.get("is_prime_day_deal")})
    for sp in m.get("summary_points") or []:
        quotes = [q[0] if isinstance(q, list) and q else q for q in sp.get("top_quotes") or []]
        row("summary_points.csv", {"category_slug": cat, "model_slug": m.get("slug"), "type": sp.get("category"),
                                   "title": sp.get("title"), "likes_count": sp.get("likes_count"),
                                   "dislikes_count": sp.get("dislikes_count"), "top_quotes": " || ".join(map(str, quotes))})
    for uc in m.get("use_cases") or []:
        key = (cat, uc.get("id"))
        if key in seen_uc:
            continue
        seen_uc.add(key)
        info = uc.get("info") or {}
        row("use_cases.csv", {"category_slug": cat, "use_case_id": uc.get("id"), "use_case_name": uc.get("name"),
                              "ranking_slug": uc.get("ranking_slug"), "ranking_title": uc.get("ranking_title"),
                              "top_product_name": uc.get("top_product_name"), "top_product_slug": uc.get("top_product_slug"),
                              "who_this_is_for": info.get("who_this_is_for"),
                              "key_needs": " | ".join(info.get("key_needs") or []),
                              "prioritize": " | ".join(f"{p.get('item')}: {p.get('why')}" for p in info.get("prioritize") or []),
                              "deprioritize": " | ".join(f"{p.get('item')}: {p.get('why')}" for p in info.get("deprioritize") or [])})
    for uo in pd.get("initialUserOpinions") or []:
        for op in uo.get("opinions") or []:
            for src in op.get("sources") or [{}]:
                row("opinions.csv", {"category_slug": cat, "model_slug": m.get("slug"), "opinion_id": op.get("opinion_id"),
                                     "reddit_username": uo.get("reddit_username"), "sentiment": uo.get("sentiment"),
                                     "specificity": op.get("specificity"),
                                     "use_case_relevance_score": op.get("use_case_relevance_score"),
                                     "quotes": " || ".join(q.get("text", "") for q in op.get("verbatim_quotes") or []),
                                     "subreddit": src.get("subreddit"), "thread_title": src.get("subm_title"),
                                     "comment_date": src.get("date"), "comment_permalink": src.get("permalink"),
                                     "comment_text": src.get("text")})
    return "model"

if __name__ == "__main__":
    main()
