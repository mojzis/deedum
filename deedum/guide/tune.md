Reference. Never auto-selected.

## Config keys

In `deedum.toml`, or `[tool.deedum]` in `pyproject.toml` (not both).
Precedence: flag, then `DEEDUM_BASE_URL` / `DEEDUM_BASE_PATH`, then the file.

| key | meaning |
| --- | --- |
| `title` | site title, required |
| `base_url` | `https://host[:port]`, required |
| `base_path` | path prefix, `/` by default |
| `description` | default meta description |
| `lang` | default language, `en` |
| `author` | site author |
| `image` | default social image, a path under `static/` |
| `favicon` | square PNG (512 px or more) or SVG; makes the icon set |
| `theme_color` | `#rgb` or `#rrggbb`, for the web manifest |
| `twitter` | handle for twitter:site |
| `analytics` | Plausible domain |
| `head_extra` | raw HTML added to every head (trusted) |
| `relative_links` | page-relative links, true or false |
| `feeds` | collection names that get `<name>/feed.xml` |
| `llms` | write `llms.txt`, `llms-full.txt` and `index.md` siblings |
| `robots_extra_sitemaps` | more absolute sitemap URLs for robots.txt |
| `content`, `templates`, `static`, `data` | folder names, relative to the config |
| `out` | output folder, `_site` |
| `app` | `module:Class` of a `deedum.App` subclass |
| `allow_tracked_out` | let the build clear an output folder holding tracked files |

## Exit codes

- 0: ok
- 1: content, render or app-hook failure
- 2: config error: bad config, bad `app`, a refused output or extras folder
- 130: interrupted

stderr carries `error: <what>` and `hint: <what to do>`.

## Template names

Lookup order: the site's `templates/`, then the built-ins, then the built-ins under
the `builtin/` prefix.

- built-ins: `deedum/head.html`, `deedum/base.html`, `deedum/favicon_links.html`,
  `page.html`, `404.html`
- `<collection>.html` is the default template for pages in that collection
- an override extends the original as `{% extends "builtin/deedum/head.html" %}`

## Safety

- Loading `app` runs that Python file: it is trusted code.
- `build` refuses `.git`, symlinks, the home folder, the site root and source folders.
- `extras` refuses a symlinked or `.git` folder and any symlinked target.

next: `uv run deedum build`
