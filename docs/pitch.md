---
title: deedum, first cut
pitch: A small Python package and CLI that builds static sites from the target repo's own templates and content, and does the boring parts (head tags, favicons, sitemap, robots, feeds, llms.txt) for them.
maturity: shaped
created: 2026-11-18
---

# deedum, first cut

Background: [constitution](constitution.md),
[existing site builds](research/existing-site-builds.md),
[the old do.py generators](research/old-do-py-generators.md). Decisions in
[decisions/](decisions/) (library plus convention CLI, Jinja/markdown-it/YAML, config and
URL model) apply to every phase.

## Problem

Seven small sites are built by their own Python scripts and a few more are hand-written
or SSG-built. Each one handles Open Graph and Twitter tags, canonical URLs, favicons,
sitemap, robots.txt, feeds, llms.txt, `.nojekyll` and 404 differently, and none has all
of them. The build skeleton (Jinja env, render helper, clear output, copy static, write
extras) is copied between repos. We want one package that does these parts correctly,
lets each site keep its own look and content, and is small enough to read.

Users: the repo owner and Claude Code sessions building sites in other repos. Readers of
the CLI output are often agents.

## Requirements

Site and URLs

- **R1** Site config is read from `deedum.toml`, or from `[tool.deedum]` in
  `pyproject.toml` when there is no `deedum.toml`. Keys: `title`, `description`,
  `base_url`, `base_path` (default `/`), `lang` (default `en`), `author`,
  `image` (default social image, a path in the site), `favicon` (source image path),
  `twitter` (handle), `analytics` (Plausible domain, optional), `head_extra` (raw HTML
  snippet, optional), `relative_links`, `feeds` (collections that get a feed),
  `llms` (bool), `robots_extra_sitemaps` (list of absolute URLs), folder names
  (`content`, `templates`, `static`, `data`, `out`, defaults as named except `out` =
  `_site`), and `app` (`module:Class`, optional). A missing `title` or `base_url`, an
  unknown key, or a wrong type fails with a message naming the file and the key.
- **R2** `base_url` and `base_path` can be overridden by `DEEDUM_BASE_URL` /
  `DEEDUM_BASE_PATH` and by `--base-url` / `--base-path`; flags win over env, env over
  the file. `base_path` is normalised to a leading and trailing slash.
- **R3** Templates get `url(path)` (root-relative link including the base path, or a
  page-relative link when `relative_links` is on) and `absolute(path)` (full URL). With
  `base_url = "https://mojzis.github.io"` and `base_path = "/aesop/"`,
  `absolute("tools/biston/")` is `https://mojzis.github.io/aesop/tools/biston/`.
  `url()` and `absolute()` leave a URL with a scheme untouched.

Rendering

- **R4** Jinja environment per decision 0002: autoescape on, `StrictUndefined`, the
  target's `templates/` folder searched before deedum's built-ins. Globals: `site`,
  `page`, `url`, `absolute`, `collections`, `data`, `now` (build time, UTC). A target
  file with the same name as a built-in (e.g. `deedum/head.html`) replaces it.
- **R5** A built-in head partial, used as `{% include "deedum/head.html" %}`, emits for
  the current page: charset, viewport, `<title>` (page title and site title, or the site
  title alone on the home page), meta description, canonical, `og:type` (`article` for
  dated pages, else `website`), `og:site_name`, `og:title`, `og:description`, `og:url`,
  `og:image` (page image, else site image, absolute; with width and height when deedum
  can read them), `og:locale`, `twitter:card` (`summary_large_image` with an image, else
  `summary`), `twitter:site` when set, favicon links, feed alternate links, `hreflang`
  alternates when the page has them, `robots noindex` when the page sets `noindex`, the
  Plausible snippet when `analytics` is set, and `head_extra`. A tag whose value is empty
  is left out, never emitted empty. All values are escaped.
- **R6** A built-in `deedum/base.html` (`<html lang>`, the head partial, blocks `head`,
  `nav`, `content`, `footer`) and a plain `page.html` that extends it, so a site with no
  templates of its own still builds a readable page. Minimal inline CSS, no JS.

Convention build

- **R7** Every `*.md` under `content/` becomes a page. Path mirrors the file:
  `content/blog/hello.md` → `/blog/hello/index.html`, `content/about.md` →
  `/about/index.html`, `content/index.md` → `/index.html`, `content/blog/index.md` →
  `/blog/index.html`. Frontmatter `slug` replaces the file name part. Files starting with
  `_` and pages with `draft: true` are skipped.
- **R8** A page has: every frontmatter field, `body` (rendered HTML, safe), `source`
  (raw markdown), `url`, `title` (frontmatter, else the first `#` heading, which is then
  removed from `body`, else the file name), `description` (frontmatter, else the first
  paragraph as plain text cut to 160 characters at a word boundary), `date` and
  `updated` (frontmatter dates, optional), `collection` (top-level folder under
  `content/`, none for root files), `image`, `noindex`, `lang`, `alternates`. Template:
  frontmatter `template`, else `<collection>.html` if the target has it, else `page.html`.
- **R9** `collections.<name>` lists a collection's pages (its `index.md` excluded),
  dated pages newest first, then undated by title. `data.<name>` holds each
  `data/<name>.yaml|.yml|.toml|.json` file, parsed.
- **R10** Every file under `static/` is copied to the output root as is. A path that is
  both a static file and a rendered page fails the build naming both.
- **R11** With `app = "site:Site"` in the config, `deedum build` imports that class
  (from the target repo root) and uses it. `deedum.App` hooks, all optional to override:
  `load_pages()` (return the page list; default is R7–R8, an override can add pages
  generated from data, e.g. one page per entry of `data/tools.yaml`), `context(page)`
  (extra template variables), `filters()` and `globals()` (added to the Jinja env), and
  `after_build(out)`. An import or hook error fails the build naming the hook.
- **R12** Python API for repos with their own script: build a `Site` from a config
  path or keyword arguments, create a `Builder(site, out)`, call
  `builder.render(template, path, **context)` for each page (the page is recorded for
  the sitemap and feeds), `builder.copy_static(src)`, then `builder.finish()`, which
  writes every extra (R13–R18) the config turns on. `deedum.head_tags(site, page)`
  returns the R5 head as markup for scripts that don't use deedum's Jinja env.
  The convention build uses this same API.

Extras

- **R13** `sitemap.xml` lists every rendered HTML page except `noindex` ones and 404,
  with absolute URLs, `lastmod` from `updated` or `date` when present, and
  `xhtml:link hreflang` entries for pages with alternates. It is well-formed XML in the
  sitemaps.org namespace.
- **R14** `robots.txt` allows all and has a `Sitemap:` line for this site, plus one line
  per `robots_extra_sitemaps` entry (a root site lists the project sites' sitemaps,
  since crawlers only read robots.txt at the domain root).
- **R15** Favicons from one source image (`favicon` key): SVG, or PNG at least 512 px
  square. Output: `favicon.ico` (16, 32, 48), `favicon.svg` (when the source is SVG),
  `apple-touch-icon.png` (180), `icon-192.png`, `icon-512.png`, `site.webmanifest`
  (name, icons, theme colour from config or white). The head partial links them. A
  missing or too small source fails naming the file. No source configured → no favicon
  files and no favicon links.
- **R16** An Atom 1.0 `feed.xml` per collection listed in `feeds`, at
  `/<collection>/feed.xml`, newest 20 dated pages, absolute links, full HTML content,
  `updated` from the newest entry. Undated pages are left out. The head partial links
  the feed of the page's collection, and the home page links every feed.
- **R17** With `llms = true`: `llms.txt` (site title, description, a markdown list of
  pages with absolute URLs and descriptions, grouped by collection), `llms-full.txt`
  (every page's markdown source), and an `index.md` sibling next to each page's
  `index.html` holding its markdown source (pages without a markdown source skip it).
- **R18** Always: `.nojekyll`; `404.html` from the target's `404.html` template or a
  built-in one (`noindex`, links home).
- **R19** The output folder is cleared before a build but `.git` and `CNAME` survive.
  deedum refuses (and changes nothing) when the output folder is the repo root, the
  user's home, a parent of the repo, or contains the content, templates, static or data
  folder.

CLI (typer + typer-agentic per docs/standards/cli.md)

- **R20** `deedum build [--out] [--base-url] [--base-path] [--config]` builds and prints
  one line per kind of output (pages, static files, extras) with counts.
- **R21** `deedum extras <dir> [--config]` for folders built by something else: reads
  the config, scans `<dir>` for `*.html` (skipping files with a robots noindex meta),
  and writes sitemap, robots, favicons, `.nojekyll` into `<dir>`. It never edits
  existing HTML and never deletes anything; it prints the `<link>` tags the site should
  add for favicons.
- **R22** `deedum serve [--port]` builds with `base_url = http://localhost:<port>`,
  serves the output with the base path mounted, and rebuilds when content, templates,
  static, data or config change. A failed rebuild prints the error and keeps serving the
  last good build.
- **R23** `deedum init` in an empty or existing repo writes `deedum.toml` (with
  placeholders and comments), `content/index.md`, `templates/page.html` (extends the
  built-in base, as an override example), an empty `static/`, and
  `.github/workflows/pages.yml` (uv, `deedum build`, upload, deploy). It never
  overwrites an existing file; it lists what it skipped.
- **R24** `deedum new <collection> "<title>"` writes `content/<collection>/<slug>.md`
  with frontmatter `title` and today's `date`, from `templates/new/<collection>.md` when
  that exists. Refuses to overwrite.
- **R25** `deedum check [<dir>]` reads a built output folder and reports, per page:
  missing title, description, canonical or `og:image`; internal links and asset
  references that point to no file in the output (respecting the base path); leftover
  `{{` or `{%`. Exit code 1 when anything is found. `deedum build --check` runs it after
  the build.
- **R26** `deedum guide` explains the three ways in, the config keys and the template
  names, per the toolbox guide convention in docs/standards/cli.md.

Example and docs

- **R27** `examples/demo/` is a small site using every feature: a `blog` collection with
  a feed, an `about` page, a data file turned into pages by an `App` subclass, a
  template override of `deedum/head.html` that extends the built-in one, a favicon SVG,
  `llms = true`, a base path. Tests build it end to end and check the output.
- **R28** README: what deedum does, the three ways in with a short example each, the
  config reference. Written to stand alone.

## Rabbit holes

- **SVG rasterising.** No system libraries (no cairo). Use a rasteriser that ships
  wheels (e.g. resvg-py) or Pillow-only paths; the gate must not need anything outside
  `uv sync`. If no wheel-only SVG rasteriser works, accept PNG sources only and say so in
  `deviations`.
- **Description from the first paragraph.** Plain text from the markdown token stream,
  not regex over HTML.
- **Relative links.** Compute from the page's output path, not by string counting; test
  pages at depth 0, 1 and 2, and with a base path.
- **The serve watcher.** Use a maintained watcher (e.g. watchfiles). Debounce. Don't
  build a live-reload websocket.
- **Time in output.** Feed and sitemap dates come from page dates; the build time is
  used only where a spec requires one. Tests freeze it, so builds are reproducible.
- **Tests stay offline.** No test touches the network.

## No-gos

- No plugin system or entry points. Plausible is a config key, not a plugin.
- No Jupyter notebooks, no link-preview fetching (svata's OG fetch), no network at build.
- No deployment (Netlify, Pages API). `init` writes a workflow file, that's all.
- No generated OG images (text to image). No image resizing beyond favicons.
- No i18n machinery: pages may carry `lang` and `alternates`, nothing translates.
- No asset hashing, bundling or minifying. No JS in the built-in templates beyond the
  Plausible snippet.
- No migration of other repos (aesop, ottowww, clauding, ...) in this run; each gets its
  own run in its repo.
- No PyPI release in this run.

## Appetite

About a week of one person's work, 6–8 phases. If something has to give, cut R25
(check), then the watcher in R22 (serve without rebuild), then R24 (new), then
relative links in R3.

## Acceptance

- `uv run poe check` passes.
- `uv run deedum build` in `examples/demo/` produces a site whose pages carry the full
  head, plus `sitemap.xml`, `robots.txt`, favicons and manifest, the blog `feed.xml`,
  `llms.txt`, `llms-full.txt`, `index.md` siblings, `404.html` and `.nojekyll`, and
  `deedum check` on it reports nothing.
- `sitemap.xml` and `feed.xml` parse as XML and use absolute URLs under the base path.
- `deedum extras` on a folder of hand-written HTML adds sitemap, robots and favicons
  without changing any existing file.
- `deedum init` in an empty folder followed by `deedum build` produces a site that
  `deedum check` accepts, apart from the placeholder description.
