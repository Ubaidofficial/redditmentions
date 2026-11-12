#!/usr/bin/env python3
"""
Faster, parallel version of scrape_wayback.py. Uses the same pages/ folder,
so it continues where the old script stopped.

    python3 scrape_fast.py                  # 4 workers
    python3 scrape_fast.py --workers 6      # more workers (more risk of throttling)
    python3 scrape_fast.py --skip-brand     # skip /<category>/brand/... pages
    python3 scrape_fast.py --gap 1          # gentler: at most 1 request per second

Speed is capped by a shared limit that slows down automatically when
archive.org pushes back (429 / dropped connections) and speeds up slowly again.
"""
import hashlib, json, os, re, sys, threading, time
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import urlparse
import requests

OUT = "pages"
CDX = "https://web.archive.org/cdx/search/cdx"
UA = {"User-Agent": "personal-research-archiver/1.0"}
CUTOFF = "20261102"                      # site became a "shut down" page on 2026-11-02
SHUTDOWN_MARK = b"RedditRecs has shut down"
SKIP = re.compile(r"/_nuxt/|\.(js|css|png|jpe?g|webp|svg|ico|woff2?|json|xml|txt)$", re.I)

args = sys.argv[1:]
WORKERS = int(args[args.index("--workers") + 1]) if "--workers" in args else 4
SKIP_BRAND = "--skip-brand" in args

class Limiter:
    """Shared pace for all workers: at most one request start per `gap` seconds.
    Backs off when archive.org pushes back, and recovers again fairly quickly."""
    def __init__(self, gap, min_gap, max_gap=8.0):
        self.gap, self.min_gap, self.max_gap = gap, min_gap, max_gap
        self.next_at = 0.0; self.lock = threading.Lock(); self.ok_streak = 0; self.last_push = 0.0
    def wait(self):
        with self.lock:
            now = time.time(); t = max(now, self.next_at); self.next_at = t + self.gap
        time.sleep(max(0, t - now))
    def pushback(self):
        with self.lock:
            now = time.time(); self.ok_streak = 0
            if now - self.last_push < 45:          # several workers hit the same throttle: count it once
                return
            self.last_push = now
            self.gap = min(self.max_gap, self.gap * 2)
            self.next_at = now + 60                # everyone pauses 60 s
            print(f"   archive.org pushed back -> pausing 60s, then 1 request per {self.gap:.1f}s", flush=True)
    def success(self):
        with self.lock:
            self.ok_streak += 1
            if self.ok_streak >= 15 and self.gap > self.min_gap:
                self.gap = max(self.min_gap, self.gap * 0.75); self.ok_streak = 0

GAP = float(args[args.index("--gap") + 1]) if "--gap" in args else 0.5
limiter = Limiter(gap=GAP, min_gap=GAP)
local = threading.local()
def session():
    if not hasattr(local, "s"):
        local.s = requests.Session(); local.s.headers.update(UA)
    return local.s

def fetch(url, **kw):
    for attempt in range(6):
        limiter.wait()
        try:
            r = session().get(url, timeout=90, **kw)
        except requests.RequestException:
            limiter.pushback(); continue
        if r.status_code in (429, 503, 504):
            limiter.pushback(); continue
        if r.status_code == 200:
            limiter.success()
        return r
    return None

def page_index():
    if os.path.exists("index.json"):
        return {k: tuple(v) for k, v in json.load(open("index.json")).items()}
    rows = []
    for host in ("redditrecs.com", "www.redditrecs.com"):
        r = fetch(CDX, params={"url": host, "matchType": "prefix", "output": "json",
                               "fl": "timestamp,original,statuscode,mimetype",
                               "filter": ["statuscode:200", "mimetype:text/html"]})
        if r is not None and r.status_code == 200 and r.text.strip():
            rows += r.json()[1:]
    latest = {}
    for ts, orig, _, _ in rows:
        p = urlparse(orig); path = (p.path.rstrip("/") or "/").lower()
        if SKIP.search(path) or p.query or ts >= CUTOFF:
            continue
        if path not in latest or ts > latest[path][0]:
            latest[path] = (ts, orig)
    json.dump(latest, open("index.json", "w"), indent=1, sort_keys=True)
    return latest

def kind(path):
    parts = path.strip("/").split("/")
    if len(parts) == 1: return 0, "category/other"
    if parts[1] == "filters": return 1, "filter"
    if parts[1] == "model": return 2, "model"
    if parts[1] == "brand": return 3, "brand"
    return 4, "other"

def filename(path):
    name = path.strip("/").replace("/", "__") or "_home"
    if len(name) > 150 or ":" in name:
        # some junk URLs are very long; keep the start and add a short unique hash
        h = hashlib.md5(path.encode()).hexdigest()[:10]
        name = re.sub(r"[^a-zA-Z0-9_.-]", "_", name)[:100] + "__" + h
    return os.path.join(OUT, name + ".html")

def main():
    os.makedirs(OUT, exist_ok=True)
    idx = page_index()
    todo, counts = [], {}
    for path, (ts, orig) in idx.items():
        pri, k = kind(path); counts[k] = counts.get(k, 0) + 1
        if SKIP_BRAND and k == "brand":
            continue
        fn = filename(path)
        if os.path.exists(fn) and SHUTDOWN_MARK not in open(fn, "rb").read():
            continue
        todo.append((pri, path, ts, orig))
    todo.sort()
    print(f"{len(idx)} pages in archive index: " + ", ".join(f"{v} {k}" for k, v in sorted(counts.items())))
    print(f"{len(idx) - len(todo)} already done or skipped, {len(todo)} to download, {WORKERS} workers", flush=True)
    done = [0]; fails = [0]; lock = threading.Lock(); recent = []
    def work(item):
        _, path, ts, orig = item
        try:
            r = fetch(f"https://web.archive.org/web/{ts}id_/{orig}")
        except Exception:
            r = None
        with lock:
            done[0] += 1
            status = "FAIL"
            if r is not None and r.status_code == 200 and SHUTDOWN_MARK not in r.content:
                try:
                    open(filename(path), "wb").write(r.content); status = "ok  "
                except OSError as e:
                    print(f"   could not save {path[:80]}: {e}")
            if status == "FAIL":
                fails[0] += 1
            now = time.time(); recent.append(now)
            while recent and now - recent[0] > 300:
                recent.pop(0)
            rate = len(recent) / max(60, min(300, now - recent[0])) * 60 if recent else 0
            eta = (len(todo) - done[0]) / max(rate, 0.01)
            print(f"[{done[0]}/{len(todo)}] {status} {path}   ({rate:.0f}/min last 5 min, ~{eta/60:.1f}h left)", flush=True)
    try:
        with ThreadPoolExecutor(WORKERS) as ex:
            list(ex.map(work, todo))
    except KeyboardInterrupt:
        print("\nStopped. Run the same command again to continue.")
        os._exit(1)
    print(f"Finished: {done[0] - fails[0]} saved, {fails[0]} failed. Run again to retry failures.")

if __name__ == "__main__":
    main()
