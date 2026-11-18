# 0003 Config file and URL model

Date: 2026-11-18
Status: accepted

## Context

Sites are served from GitHub Pages under a path (`https://mojzis.github.io/aesop/`).
The surveyed repos use three URL styles: a full base URL prefix (aesop), base URL plus
base path (ottowww), and relative `root` prefixes (podcast-template, changelog).
Canonical, Open Graph, sitemap and feed URLs must be absolute.

## Decision

- Config lives in `deedum.toml` at the target repo root, or in `[tool.deedum]` of its
  `pyproject.toml` when there is no `deedum.toml`. Not both.
- The URL model is ottowww's: `base_url` (scheme and host, e.g.
  `https://mojzis.github.io`) plus `base_path` (e.g. `/aesop/`). `url(path)` gives a
  root-relative link with the base path; `absolute(path)` gives the full URL.
- `DEEDUM_BASE_URL` / `DEEDUM_BASE_PATH` env vars and `--base-url` / `--base-path` flags
  override the config, flags winning, so a fork or a local preview builds without edits.
- Optional `relative_links = true`: `url()` returns links relative to the page being
  rendered. Absolute URLs (canonical, OG, sitemap, feed) stay absolute.

## Consequences

- One model covers all three styles.
- A site with relative links still needs `base_url` for its absolute URLs.
