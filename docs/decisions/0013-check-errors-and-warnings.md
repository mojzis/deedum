# 0013 `deedum check`: what is an error and what is a warning

Date: 2026-11-19
Status: accepted

## Context

`deedum check` lints a built folder, and `deedum build --check` runs it after a
build. A linter that fails on everything gets switched off; one that fails on
nothing gets ignored.

## Decision

- **Errors** (exit 1):
  - a broken internal link or asset;
  - a link outside the base path;
  - leftover `{{` or `{%` outside `code`, `pre`, `script`, `style` and `textarea`;
  - a missing or empty `<title>`;
  - a missing canonical link.
- **Warnings** (printed, exit 0): a missing meta description, a missing `og:image`.
- `deedum check --strict` makes warnings exit 1 too. `build --check` has no
  `--strict`: warnings never fail a build.
- Metadata rules (title, canonical, description, og:image) apply only to indexable
  pages, i.e. pages without a robots noindex meta. Link and leftover-syntax rules
  apply to every page, the 404 page included.
- Absolute URLs that point at the site's own origin are not checked.
- `check DIR` with no config uses `--base-path` or `/` and ignores `DEEDUM_BASE_PATH`; with a config, env and flags apply as in `build`.
- The page count includes `404.html`: it is linted for links but exempt from metadata rules.

## Consequences

- A fresh `init` site passes `check` and fails `check --strict` only for `og:image`.
- A page that is noindex on purpose is never nagged about metadata.
- Own-origin absolute links can rot unnoticed until a later phase resolves them.
