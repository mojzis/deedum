# 0007 Refuse to clear an output folder that holds tracked files

Date: 2026-11-18
Status: accepted

## Context

The builder clears the output folder on every build. A repo that tracks its output
(or points `out` at a folder with committed files) would lose them.

## Decision

Before clearing, run `git ls-files` inside the output folder, i.e. in the repo containing the output folder (not necessarily the site's repo). If any
file is tracked, refuse, change nothing, and name up to 5 files plus the total. Outside
a git repo, or without `git` on PATH, the check is skipped silently.

Opt in for repos that commit their output: config key `allow_tracked_out = true`, or
`Builder(..., force_clear=True)` (the future `--force-clear` flag). Neither bypasses the
refusals for dangerous folders (home, site root, source folders, symlinks).

## Consequences

- One `git` subprocess per build when the output folder exists.
- A repo publishing from a committed folder must set the key once.
