# deedum

deedum builds a small static website from a folder of markdown files, or from a few
lines of Python, and does the boring parts for you: the full `<head>` (title,
description, canonical, social tags, icons), a sitemap, a robots file, feeds and
files for language models. It is meant for sites that live on GitHub Pages or any
plain file host. It installs from git; there is no PyPI release.

What a build writes:

- one `index.html` per page, with a complete head
- `sitemap.xml`, `robots.txt`, `404.html` and `.nojekyll`
- `favicon.ico`, `favicon.svg`, `apple-touch-icon.png`, `icon-192.png`,
  `icon-512.png` and `site.webmanifest`, made from one `favicon` source
- an Atom feed per collection named in `feeds`, as `<name>/feed.xml`
- with `llms = true`: `llms.txt`, `llms-full.txt` and an `index.md` next to every
  `index.html`
- the files of your `static/` folder, copied as they are

## Install and first run

```sh
uvx --from git+https://github.com/mojzis/deedum deedum guide
```

or, inside a uv project:

```sh
uv add git+https://github.com/mojzis/deedum
uv run deedum init
uv run deedum build --check
```

`deedum init` writes a config, a home page, a template override and a GitHub Pages
workflow. `deedum build` writes the site into `_site/`. `--check` lints it afterwards.

## The three ways in

### 1. Convention build

No Python of your own. A folder tree plus a config:

```text
deedum.toml
content/index.md          -> /
content/about.md          -> /about/
content/blog/hello.md     -> /blog/hello/
static/                   -> copied as they are
```

```toml
title = "My site"
base_url = "https://example.org"
```

```sh
uv run deedum build
```

Frontmatter (`title`, `description`, `date`, `updated`, `slug`, `draft`, `image`,
`noindex`, `lang`, `template`) is optional. Files and folders starting with `_` or `.`
are skipped.

### 2. An `App` subclass

Set `app = "module:Class"` in the config. The module is a Python file under the site
root. Override any of `load_pages`, `context`, `filters`, `globals` and `after_build`:

```python
import deedum


class MyApp(deedum.App):
    def load_pages(self):
        pages = super().load_pages()
        for person in self.data["people"]:
            pages.append(self.page(f"people/{person['slug']}/", title=person["name"]))
        return pages
```

The class runs as trusted code, then `uv run deedum build` works as before.

### 3. The Python API

Full control, no config file needed beyond the `Site` values:

```python
from pathlib import Path

import deedum

site = deedum.load_site(Path("."))
pages = deedum.load_pages(site)
builder = deedum.Builder(
    site,
    collections=deedum.build_collections(pages),
    data=deedum.load_data(site),
)
for page in pages:
    builder.render(page.template, page.url, page=page)
builder.copy_static()
report = builder.finish()
print(report.pages, report.extras)
print(deedum.head_tags(site, pages[0]))
```

`render` writes one page, `copy_static` copies the static folder, `finish` writes the
404 page, sitemap, robots file, icons, feeds and llms files. `head_tags` returns the
documented head tags for a page, to paste into a page you render yourself.

## `deedum extras`

A side door, not a fourth way in: `uv run deedum extras DIR` adds the sitemap, robots
file, icons and `.nojekyll` to a folder some other tool built. It never edits your
HTML and skips files that exist; `--overwrite` replaces them.

## Commands

- `deedum build [--out DIR] [--check]` builds the site and prints `pages`, `static` and `extras` lines
- `deedum check [DIR] [--strict]` lints built HTML: links, leftover template syntax, head metadata
- `deedum extras DIR [--overwrite]` adds sitemap, robots, icons to a folder
- `deedum init [DIR]` scaffolds config, home page, template override and Pages workflow
- `deedum new COLLECTION TITLE [--slug S]` creates `content/COLLECTION/<slug>.md` with today's date
- `deedum serve [--port N]` builds to temp folders, serves on `127.0.0.1` and rebuilds on change
- `deedum guide [setup|use|tune]` prints instructions for an agent about to use deedum

`build`, `check`, `extras`, `new` and `serve` take `--config FILE`; `build`, `check`
and `extras` also take `--base-url` and `--base-path`.

## Config reference

Keys live in `deedum.toml`, or in a `[tool.deedum]` table of `pyproject.toml` (not
both). An unknown key is an error with a suggestion.

| key | type | default | meaning |
| --- | --- | --- | --- |
| `title` | string | required | site title |
| `base_url` | string | required | `https://host[:port]`, no path |
| `base_path` | string | `/` | path prefix, for a project site such as `/repo/` |
| `description` | string | empty | default meta description |
| `lang` | string | `en` | default page language |
| `author` | string | empty | site author |
| `image` | string | empty | default social image, a path under `static/` |
| `favicon` | string | empty | square PNG (512 px or more) or SVG; makes the icon set |
| `theme_color` | string | `#ffffff` | `#rgb` or `#rrggbb`, for the web manifest |
| `twitter` | string | empty | handle for `twitter:site` |
| `analytics` | string | empty | Plausible domain; adds its script to every head |
| `head_extra` | string | empty | raw HTML added to every head (trusted) |
| `relative_links` | boolean | `false` | page-relative instead of root-relative links |
| `feeds` | array of strings | `[]` | collection names that get `<name>/feed.xml` |
| `llms` | boolean | `false` | write `llms.txt`, `llms-full.txt` and `index.md` siblings |
| `robots_extra_sitemaps` | array of strings | `[]` | more absolute sitemap URLs for `robots.txt` |
| `content` | string | `content` | markdown folder, relative to the config |
| `templates` | string | `templates` | template overrides folder |
| `static` | string | `static` | files copied as they are |
| `data` | string | `data` | yaml, toml or json files for templates |
| `out` | string | `_site` | output folder; the build clears it |
| `app` | string | empty | `module:Class` of a `deedum.App` subclass |
| `allow_tracked_out` | boolean | `false` | let the build clear an output folder that holds tracked files |

Precedence for `base_url` and `base_path`: the flag (`--base-url`, `--base-path`),
then `DEEDUM_BASE_URL` / `DEEDUM_BASE_PATH`, then the file. `base_url` must come from
one of the three.

## Templates

Lookup order: your `templates/` folder, then deedum's built-ins, then the built-ins
again under the `builtin/` prefix.

- built-ins: `deedum/head.html`, `deedum/base.html`, `deedum/favicon_links.html`,
  `page.html` and `404.html`
- a page in the collection `blog` uses `blog.html` when you have one, else `page.html`
- an override reaches the original through the prefix:
  `{% extends "builtin/deedum/head.html" %}`, then override a block such as `meta`
  and call `{{ super() }}`

Templates see `site`, `page`, `url()`, `absolute()`, `collections`, `data` and `now`.

## Notes

- Uppercase `.MD` and `.HTML` files are ignored: only lowercase suffixes count.
- Two outputs that claim the same path, or a file where another output needs a
  folder, fail the build and name both. The comparison is case-sensitive: `About/`
  and `about/` do not clash in deedum, but they do on a case-insensitive file system,
  so avoid names that differ only by case.
- `check` has errors and warnings. A broken link, a link outside the base path,
  leftover `{{` or `{%`, or a missing title or canonical is an error (exit 1). A
  missing description or `og:image` is a warning (exit 0); `--strict` makes warnings
  exit 1 too.
- `serve` rebuilds on any change inside the site root. A file written inside the root
  (say, the server's own log) triggers another rebuild and can loop: keep logs outside
  the root. A failed rebuild keeps serving the last good build; Ctrl-C stops it and
  removes its temp folders.

## The demo

[`examples/demo/`](examples/demo/) is a small site that uses every feature: a blog
with a feed, pages made from data by an `App`, a head override, a `new` template and
`llms.txt`. Try it from this repository:

```sh
uv run deedum build --config examples/demo/deedum.toml --check
uv run deedum check examples/demo/_site --config examples/demo/deedum.toml --strict
```
