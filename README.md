# blog.acqrs.co.uk

Static source of truth for the Harrogate Philosophical Society blog.

- **Live:** https://blog.acqrs.co.uk
- **Hosting:** Cloudflare Worker `blog-acqrs` — Workers static assets, account `42b2d98d9a78704a355c9a4f930c6065`, zone `acqrs.co.uk` (`466bda6631f7575f444110ad352c2fae`)
- **Deploy:** push to `main` → GitHub Actions runs `wrangler deploy` → assets upload → live

`site/` is the whole website. Everything else is tooling.

## Editing the site

Edit files in `site/` and push to `main`. There is no build step for normal edits.

- Clean URLs are directories with an `index.html`: `site/about/index.html` serves `/about`.
  A new post is `site/<slug>/index.html`.
- The canonical form has **no** trailing slash (`/about`, not `/about/`); the Worker config
  `html_handling = "drop-trailing-slash"` redirects `/about/` to `/about`.
- Missing paths serve `site/404.html` with a real 404 status.
- `site/bl-content/uploads/bltsearch.json` is the client-side search index used by `/dtsearch`;
  add new posts to that array as well (or regenerate the whole tree from the CMS).
- Images: prefer WebP and keep filenames to `[A-Za-z0-9._-]` (no spaces) so URLs need no escaping.

## Deploying

`.github/workflows/deploy.yml` deploys on every push to `main`, then smoke-tests `/`, `/about`,
`/dtsearch`, `/sitemap.xml`, the search index and the 404 behaviour.

It needs one repository secret:

| secret | value |
| --- | --- |
| `CLOUDFLARE_API_TOKEN` | API token with **Account → Workers Scripts → Edit** for `Mttypl@gmail.com's Account` |

Without it the job fails fast with an explicit message — nothing silently skips the deploy.

Local deploy, with such a token:

```bash
CLOUDFLARE_API_TOKEN=... npx wrangler deploy
```

### Alternative: Cloudflare Workers Builds (no secret)

Dashboard → Workers & Pages → `blog-acqrs` → Settings → Builds → Connect, pick this repo,
branch `main`, deploy command `npx wrangler deploy`. Cloudflare then builds and deploys on push
itself and the Actions workflow can be deleted. This needs the Cloudflare GitHub App installed on
the account, which only the account owner can authorise.

## Rebuilding from the Bludit CMS

`build.py` mirrors the original Bludit install (still running on the Hetzner box, which serves
`hgtphisoc.org`) into `site/`. It reads the origin over a local SSH tunnel so Cloudflare's edge
rewrites never end up in the HTML:

```bash
ssh -f -N -L 18081:127.0.0.1:9999 matt@95.216.187.160
python3 build.py                 # rewrites site/
git add -A && git commit -m "Mirror CMS content" && git push
```

It crawls every published page (posts, about, search, category + tag listings, the 404 page),
rewrites the CMS's absolute `https://hgtphisoc.org/...` URLs to root-relative paths, points share
links at `blog.acqrs.co.uk`, converts PNG/JPEG over 40 KB to WebP (max 1400 px, q82 — 11.2 MB →
2.7 MB), and regenerates `sitemap.xml` and `robots.txt`.

## History: how it was migrated

The blog ran as PHP (Bludit) behind Caddy on a Hetzner VPS. On 2026-11-14 it was mirrored to
static files and moved to Cloudflare:

- The domain's proxied `A 95.216.187.160` record was deleted and `blog.acqrs.co.uk` was attached
  as a Worker custom domain, so Cloudflare owns the CNAME and certificate (`cert_id 5d45ddc3…`).
- The Worker is deployed as an **assets-only** script — no `main_module`. With a stub worker,
  unmatched paths invoke the worker, `env.ASSETS` is undefined there, and the site 500s instead of
  serving `404.html`.
- `upload_assets.py` exists because at migration time the only Cloudflare credentials available
  were the read-only `cfut_` token in `~/.cloudflared/cert.pem` (no Workers write) plus the MCP
  OAuth session. The trick was to split the assets protocol: create the upload session and attach
  the version through the API (small payloads), but push the file bytes from the local machine
  with the short-lived upload JWT. Actions + a real token makes that unnecessary.

## Gotchas

- `robots.txt` in `site/` is ignored in production: the zone has Cloudflare's **managed
  robots.txt** enabled, which serves the edge's own content-signals file.
- Client-side search on `/dtsearch` returns no results — it behaves the same on the original
  Bludit site, so it is a pre-existing theme bug, not a regression.
- The CMS's unpublished draft (`a-short-stay-in-hell`) is intentionally absent; it 404s upstream.
- Rollback of the whole migration: re-add `A blog.acqrs.co.uk → 95.216.187.160` (proxied) and
  delete the Worker custom domain; the Hetzner Caddy vhost still exists.
