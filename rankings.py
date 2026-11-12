#!/usr/bin/env python3
"""
Recover RedditRecs' own ranking order from the decoded pages in output/json/.
Run after extract.py:

    python3 rankings.py

Where the rankings come from (category and /lists pages were rendered in the
browser, so their archived copies hold no ranking data):
  * filter pages  (/<category>/filters/...)  -> "initialProducts", in display order
  * series pages  (/<category>/series/...)   -> "topCategoryProducts", the category's
                                                overall top 5, in display order
The newest snapshot (from index.json) wins when several pages hold the same list.

Writes:
  output/rankings.csv           one row per (list, rank)
  output/ranking_lists.csv      one row per list: title, type, filters, size
  output/category_meta.csv      per category: Reddit users / threads analysed, specs, subreddits
  output/use_case_evidence.csv  Reddit snippets + permalinks backing each "best for" use case
"""
import csv, json, os

JSON_DIR = os.path.join("output", "json")
OUT = "output"


def load_index():
    """path -> snapshot timestamp, from scrape_fast.py's index.json (optional)."""
    try:
        with open("index.json", encoding="utf-8") as f:
            return {k.rstrip("/"): v[0] for k, v in json.load(f).items()}
    except (OSError, ValueError):
        return {}


def key_with(prefix, data):
    return [k for k in data if k.startswith(prefix)]


def listing_fields(p):
    fl = p.get("first_listing") or {}
    return {"price": fl.get("price"), "currency": fl.get("currency"),
            "seller": fl.get("seller_site_name"), "buy_url": fl.get("url")}


def product_slug(p):
    s = p.get("slug") or ""
    return s.split("/", 1)[1] if "/" in s else s


def main():
    if not os.path.isdir(JSON_DIR):
        raise SystemExit("output/json not found - run extract.py first")
    ts_of = load_index()
    lists = {}        # list_key -> dict(meta..., products=[...], ts=...)
    cat_meta = {}     # category -> (ts, row)
    evidence = {}     # (category, use_case_id) -> rows
    one_liners = {}   # (category, model_id) -> one-liner text
    bad = 0

    names = sorted(f for f in os.listdir(JSON_DIR) if f.endswith(".json"))
    print(f"reading {len(names)} decoded pages...", flush=True)
    for fn in names:
        try:
            with open(os.path.join(JSON_DIR, fn), encoding="utf-8") as f:
                d = json.load(f)
            data = d.get("data") if isinstance(d, dict) else None
            if not isinstance(data, dict):
                continue
            path = (d.get("path") or "").strip("/")
            parts = path.split("/")
            cat = parts[0] if parts else ""
            ts = ts_of.get("/" + path.lower(), "")

            for k in key_with("topOneLiners-", data):
                for o in data[k] or []:
                    if isinstance(o, dict) and o.get("one_liner"):
                        one_liners[(cat, o.get("model_id") or o.get("series_id"))] = o["one_liner"]

            # ---- category-level metadata (present on filter pages) ----------
            for k in key_with("categoryMetadata-", data):
                m = data[k] or {}
                subs = []
                for sk in key_with("subredditsData-", data):
                    subs = [f"r/{s.get('subm_subreddit')} ({s.get('opinion_count')})"
                            for s in (data[sk] or [])[:10] if isinstance(s, dict)]
                row = {"category_slug": cat, "reddit_users": m.get("users_count"),
                       "threads_analysed": m.get("subms_count"),
                       "spec_filters": " | ".join(f"{s.get('label')}" + (f" ({s.get('units')})" if s.get("units") else "")
                                                  for s in m.get("specs_def") or [] if isinstance(s, dict)),
                       "use_cases": " | ".join(u.get("name", "") for u in m.get("use_cases") or [] if isinstance(u, dict)),
                       "top_subreddits": ", ".join(subs), "snapshot": ts}
                if cat not in cat_meta or ts > cat_meta[cat][0]:
                    cat_meta[cat] = (ts, row)

            # ---- evidence behind each use case ------------------------------
            for k in key_with("useCasesWithInfo-", data):
                for uc in data[k] or []:
                    if not isinstance(uc, dict):
                        continue
                    ev = (uc.get("info") or {}).get("evidence") or []
                    key = (cat, uc.get("id"))
                    if ev and (key not in evidence or ts > evidence[key][0]):
                        evidence[key] = (ts, [{"category_slug": cat, "use_case_id": uc.get("id"),
                                               "use_case_name": uc.get("name"), "snippet": e.get("snippet"),
                                               "permalink": e.get("permalink")}
                                              for e in ev if isinstance(e, dict)])

            # ---- filter page rankings ----------------------------------------
            for k in key_with("filteredProducts-", data):
                fp = data[k] or {}
                prods = fp.get("initialProducts") or []
                page = fp.get("filteredPageData") or {}
                params = page.get("rpc_get_filtered_products_params") or {}
                ucs = params.get("use_cases_to_filter") or []
                specs = (params.get("specs_to_filter_options") or []) + (params.get("specs_to_filter_range") or [])
                subs = params.get("subreddits_to_filter") or []
                dims = sum(1 for x in (ucs, specs, subs) if x)
                if dims == 0:
                    ltype = "all"
                elif dims > 1 or len(ucs) > 1 or len(specs) > 1 or len(subs) > 1:
                    ltype = "combination"
                else:
                    ltype = "use_case" if ucs else ("spec" if specs else "subreddit")
                ident = json.dumps({"c": cat, "u": sorted(map(str, ucs)), "s": specs, "r": sorted(map(str, subs)),
                                    "pmin": params.get("price_min"), "pmax": params.get("price_max")},
                                   sort_keys=True, default=str)
                uc_info = (page.get("useCaseInfo") or [{}])[0] if page.get("useCaseInfo") else {}
                entry = {"category_slug": cat, "list_type": ltype, "title": page.get("title") or parts[-1],
                         "use_case": uc_info.get("name") if isinstance(uc_info, dict) else None,
                         "page_path": "/" + path, "filters": ident, "ts": ts, "products": prods}
                if ident not in lists or ts > lists[ident]["ts"]:
                    lists[ident] = entry

            # ---- overall category top 5 (series pages) -----------------------
            for k in key_with("topCategoryProducts-", data):
                prods = (data[k] or {}).get("topProducts") or []
                ident = f"overall:{cat}"
                if prods and (ident not in lists or ts > lists[ident]["ts"]):
                    lists[ident] = {"category_slug": cat, "list_type": "overall_top5",
                                    "title": f"Top {cat.replace('-', ' ')} overall", "use_case": None,
                                    "page_path": "/" + path, "filters": "", "ts": ts, "products": prods}
        except Exception as e:
            bad += 1
            if bad <= 5:
                print(f"  skipped {fn[:70]}: {type(e).__name__}: {e}"[:160])

    # ---- write outputs -----------------------------------------------------
    rank_cols = ["category_slug", "list_type", "list_title", "use_case", "rank", "brand", "product", "product_slug",
                 "positive", "neutral", "negative", "price", "currency", "seller", "buy_url", "one_liner",
                 "snapshot", "source_page"]
    list_cols = ["category_slug", "list_type", "list_title", "use_case", "products", "number_1", "snapshot",
                 "source_page", "filters"]
    n_rows = 0
    with open(os.path.join(OUT, "rankings.csv"), "w", newline="", encoding="utf-8") as fr, \
         open(os.path.join(OUT, "ranking_lists.csv"), "w", newline="", encoding="utf-8") as fl:
        wr = csv.DictWriter(fr, fieldnames=rank_cols); wr.writeheader()
        wl = csv.DictWriter(fl, fieldnames=list_cols); wl.writeheader()
        for ident, L in sorted(lists.items(), key=lambda kv: (kv[1]["category_slug"], kv[1]["list_type"], kv[1]["title"])):
            prods = [p for p in L["products"] if isinstance(p, dict)]
            first = prods[0] if prods else {}
            wl.writerow({"category_slug": L["category_slug"], "list_type": L["list_type"], "list_title": L["title"],
                         "use_case": L["use_case"], "products": len(prods),
                         "number_1": f"{first.get('brand_name', '')} {first.get('name', '')}".strip(),
                         "snapshot": L["ts"], "source_page": L["page_path"], "filters": L["filters"]})
            for rank, p in enumerate(prods, 1):
                wr.writerow({"category_slug": L["category_slug"], "list_type": L["list_type"], "list_title": L["title"],
                             "use_case": L["use_case"], "rank": rank, "brand": p.get("brand_name"),
                             "product": p.get("name"), "product_slug": product_slug(p),
                             "positive": p.get("positive"), "neutral": p.get("neutral"), "negative": p.get("negative"),
                             **listing_fields(p),
                             "one_liner": p.get("top_one_liner") or one_liners.get((L["category_slug"],
                                                                                     p.get("model_id") or p.get("series_id"))),
                             "snapshot": L["ts"], "source_page": L["page_path"]})
                n_rows += 1

    meta_rows = [row for _, row in sorted(cat_meta.values(), key=lambda t: t[1]["category_slug"])]
    if meta_rows:
        with open(os.path.join(OUT, "category_meta.csv"), "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=list(meta_rows[0])); w.writeheader(); w.writerows(meta_rows)
    ev_rows = [r for _, rows in evidence.values() for r in rows]
    if ev_rows:
        with open(os.path.join(OUT, "use_case_evidence.csv"), "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=list(ev_rows[0])); w.writeheader(); w.writerows(ev_rows)

    by_type = {}
    for L in lists.values():
        by_type[L["list_type"]] = by_type.get(L["list_type"], 0) + 1
    print(f"ranking lists: {len(lists)} ({', '.join(f'{n} {t}' for t, n in sorted(by_type.items()))})")
    print(f"  output/rankings.csv: {n_rows} rows")
    print(f"  output/category_meta.csv: {len(meta_rows)} categories")
    print(f"  output/use_case_evidence.csv: {len(ev_rows)} Reddit snippets")
    if bad:
        print(f"  {bad} pages could not be read")


if __name__ == "__main__":
    main()
