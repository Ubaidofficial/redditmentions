#!/usr/bin/env python3
"""Polite, fast, resumable crawler for redrecs.com (competitor research).

- Reads the URLs from the site's own sitemap and honours robots.txt (skips /api/ and /login).
- A few workers share ONE global rate limit (default 2 requests/second in total), ask for gzip
  (pages shrink ~5x), identify themselves, and back off on 429/5xx, timeouts and dropped connections.
- redrecs.com is a Next.js app: each page embeds its data in the `self.__next_f` payload.
  We decode that payload and save only the structured data (analysis + products + source thread
  URLs) to output/redrecs/<slug>.json. Pages without a ranking (home, categories, about) are saved
  as decoded text so they can be inspected.
- Resumable: finished files are skipped, half-written or corrupt files are re-fetched, files are
  written atomically, and a page that keeps failing is reported at the end instead of stopping the run.

Output goes to output/ which is gitignored (third-party content stays on your machine).

    python3 redrecs_scrape.py                # crawl everything not yet downloaded (~4 minutes)
    python3 redrecs_scrape.py --limit 5      # try a few pages first
    python3 redrecs_scrape.py --workers 2 --rate 1   # gentler
Works on Python 3.7+ (standard library only).
"""
import argparse, concurrent.futures as cf, gzip, http.client, json, os, re, sys, threading, time
import urllib.error, urllib.request
from pathlib import Path

BASE = "https://www.redrecs.com"
UA = "Mozilla/5.0 (compatible; research-crawler/1.0)"
SKIP_PREFIXES = ("/api/", "/login")


class Limiter:
    """Global politeness: at most one request start every `gap` seconds across all workers."""

    def __init__(self, gap):
        self.gap, self.next, self.lock = gap, 0.0, threading.Lock()

    def wait(self):
        with self.lock:
            now = time.monotonic()
            t = max(now, self.next)
            self.next = t + self.gap
        if t > now:
            time.sleep(t - now)


def get(url, limiter, retries=6):
    """Return the page text, or None for a 404. Raises RuntimeError after repeated failures."""
    delay, last = 4, None
    for _ in range(retries):
        limiter.wait()
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept-Encoding": "gzip"})
            with urllib.request.urlopen(req, timeout=60) as r:
                raw = r.read()
                if (r.headers.get("Content-Encoding") or "").lower() == "gzip":
                    raw = gzip.decompress(raw)
                return raw.decode("utf-8", "replace")
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return None
            last = f"HTTP {e.code}"
            if e.code not in (403, 408, 425, 429, 500, 502, 503, 504):
                break
        except (OSError, EOFError, http.client.HTTPException) as e:
            # URLError, socket.timeout (not a TimeoutError before Python 3.10), resets, SSL errors,
            # IncompleteRead and a truncated gzip stream all land here: wait and retry.
            last = type(e).__name__
        time.sleep(delay)
        delay = min(delay * 2, 60)
    raise RuntimeError(f"{url}: gave up after {retries} tries ({last})")


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
        except (json.JSONDecodeError, KeyError):
            pass
    title = re.search(r"<title>(.*?)</title>", html, re.S)
    return {"kind": "page", "title": title.group(1) if title else None, "flight": text}


def sitemap_paths(limiter):
    xml = get(BASE + "/sitemap.xml", limiter)
    paths = []
    for u in re.findall(r"<loc>([^<]+)</loc>", xml or ""):
        p = re.sub(r"^https?://[^/]+", "", u) or "/"
        if not p.startswith(SKIP_PREFIXES):
            paths.append(p)
    return list(dict.fromkeys(paths))


def target_file(out, path):
    slug = path.strip("/") or "home"
    return out / (slug.replace("/", "__") + ".json")


def needs_fetch(f, refresh):
    if not f.exists():
        return True
    try:
        old = json.loads(f.read_text(encoding="utf-8"))
    except (OSError, ValueError):  # half-written or corrupt: fetch again
        return True
    if refresh and old.get("kind") == "analysis" and "source_urls" not in old:
        return True
    return False


def fetch_one(path, out, limiter):
    html = get(BASE + path, limiter)
    if html is None:
        return path, "missing", 0
    rec = extract(html)
    rec["path"] = path
    f = target_file(out, path)
    tmp = f.with_name(f.name + ".tmp")
    tmp.write_text(json.dumps(rec, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, f)  # atomic: a crash never leaves a half-written file
    n = len(rec["data"].get("products", [])) if rec["kind"] == "analysis" else 0
    return path, rec["kind"], n


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--workers", type=int, default=4, help="parallel downloads (default 4)")
    ap.add_argument("--rate", type=float, default=2.0, help="max requests per second in total (default 2)")
    ap.add_argument("--limit", type=int, default=0, help="stop after this many pages (for a trial)")
    ap.add_argument("--out", default="output/redrecs")
    ap.add_argument("--refresh", action="store_true", help="re-fetch ranking pages saved before source_urls was captured")
    a = ap.parse_args()

    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    for stale in out.glob("*.tmp"):
        stale.unlink()
    limiter = Limiter(1.0 / max(a.rate, 0.1))
    paths = sitemap_paths(limiter)
    todo = [p for p in paths if needs_fetch(target_file(out, p), a.refresh)]
    if a.limit:
        todo = todo[: a.limit]
    print(f"{len(paths)} URLs in sitemap, {len(todo)} to download ({len(paths) - len(todo)} already done)", flush=True)

    failed, done, t0 = [], 0, time.time()
    for attempt in (1, 2):
        if not todo:
            break
        if attempt == 2:
            print(f"retrying {len(todo)} failed page(s) more gently...", flush=True)
            time.sleep(15)
        workers = a.workers if attempt == 1 else 1
        failed = []
        ex = cf.ThreadPoolExecutor(max_workers=workers)
        futs = {ex.submit(fetch_one, p, out, limiter): p for p in todo}
        try:
            for fut in cf.as_completed(futs):
                p = futs[fut]
                try:
                    _, kind, n = fut.result()
                    done += 1
                    print(f"[{done}/{len(paths)}] {p} {kind} products={n}", flush=True)
                except Exception as e:  # one bad page must not stop the run
                    failed.append(p)
                    print(f"  failed: {e}", flush=True)
        except KeyboardInterrupt:
            ex.shutdown(wait=False, cancel_futures=True)
            print("\nstopped; run the same command again to resume", flush=True)
            return 130
        ex.shutdown()
        todo = failed
    secs = time.time() - t0
    if failed:
        print(f"\nfinished in {secs:.0f}s with {len(failed)} page(s) not downloaded:\n  " + "\n  ".join(failed))
        print("run the same command again to retry them")
        return 1
    print(f"\ndone: {done} page(s) in {secs:.0f}s, nothing missing")
    return 0


if __name__ == "__main__":
    sys.exit(main())
