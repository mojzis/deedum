# Architecture

## Overview

A library with a thin CLI on top (decision 0001). The convention build (`deedum build`)
is a client of the same API a hand-written build script uses.

## Components

- **config**: reads `deedum.toml` / `[tool.deedum]`, applies env and flag overrides,
  validates. Produces a `Site`.
- **site**: `Site` (settings plus `url()` / `absolute()`), `Page`.
- **content**: loads `content/**/*.md` into pages (frontmatter, markdown, title and
  description fallbacks), collections, data files.
- **render**: the Jinja environment (target templates before built-ins) and the
  built-in templates under `deedum/templates/deedum/`.
- **builder**: `Builder(site, out)`: output safety, render, copy static, record pages,
  `finish()` writes the extras.
- **extras**: one module per output: sitemap, robots, favicons, feeds, llms, 404.
- **app**: `deedum.App`, the hooks the convention build calls.
- **check**: lints a built folder.
- **cli**: typer router; each command calls one function above.

## Flows

`deedum build`: config → `App.load_pages()` → `Builder.render` per page → copy static →
`finish()` (extras) → `App.after_build()` → optional check.

`deedum extras <dir>`: config → scan HTML in `<dir>` → sitemap, robots, favicons,
`.nojekyll`.
