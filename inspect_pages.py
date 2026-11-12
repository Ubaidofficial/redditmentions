#!/usr/bin/env python3
"""
Write output/page_shapes.json: the data structure (keys, types, one example item,
shortened text) of a few category, filter, series and list pages. It contains no
full page content, only the layout, so it is small enough to share.

    python3 inspect_pages.py
"""
import json, os

JSON_DIR = os.path.join("output", "json")
PICK = {"category": lambda n: n in ("action-camera", "air-purifier", "espresso-machine"),
        "filter": lambda n: "__filters__best-for" in n,
        "series": lambda n: "__series__" in n,
        "lists": lambda n: n.startswith("lists"),
        "brand": lambda n: "__brand__" in n}


def shape(o, depth=0):
    if depth > 7:
        return "..."
    if isinstance(o, dict):
        return {k: shape(v, depth + 1) for k, v in list(o.items())[:60]}
    if isinstance(o, list):
        return [f"<list of {len(o)}>", shape(o[0], depth + 1)] if o else []
    if isinstance(o, str):
        return o[:80]
    return o


def main():
    if not os.path.isdir(JSON_DIR):
        raise SystemExit("output/json not found - run extract.py first")
    names = sorted(f[:-5] for f in os.listdir(JSON_DIR) if f.endswith(".json"))
    out = {}
    for kind, test in PICK.items():
        picked = [n for n in names if test(n)][:2]
        for n in picked:
            with open(os.path.join(JSON_DIR, n + ".json"), encoding="utf-8") as f:
                d = json.load(f)
            data = d.get("data", {}) if isinstance(d, dict) else {}
            data = {k: v for k, v in data.items() if k != "global-categories"} if isinstance(data, dict) else data
            out[f"{kind}: {n}"] = {"path": d.get("path") if isinstance(d, dict) else None, "data": shape(data)}
    out["_counts"] = {k: sum(1 for n in names if t(n)) for k, t in PICK.items() if k != "category"}
    with open(os.path.join("output", "page_shapes.json"), "w", encoding="utf-8") as f:
        json.dump(out, f, indent=1, ensure_ascii=False)
    print(f"wrote output/page_shapes.json ({os.path.getsize(os.path.join('output', 'page_shapes.json')) // 1024} KB) "
          f"from {len(out) - 1} sample pages; page counts: {out['_counts']}")


if __name__ == "__main__":
    main()
