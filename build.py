#!/usr/bin/env python3
"""Mirror blog.acqrs.co.uk (Bludit on the Hetzner box) into a self-contained static site.

Reads from the origin over an ssh -L tunnel (no Cloudflare edge rewrites) and
writes site/ ready for static hosting: clean-URL directory indexes, optimised
images, no references back to the old hgtphisoc.org domain.
"""
import os, re, io, json, ssl, urllib.request, urllib.error, urllib.parse
from PIL import Image

BASE   = os.environ.get("ORIGIN", "http://127.0.0.1:18081")   # tunnel to bludit :9999
HOST   = "blog.acqrs.co.uk"
PUBLIC = "https://blog.acqrs.co.uk"
OLD    = "https://hgtphisoc.org"          # Bludit's configured siteURL
ROOT   = "/home/hermes/projects/blog-static"
SITE   = os.path.join(ROOT, "site")
UA     = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120 Safari/537.36"
CTX    = ssl.create_default_context()

POSTS = [
    "yes-it-talks-about-that-read-the-other-books-a-review-of-wool-by-hugh-howey",
    "a-benelovent-autocracy-interested-in-your-philosophical-wellfare-or-how-we-choose-books",
    "elevated-reflections-terre-des-hommes",
    "is-infinite-information-no-information-a-review-of-the-book-that-wouldn-t-burn-by-mark-lawrence",
    "a-reflective-revisit-balancing-tech-optimism-and-literary-nostalgia-in-mr-penumbra-s-24-hour-bookstore",
    "about",
]
SEED = ["/"] + ["/" + s for s in POSTS] + ["/dtsearch"]

IMG_EXT = {".png", ".jpg", ".jpeg", ".gif", ".bmp"}
REF_RE  = re.compile(r'(href|src|content|data-src)="([^"]+)"')
CSSURL  = re.compile(r'url\(\s*[\'"]?([^\'")]+)[\'"]?\s*\)')

# ------------------------------------------------------------------ fetching
def fetch(path):
    url = BASE + urllib.parse.quote(path, safe="/%")
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Host": HOST})
    try:
        with urllib.request.urlopen(req, timeout=40, context=CTX) as r:
            return r.status, r.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read()

def internal_path(ref):
    ref = ref.strip()
    if ref.startswith(OLD):
        ref = ref[len(OLD):] or "/"
    if ref.startswith("/") and not ref.startswith("//"):
        return ref.split("?")[0].split("#")[0]
    return None

def clean(u):
    return u.split("?")[0].split("#")[0]

def is_asset(p):
    return bool(os.path.splitext(p)[1]) and not p.endswith("/")

# ------------------------------------------------------------------ crawl pages
pages = {}          # path -> html
queue = list(SEED)
while queue:
    p = queue.pop(0)
    if p in pages:
        continue
    st, body = fetch(p)
    if st != 200:
        print(f"  ! page {st} {p}")
        continue
    html = body.decode("utf-8", "replace")
    pages[p] = html
    for m in REF_RE.finditer(html):
        q = internal_path(m.group(2))
        if not q or q.startswith("/cdn-cgi"):
            continue
        if is_asset(q) or q in pages:
            continue
        queue.append(q)

st, body = fetch("/__definitely_not_here__")
PAGE404 = body.decode("utf-8", "replace")
print(f"pages: {len(pages)} (+404)")

# ------------------------------------------------------------------ assets
refs = set()
for html in list(pages.values()) + [PAGE404]:
    for m in REF_RE.finditer(html):
        q = internal_path(m.group(2))
        if q and is_asset(q):
            refs.add(q)
    for m in CSSURL.finditer(html):
        q = internal_path(m.group(1))
        if q and is_asset(q):
            refs.add(q)

# assets referenced from JS rather than HTML
EXTRA_ASSETS = ["/bl-content/uploads/bltsearch.json"]
refs.update(EXTRA_ASSETS)

mapping = {}        # old path -> new path
done    = {}
def save(path, data):
    dest = os.path.join(SITE, path.lstrip("/"))
    os.makedirs(os.path.dirname(dest) or SITE, exist_ok=True)
    with open(dest, "wb") as f:
        f.write(data)

def sanitize(path):
    """Keep asset URLs to a safe charset (spaces, middle dots, commas -> '-')."""
    d, f = os.path.split(path)
    f = re.sub(r"[^A-Za-z0-9._-]+", "-", f)
    return (d + "/" + f) if d else f

def optimise(path, data):
    ext = os.path.splitext(path)[1].lower()
    if ext not in IMG_EXT or len(data) < 40_000:
        return path, data
    try:
        im = Image.open(io.BytesIO(data)); im.load()
    except Exception as e:
        print("  ! image", path, e); return path, data
    if im.mode not in ("RGB", "RGBA"):
        im = im.convert("RGBA" if "A" in im.getbands() else "RGB")
    maxw = 256 if ("Harrogate Phil" in path or "apple-touch" in path) else 1400
    if im.width > maxw:
        im = im.resize((maxw, round(im.height * maxw / im.width)), Image.LANCZOS)
    buf = io.BytesIO(); im.save(buf, "WEBP", quality=82, method=6)
    out = buf.getvalue()
    if len(out) < len(data) * 0.92:
        return os.path.splitext(path)[0] + ".webp", out
    return path, data

q = sorted(refs)
total_in = total_out = 0
while q:
    raw = q.pop(0)
    p = clean(raw)
    if p in done:
        mapping.setdefault(raw, done[p])
        continue
    st, data = fetch(p)
    if st != 200:
        print(f"  ! asset {st} {p}"); done[p] = None; continue
    total_in += len(data)
    low = p.lower()
    if low.endswith((".css", ".js", ".json", ".webmanifest", ".xml", ".svg", ".txt")):
        data = data.decode("utf-8", "replace").replace(OLD + "/", "/").replace(OLD, "").encode()
    newp, newd = optimise(p, data)
    newp = sanitize(newp)
    save(newp, newd)
    total_out += len(newd)
    done[p] = newp
    mapping[p] = newp
    mapping[raw] = newp
    if low.endswith(".css"):
        base = os.path.dirname(p)
        for m in CSSURL.finditer(newd.decode("utf-8", "replace")):
            u = m.group(1).strip()
            if u.startswith(("data:", "http", "//")):
                continue
            r = u if u.startswith("/") else os.path.normpath(os.path.join(base, u))
            if not r.startswith("/"):
                r = "/" + r
            if r not in done:
                q.append(r)
    if newp != p:
        print(f"  img {p} {len(data)//1024}K -> {newp} {newd.__len__()//1024}K")

print(f"assets: {len(done)} fetched, {total_in/1048576:.2f} MB -> {total_out/1048576:.2f} MB")

# rewrite relative url() inside every saved css file now that the map is complete
for root, _, files in os.walk(SITE):
    for f in files:
        if not f.endswith(".css"):
            continue
        full = os.path.join(root, f)
        rel  = "/" + os.path.relpath(full, SITE)
        base = os.path.dirname(rel)
        css  = open(full, encoding="utf-8").read()
        def sub(m):
            u = m.group(1).strip()
            if u.startswith(("data:", "http", "//")):
                return m.group(0)
            r = u if u.startswith("/") else os.path.normpath(os.path.join(base, u))
            new = mapping.get(r) or mapping.get(clean(r), u)
            return "url(" + new + ")"
        open(full, "w", encoding="utf-8").write(CSSURL.sub(sub, css))

# ------------------------------------------------------------------ html
def rewrite(html):
    def repl(m):
        raw = m.group(2)
        key = internal_path(raw)
        new = None
        if key:
            new = mapping.get(key) or mapping.get(raw)
        if new:
            return f'{m.group(1)}="{new}"'
        return m.group(0)
    html = REF_RE.sub(repl, html)
    html = CSSURL.sub(lambda m: "url(" + mapping.get(m.group(1), m.group(1)) + ")", html)
    # internal links back to the old domain -> root-relative
    html = html.replace(OLD + "/", "/").replace(OLD, "")
    # anything still naming the old domain (share links, mailto bodies) -> new host
    html = html.replace("https%3A%2F%2Fhgtphisoc.org", "https%3A%2F%2Fblog.acqrs.co.uk")
    html = html.replace("club@hgtphisoc.org", "%%EMAIL%%")
    html = html.replace("hgtphisoc.org", "blog.acqrs.co.uk")
    html = html.replace("%%EMAIL%%", "club@hgtphisoc.org")
    # client-side search results must point at this host
    html = html.replace('domainBase="/"', 'domainBase="/"')
    return html

targets = {"404.html": PAGE404}
for p, html in pages.items():
    targets["index.html" if p == "/" else p.strip("/") + "/index.html"] = html
for out, html in targets.items():
    body = rewrite(html)
    save(out, body.encode())

# sitemap + robots
urls = ["/"] + ["/" + s for s in POSTS] + ["/dtsearch"] + [p for p in pages if p not in SEED]
sm = ['<?xml version="1.0" encoding="UTF-8"?>',
      '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">']
for u in sorted(set(urls)):
    sm.append(f"  <url><loc>{PUBLIC}{u}</loc></url>")
sm.append("</urlset>")
save("sitemap.xml", "\n".join(sm).encode())
save("robots.txt", f"User-agent: *\nAllow: /\nSitemap: {PUBLIC}/sitemap.xml\n".encode())

json.dump(mapping, open(os.path.join(ROOT, "mapping.json"), "w"), indent=1)
size  = sum(os.path.getsize(os.path.join(r, f)) for r, _, fs in os.walk(SITE) for f in fs)
files = sum(len(fs) for _, _, fs in os.walk(SITE))
print(f"DONE: {files} files, {size/1048576:.2f} MB")
