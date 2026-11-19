# 0016 The demo is the bar; the README installs from git

Date: 2026-11-19
Status: accepted

## Context

deedum needs a worked example and a README that stands alone. Both must stay true as
the code changes, and the pitch rules out a PyPI release.

## Decision

- `examples/demo/` uses every feature (all five `App` hooks, a feed, llms files, a
  head override, a `new` template, an `icon.svg` favicon, a site `image`). The bar for
  it is `deedum check --strict` with zero findings, not only zero errors.
- Tests build the demo into a temp folder with a frozen `now` and never write into
  `examples/`. The build output folder `examples/demo/_site/` is gitignored.
- The favicon source `icon.svg` sits next to the config, not in `static/`, because a
  static `favicon.svg` collides with the generated one (decision 0009).
- The README installs from git (`uvx --from git+https://github.com/mojzis/deedum` or
  `uv add git+...`), never from PyPI. `deedum@latest` would fetch nothing, or a
  stranger's package.
- A test fails when a config key in `deedum.config._KNOWN` has no README row, and the
  README's Python API example is executed by a test.

## Consequences

- A change that adds a warning to a demo page, or a config key without a README row,
  fails the suite.
- The demo posts include hostile content (a 200-character URL, a wide code block and
  table) so layout regressions show up in a browser check.
- If a PyPI release is ever made, the README install lines and `scaffold.py` change
  together.
