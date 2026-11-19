# 0005 Template lookup and the `builtin/` prefix

Date: 2026-11-18
Status: accepted

## Context

Sites must render with no templates of their own, yet be able to replace any
built-in. An override of `deedum/head.html` that extends `deedum/head.html` would
recurse into itself.

## Decision

- Lookup order: the target's `templates/` folder, then the built-ins shipped in
  `deedum/templates/`, then the same built-ins under the `builtin/` prefix.
- An override extends the original as `{% extends "builtin/deedum/head.html" %}`.
- `deedum.head_tags(site, page)` renders the built-in head with built-ins only, so it
  is the documented head whatever the target overrides.
- `url()` is a context function bound from the context's `page`, so
  `relative_links` works with one environment for all pages. `page` is passed per
  render, not a global.
- Autoescape is on for every template, undefined names raise, and any Jinja error is
  wrapped in `RenderError` naming the template, the page and the line.
- No sandbox: target templates are trusted code. `site.head_extra` is the only raw
  output besides the markdown body.

## Consequences

- Overrides can replace or extend one head block (`meta`, `social`, `links`,
  `robots`, `scripts`).
- The `builtin/` name is reserved.
