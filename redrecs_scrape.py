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
import argparse, http.client, json, re, sys, time, urllib.request, urllib.error
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
        except (OSError, http.client.HTTPException):
            # URLError, socket.timeout (a different class from TimeoutError before Python 3.10), connection resets,
            # SSL errors and IncompleteRead all land here: wait and retry.
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


def resolve_text_ref(text, ref):
    """Pages reference long strings as "$<id>"; the string itself is a flight row `<id>:T<hexlen>,<text>`."""
    if not isinstance(ref, str) or not ref.startswith("$"):
        return None
    m = re.search(r"(?m)^" + re.escape(ref[1:]) + r":T([0-9a-f]+),", text)
    if not m:
        return None
    n = int(m.group(1), 16)  # length in UTF-8 bytes
    return text[m.end():].encode("utf-8")[:n].decode("utf-8", "ignore")


def extract(html):
    text = flight_text(html)
    i = text.find('{"analysis":{')
    if i != -1:
        try:
            obj, _ = json.JSONDecoder().raw_decode(text[i:])
            raw = resolve_text_ref(text, obj["analysis"].get("sources"))
            urls = [u.strip() for u in (raw or "").splitlines() if u.startswith("http")]
            return {"kind": "analysis", "data": obj, "source_urls": urls}
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
    ap.add_argument("--refresh", action="store_true", help="re-fetch ranking pages saved before source_urls was captured")
    a = ap.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    paths = sitemap_urls()
    print(f"{len(paths)} URLs in sitemap", flush=True)
    done = 0
    for n, p in enumerate(paths, 1):
        slug = p.strip("/") or "home"
        f = OUT / (slug.replace("/", "__") + ".json")
        if f.exists():
            if not a.refresh:
                continue
            old = json.loads(f.read_text())
            if old.get("kind") != "analysis" or "source_urls" in old:
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
