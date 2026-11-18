# Existing site builds across the repos

Surveyed 2026-11-18: about 20 repos under `~/git`. Seven build a static site with their own
Python script; each writes an output folder that a GitHub Pages workflow uploads under
`/<repo>/`. Each handles the "little stuff" differently and none has all of it.

## Own build scripts

| Repo | Build | Has | Missing |
| --- | --- | --- | --- |
| aesop | `uv run build` (`build/__main__.py`), Jinja, `content/*.yaml` + `.md` → `site/` | description, OG (type, site_name, title, description, url, image), `twitter:card`, canonical, SVG favicon, `lang`, `index.md` siblings, `llms.txt` / `llms-full.txt`, `.nojekyll`, `static/` copy. `base_url` from `site.yaml`, `BASE_URL` env override | sitemap, robots, 404, analytics |
| ottowww | `ottowww --content … --out _site --base-url … --base-path /ottowww/`, Jinja `PackageLoader` + `StrictUndefined`, markdown-it | `Site(base_url, base_path)` with `.url()` / `.absolute()`, languages at `/<lang>/` with a root language page, `sitemap.xml` with `xhtml:link hreflang`, canonical, hreflang, OG title/description/url | favicon, OG image, Twitter tags, robots |
| podcast-template | `podcast build --out public`, Jinja, `podcast.toml` + `episodes/*.md` | RSS `feed.xml` (iTunes tags), feed `<link rel=alternate>`, cover as favicon, `lang`, guard refusing an unsafe output folder | OG, canonical, sitemap. Links relative via `root="../../"` |
| changelog | `cha …` writes into the separate repo changelog-chronicles.github.io | HTML, JSON, `llms.txt`, `.well-known/atproto-did`; clearing output keeps `.git` and `CNAME` | description, favicon, sitemap, feed; OG only on one page. Links relative via `root` |
| clauding | `uv run build`, f-strings (no template engine), markdown + frontmatter | description, `lang`, `index.md` siblings, `llms.txt` / `llms-full.txt`, `.nojekyll`. `BASE_URL` default `/clauding` | OG, favicon, canonical, sitemap |
| sketchpy | `scripts/build.py` (595 lines) → `output/` | timestamped JS names (only cache-busting found) | nearly all meta |
| noticky | `do.py publish`, Jinja, output committed in `public/` | richest head: OG + Twitter, generated OG images, full favicon package (ico, PNGs, apple-touch, `site.webmanifest`, `browserconfig.xml`), `robots.txt`, `sitemap.txt`, Plausible | most of it hand-dropped into `public/` |

## Hand-written or data-only

- saints-calendar: hand-written `site/` (cs + `en/`); build writes `.ics` and `days.json`. Has description, emoji favicon, hreflang.
- trains-de: one `page.html.j2` with inline CSS; the workflow writes a meta-refresh `index.html`.
- happytube: hand-written `index.html`, build writes `videos.json`.
- model-comparison: f-string HTML; the daily workflow commits `out/`.

## Owned by a static site generator

- orch: zensical. braindump, comicforge, introspect: mkdocs. biston, gerenuk, madoqua, dermestes, ty-find: mdBook, each with its own drifted copy of `docs/generate-llms-txt.sh`.
- These already make sitemap, 404 and search. They only need extras deedum can add next to the SSG output (llms.txt, favicons, OG image).

## Out of scope

Server-rendered: famtodo, esl, ideas-viewer. bookmaker-review pages are `noindex`. cecil is a local app.

## Shared or duplicated today

- aesop's `docs-theme/sync.py` copies one JS/CSS theme into the mdBook repos (byte-identical, "GENERATED COPY" header).
- The same build skeleton is written out at least six times: Jinja `Environment(autoescape, trim_blocks, lstrip_blocks)` (StrictUndefined in ottowww and podcast-template); `render(template, out_path, **ctx)` with `mkdir -p`; `rmtree(out)` → `copytree(static)` → touch `.nojekyll`; `llms.txt` generation.
- Three URL styles: a full `base_url` prefix (aesop), base url + base path (ottowww), relative `root` prefixes (podcast-template, changelog). Canonical and OG URLs need absolute URLs, so relative-link sites still need a `base_url`.

## Takeaways

- Typical build: load config and content → Jinja env → clear output → render pages → copy static → write extras → Pages upload.
- First adopters: aesop (migration should be close to pure deletion), ottowww (its `Site` and sitemap are the model for deedum's), clauding (f-strings → templates), then podcast-template and changelog (relative mode, feeds).
- SSG and hand-written sites want only an `extras` step run after their own build.
