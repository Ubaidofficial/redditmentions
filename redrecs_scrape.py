#!/usr/bin/env python3
"""Polite, resumable crawler for redrecs.com (competitor research).

- Reads the URLs from the site's own sitemap and honours robots.txt (skips /api/ and /login).
- One request at a time with a delay (default 1.5 s), identifies itself, backs off on 429/5xx.
- redrecs.com is a Next.js app: each page embeds its data in the `self.__next_f` payload.
  We decode that payload and save only the structured data (analysis + products + sources)
  to output/redrecs/<slug>.json. Pages without a ranking (home, categories, about) are saved
  as decoded text so they can be inspected.

Output goes to output/ which is gitignored (third-party content stays on your machine).

    python3 redrecs_scrape.py            # crawl everything not yet downloaded
    python3 redrecs_scrape.py --limit 5  # try a few pages first
"""
import argparse, json, re, sys, time, urllib.request, urllib.error
from pathlib import Path

BASE = "https://www.redrecs.com"
UA = "Mozilla/5.0 (compatible; research-crawler/1.0)"
OUT = Path("output/redrecs")
SKIP_PREFIXES = ("/api/", "/login")


def get(url, retries=5):
    delay = 5
    for _ in range(retries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=60) as r:
                return r.read().decode("utf-8", "replace")
        except urllib.error.HTTPError as e:
            if e.code in (429, 500, 502, 503, 504):
                time.sleep(delay); delay *= 2; continue
            if e.code == 404:
                return None
            raise
        except (urllib.error.URLError, TimeoutError):
            time.sleep(delay); delay *= 2
    return None


def flight_text(html):
    chunks = re.findall(r'self\.__next_f\.push\(\[1,"(.*?)"\]\)</script>', html, re.S)
    out = []
    for c in chunks:
        try:
            out.append(json.loads('"' + c + '"'))
        except json.JSONDecodeError:
            pass
    return "".join(out)


def extract(html):
    text = flight_text(html)
    i = text.find('{"analysis":{')
    if i != -1:
        try:
            obj, _ = json.JSONDecoder().raw_decode(text[i:])
            return {"kind": "analysis", "data": obj}
        except json.JSONDecodeError:
            pass
    title = re.search(r"<title>(.*?)</title>", html, re.S)
    return {"kind": "page", "title": title.group(1) if title else None, "flight": text}


def sitemap_urls():
    xml = get(BASE + "/sitemap.xml")
    urls = re.findall(r"<loc>([^<]+)</loc>", xml or "")
    paths = []
    for u in urls:
        p = re.sub(r"^https?://[^/]+", "", u) or "/"
        if not p.startswith(SKIP_PREFIXES):
            paths.append(p)
    return paths


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--gap", type=float, default=1.5)
    ap.add_argument("--limit", type=int, default=0)
    a = ap.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    paths = sitemap_urls()
    print(f"{len(paths)} URLs in sitemap", flush=True)
    done = 0
    for n, p in enumerate(paths, 1):
        slug = p.strip("/") or "home"
        f = OUT / (slug.replace("/", "__") + ".json")
        if f.exists():
            continue
        html = get(BASE + p)
        if html is None:
            print(f"[{n}/{len(paths)}] FAILED {p}", flush=True)
            continue
        rec = extract(html)
        rec["path"] = p
        f.write_text(json.dumps(rec, ensure_ascii=False))
        n_prod = len(rec["data"].get("products", [])) if rec["kind"] == "analysis" else 0
        print(f"[{n}/{len(paths)}] {p} {rec['kind']} products={n_prod}", flush=True)
        done += 1
        if a.limit and done >= a.limit:
            break
        time.sleep(a.gap)


if __name__ == "__main__":
    sys.exit(main())
