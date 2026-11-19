# 0012 `deedum extras` skips files that already exist

Date: 2026-11-19
Status: accepted

## Context

`deedum extras <dir>` writes into a folder that something else built. The folder may
already hold a hand-written `robots.txt` or a sitemap from another tool, and the user
may run the command again after a rebuild.

## Decision

- The targets are `sitemap.xml`, `robots.txt`, `.nojekyll`, every favicon output and
  `site.webmanifest`.
- A target that already exists is skipped and listed under `skipped`. `--overwrite`
  replaces it. A rerun therefore needs the flag; by default nothing is clobbered.
- A target that is a folder is always skipped and never deleted, even with
  `--overwrite`.
- `extras` never deletes and never edits an `.html` file. It refuses, with exit 2 and
  nothing written, when `<dir>` is a symlink or is in a `.git` folder, or when any
  target is a symlink (even with `--overwrite`).
- The favicon source is validated before the first write.

## Consequences

- Safe to run on a folder the user cares about; the cost is one flag to refresh files.
- The sitemap is not refreshed automatically after the HTML changes: rerun with
  `--overwrite`.
- `extras` scans only lowercase `*.html`; `.HTML` files are not listed in the sitemap.
