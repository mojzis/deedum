# 0015 `deedum serve` builds to temp folders

Date: 2026-11-19
Status: accepted

## Context

`serve` rebuilds on every change. Building into the configured `out` folder would
clear it each time, could clobber a tracked folder, and would leave a half-written
site visible while a build is running or after it fails.

## Decision

- Each build goes into a fresh folder made with
  `tempfile.mkdtemp(prefix="deedum-serve-")`, outside the repo.
- The server switches to a build only after it succeeds. A failed rebuild prints
  `error:` (and `hint:`) on stderr and the previous build keeps being served.
- It keeps the current and the previous build; older ones are deleted, and all of
  them on exit. It deletes only folders it made, tracked by path, never by glob.
- Serve never reads or writes the configured `out` folder; changes under it are
  ignored by the watcher.
- It builds with `base_url = http://localhost:<bound port>`, binds `127.0.0.1` only,
  and serves only files that resolve inside the current build folder.

## Consequences

- `serve` never needs `--force-clear`, and a crash leaves the repo as it was.
- A hard kill (SIGKILL, power loss) can leave `deedum-serve-*` folders in the temp
  dir; Ctrl-C (SIGINT) cleans up, SIGTERM does not.
- Output is identical to a normal build apart from `base_url`.
