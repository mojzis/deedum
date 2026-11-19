# 0014 How the `init` Pages workflow installs deedum

Date: 2026-11-19
Status: accepted

## Context

`deedum init` writes a GitHub Pages workflow that builds the site in CI. The runner
has no deedum, and the target folder may or may not be a Python project.

## Decision

- **The target folder has a `pyproject.toml`:** the workflow runs `uv sync`, then
  `uv run deedum build --check`. `init` prints `hint: run uv add deedum` unless
  `deedum` already appears in `[project].dependencies`.
- **No `pyproject.toml`:** the workflow runs
  `uvx --from git+https://github.com/mojzis/deedum deedum build --check`.
- The workflow builds with `--check`, so a broken link fails the deploy.
- Actions are pinned to the newest release found with `gh release view`, using the
  major tag when it exists (`actions/checkout@v7`, `actions/upload-pages-artifact@v5`,
  `actions/deploy-pages@v5`) and the full version when it doesn't
  (`astral-sh/setup-uv@v10.3.3`).
- The workflow uploads the `out` of an existing `deedum.toml` or `[tool.deedum]` (raw value, so a placeholder `base_url` is fine), default `_site`; an unreadable config exits 2 before any write, and an absolute or `..` `out` keeps `_site` with a hint.
- `init` never overwrites: an existing workflow is skipped and listed.

## Consequences

- A project repo gets its locked deedum version in CI; a plain content repo always
  gets deedum's default branch, so its build can change under it.
- The workflow's action pins age; refresh them when `init` is next touched.
