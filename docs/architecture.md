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
- **app**: `deedum.App`, the hooks the convention build calls, and `build()`.
- **foreign**: `write_extras`, the engine of `deedum extras <dir>`.
- **check**: `check_folder`, lints a built folder (links, leftover template syntax,
  head metadata); shares the HTML walk with `foreign`.
- **scaffold**: `init_site` and `new_entry`, the only writers into a user's source
  tree; exclusive create, never through a symlink.
- **serve**: builds into temp folders, serves the newest good build on `127.0.0.1`
  with stdlib `http.server`, rebuilds on `watchfiles` events.
- **cli**: typer router (`build`, `check`, `extras`, `init`, `new`, `serve`, `guide`);
  each command calls one function above. `deedum guide` prints the agent pages shipped
  in `deedum/guide/`.

## Flows

`deedum build`: config → `App.load_pages()` → `Builder.render` per page → copy static →
`finish()` (extras) → `App.after_build()` → optional check.

`deedum extras <dir>`: config → scan HTML in `<dir>` → sitemap, robots, favicons,
`.nojekyll`.

`deedum check [dir]`: config (optional with a dir) → walk `*.html` below the folder →
per page: links, leftover `{{`/`{%`, head metadata → findings, exit 1 on errors
(`--strict`: on warnings too). `deedum build --check` runs it on the build's output.

`deedum serve`: bind `127.0.0.1:<port>` → `load_site` with `base_url` localhost →
build into `deedum-serve-*` temp folder → serve it; on a `watchfiles` batch, rebuild
into a new folder and switch only on success (keep current and previous, delete the
rest and all on exit).
