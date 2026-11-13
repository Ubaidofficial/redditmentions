#!/usr/bin/env python3
"""Merge the redditrecs archive (output/models.csv, opinions) with the redrecs crawl
(output/redrecs/*.json) into one product table, output/merged/products.csv.

    python3 scripts/merge_sources.py --rt-models PATH/models.csv [--rt-opinions PATH/opinions_slim.csv]

Design choices (the two sources measure different things, so nothing is averaged or summed):
  * products are matched on Amazon ASIN first, then on brand + model name inside a category pair
    that the ASIN matches already proved to be the same topic (method = "asin" / "name");
  * both sources' counts are kept in separate columns (rt_* = redditrecs, rr_* = redrecs). Sentiment
    methods differ (median gap ~10 points on matched products) and redrecs comments carry no
    permalink, so they cannot be de-duplicated against redditrecs: adding them would double count;
  * a confidence score is computed per source with the Wilson lower bound
    (positive = 1, neutral = 0.5, negative = 0);
  * with --rt-opinions, redditrecs sentiment is recomputed with ONE VOTE PER REDDITOR per product (the
    redditrecs archive counts repeat commenters repeatedly), and recency / subreddit spread are added;
  * `topic` is a unified category: the redditrecs category, or for redrecs-only lists the list slug (lists proven
    to be the same topic by ASIN matches, >= 2 products, take the redditrecs category);
  * `entity_type` marks brand-level rows (brand lists, or name == brand) so they are not mixed with models.
Writes: products.csv, match_report.json (incl. rank agreement between the two sources on matched products).
"""
import argparse, collections, csv, datetime, glob, json, math, os, re, sys, unicodedata

csv.field_size_limit(min(sys.maxsize, 2**31 - 1))


def norm(s):
    s = unicodedata.normalize("NFKD", (s or "").replace("+", " plus ").replace("&", " and "))
    s = "".join(c for c in s if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9]+", " ", s.lower()).strip()


def strip_brand(name, brand):
    n, b = norm(name), norm(brand)
    return n[len(b) + 1:] if b and n.startswith(b + " ") else n


def asin_of(url):
    m = re.search(r"/dp/([A-Z0-9]{10})", url or "")
    return m.group(1) if m else None


def wilson(pos, neu, neg, z=1.96):
    n = pos + neu + neg
    if n == 0:
        return 0.0
    p = (pos + 0.5 * neu) / n
    d = 1 + z * z / n
    return round(100 * ((p + z * z / (2 * n) - z * math.sqrt((p * (1 - p) + z * z / (4 * n)) / n)) / d), 1)


def to_int(x):
    try:
        return int(float(x))
    except (TypeError, ValueError):
        return 0


def load_rt(path):
    out = []
    for m in csv.DictReader(open(path, encoding="utf-8")):
        m["asin"] = asin_of(m["amazon_url"])
        m["pos"], m["neu"], m["neg"] = to_int(m["positive"]), to_int(m["neutral"]), to_int(m["negative"])
        out.append(m)
    return out


def load_rt_opinions(path, today=None):
    """Per (category, model): one vote per Redditor (their most frequent sentiment), subreddits, recency."""
    today = today or datetime.date.today()
    cut = (today - datetime.timedelta(days=365)).isoformat()
    per = collections.defaultdict(lambda: {"u": collections.defaultdict(collections.Counter), "subs": set(), "n": 0, "fresh": 0, "last": ""})
    for r in csv.DictReader(open(path, encoding="utf-8")):
        d = per[(r["category_slug"], r["model_slug"])]
        d["u"][r["reddit_username"]][r["sentiment"]] += 1
        d["subs"].add(r["subreddit"]); d["n"] += 1
        day = (r.get("comment_date") or "")[:10]
        d["fresh"] += day >= cut
        d["last"] = max(d["last"], day)
    out = {}
    for k, d in per.items():
        votes = collections.Counter(c.most_common(1)[0][0] for c in d["u"].values())
        out[k] = {"voters": len(d["u"]), "pos": votes["positive"], "neu": votes["neutral"], "neg": votes["negative"],
                  "subs": len(d["subs"]), "fresh": round(d["fresh"] / d["n"], 2), "last": d["last"]}
    return out


def load_rr(folder):
    best = {}
    lists = collections.defaultdict(set)
    for f in glob.glob(os.path.join(folder, "*.json")):
        r = json.load(open(f, encoding="utf-8"))
        if r.get("kind") != "analysis":
            continue
        a = r["data"]["analysis"]
        for p in r["data"]["products"]:
            key = p.get("asin") or norm(p["name"])
            lists[key].add(a["slug"])
            p["_list"], p["_cat"], p["_key"] = a["slug"], a.get("category"), key
            if key not in best or (p.get("redditMentions") or 0) > (best[key].get("redditMentions") or 0):
                best[key] = p
    for k, p in best.items():
        p["_lists"] = sorted(lists[k])
    return list(best.values())


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--rt-models", required=True)
    ap.add_argument("--rt-opinions", help="opinions.csv or opinions_slim.csv from extract.py")
    ap.add_argument("--rr-dir", default="output/redrecs")
    ap.add_argument("--out", default="output/merged")
    a = ap.parse_args()
    rt, rr = load_rt(a.rt_models), load_rr(a.rr_dir)
    ops = load_rt_opinions(a.rt_opinions) if a.rt_opinions else {}
    os.makedirs(a.out, exist_ok=True)

    rt_by_asin = collections.defaultdict(list)
    for m in rt:
        if m["asin"]:
            rt_by_asin[m["asin"]].append(m)

    # 1) ASIN matches; also learn which redditrecs category each redrecs list belongs to
    pairs, used_rt, vote = {}, set(), collections.defaultdict(collections.Counter)
    for p in rr:
        cands = rt_by_asin.get(p.get("asin")) or []
        if cands:
            m = max(cands, key=lambda c: c["pos"] + c["neu"] + c["neg"])
            pairs[p["_key"]] = (m, "asin")
            used_rt.add(m["model_id"])
            for l in p["_lists"]:
                vote[l][m["category_slug"]] += 1
    list_cat = {l: c.most_common(1)[0][0] for l, c in vote.items() if sum(c.values()) >= 2}

    # 2) name matches inside those category pairs (brand must agree, model text must be equal)
    idx = collections.defaultdict(dict)
    for m in rt:
        if m["model_id"] not in used_rt:
            idx[m["category_slug"]][(norm(m["brand_name"]), strip_brand(m["model_name"], m["brand_name"]))] = m
    for p in rr:
        if p["_key"] in pairs:
            continue
        for l in p["_lists"]:
            cat = list_cat.get(l)
            if not cat:
                continue
            key = (norm(p.get("brand")), strip_brand(p["name"], p.get("brand")))
            m = idx[cat].get(key)
            if m and m["model_id"] not in used_rt:
                pairs[p["_key"]] = (m, "name")
                used_rt.add(m["model_id"])
                break

    cols = ["name", "brand", "category", "topic", "entity_type", "asin", "sources", "match_method",
            "rt_opinions", "rt_positive", "rt_neutral", "rt_negative", "rt_score", "rt_page",
            "rt_voters", "rt_voter_positive", "rt_voter_neutral", "rt_voter_negative", "rt_voter_score",
            "rt_subreddits", "rt_fresh_share", "rt_last_comment",
            "rr_mentions", "rr_positive", "rr_neutral", "rr_negative", "rr_score", "rr_signal",
            "rr_best_rank", "rr_lists", "price_usd"]
    rows, stats = [], collections.Counter()

    def rr_fields(p):
        pos, neu, neg = (p.get("positiveMentions") or 0), (p.get("neutralMentions") or 0), (p.get("negativeMentions") or 0)
        return {"rr_mentions": p.get("redditMentions") or 0, "rr_positive": pos, "rr_neutral": neu, "rr_negative": neg,
                "rr_score": wilson(pos, neu, neg), "rr_signal": p.get("signalScore"),
                "rr_best_rank": p.get("rank"), "rr_lists": ";".join(p["_lists"])}

    def rt_fields(m):
        f = {"rt_opinions": to_int(m["user_opinion_count"]), "rt_positive": m["pos"], "rt_neutral": m["neu"],
             "rt_negative": m["neg"], "rt_score": wilson(m["pos"], m["neu"], m["neg"]), "rt_page": m["page_path"]}
        o = ops.get((m["category_slug"], m["model_slug"]))
        if o:
            f.update(rt_voters=o["voters"], rt_voter_positive=o["pos"], rt_voter_neutral=o["neu"], rt_voter_negative=o["neg"],
                     rt_voter_score=wilson(o["pos"], o["neu"], o["neg"]), rt_subreddits=o["subs"],
                     rt_fresh_share=o["fresh"], rt_last_comment=o["last"])
        return f

    def etype(p):
        brandish = "brands" in p["_list"] or norm(p["name"]) == norm(p.get("brand"))
        return "brand" if brandish else "product"

    for p in rr:
        row = dict.fromkeys(cols, "")
        price = re.sub(r"[^0-9.]", "", p.get("price") or "")
        row.update(name=p["name"], brand=p.get("brand") or "", category=p["_cat"] or "", asin=p.get("asin") or "",
                   price_usd=price, entity_type=etype(p), **rr_fields(p))
        row["topic"] = next((list_cat[l] for l in p["_lists"] if l in list_cat), p["_list"])
        if p["_key"] in pairs:
            m, how = pairs[p["_key"]]
            row.update(rt_fields(m)); row["sources"] = "both"; row["match_method"] = how
            row["category"] = m["category_slug"]; row["topic"] = m["category_slug"]; row["asin"] = row["asin"] or m["asin"] or ""
        else:
            row["sources"] = "redrecs"
        stats[row["sources"]] += 1
        rows.append(row)
    for m in rt:
        if m["model_id"] in used_rt:
            continue
        row = dict.fromkeys(cols, "")
        row.update(name=m["model_name"], brand=m["brand_name"], category=m["category_slug"], topic=m["category_slug"],
                   entity_type="product", asin=m["asin"] or "",
                   sources="redditrecs", price_usd=m["lowest_price"] if m["currency"] == "USD" else "", **rt_fields(m))
        stats["redditrecs"] += 1
        rows.append(row)

    with open(os.path.join(a.out, "products.csv"), "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=cols); w.writeheader(); w.writerows(rows)
    agree = {}
    both = collections.defaultdict(list)
    for r in rows:
        if r["sources"] == "both":
            both[r["topic"]].append(r)
    def ranks(v):
        order = sorted(range(len(v)), key=lambda i: v[i]); r = [0] * len(v)
        for pos, i in enumerate(order): r[i] = pos
        return r
    for t, rs in both.items():
        if len(rs) >= 5:
            x, y = ranks([r["rt_score"] for r in rs]), ranks([r["rr_score"] for r in rs]); n = len(rs)
            agree[t] = {"n": n, "spearman": round(1 - 6 * sum((a - b) ** 2 for a, b in zip(x, y)) / (n * (n * n - 1)), 2)}
    report = {"rank_agreement_matched_products": agree, "redditrecs_models": len(rt), "redrecs_unique_products": len(rr), "merged_rows": len(rows),
              "by_sources": dict(stats), "matched_by": dict(collections.Counter(h for _, h in pairs.values())),
              "list_to_category": list_cat}
    json.dump(report, open(os.path.join(a.out, "match_report.json"), "w"), indent=1)
    print(json.dumps({k: v for k, v in report.items() if k != "list_to_category"}, indent=1))


if __name__ == "__main__":
    main()
