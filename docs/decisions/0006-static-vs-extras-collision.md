# 0006 A static file at an extra's output path fails the build

Date: 2026-11-18
Status: accepted

## Context

deedum writes four extras: `sitemap.xml`, `robots.txt`, `.nojekyll` and `404.html`.
A file in the static folder with one of those output paths would be silently
overwritten, or would overwrite the extra.

## Decision

The build fails with a `ContentError` naming both sides: the static source path and
the extra (`extra:robots`, ...). Same style as a static/page collision. The check
runs in `finish()`, before any extra is written.

## Consequences

- A site that wants its own `robots.txt` must say so explicitly; there is no opt-out
  in this phase.
- Static `CNAME` is not an extra and is never a collision.
