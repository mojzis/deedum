Configured here. Pick the way in that fits, take the first that applies.

1. **No Python of your own:** `uv run deedum build`. Folder conventions only.
   Add `--out DIR`, `--base-url URL`, `--base-path /p/`, `--config FILE` when needed.
2. **Pages from data, filters, a post-build step:** set `app = "module:Class"` in the
   config, where the class subclasses `deedum.App` and lives in a file under the site
   root. Override any of `load_pages`, `context`, `filters`, `globals`, `after_build`.
   `self.page("people/ann/", title="Ann")` builds a page for `load_pages` to return.
   Then run `uv run deedum build` as before.
3. **Full control:** the Python API. `deedum.load_site(Path("."))`,
   `deedum.Builder(site)`, `builder.render(template, path)`,
   `builder.copy_static()`, `builder.finish()`.
4. **A folder something else built:** `uv run deedum extras DIR` adds the sitemap,
   robots.txt, favicons and `.nojekyll`. It skips files that already exist; add
   `--overwrite` to replace them (after content changes, rerun with `--overwrite`).
   It never edits your HTML.

5. **Day to day:**
   - `uv run deedum new COLLECTION "Title"` creates `content/COLLECTION/<slug>.md`
     with the title and today's date. It refuses to overwrite. A template at
     `templates/new/COLLECTION.md` replaces the default body; it gets `title`, `date`,
     `slug` and `collection`, and should write the title as `{{ title | tojson }}`.
   - `uv run deedum serve [--port 8000]` builds into temp folders, serves
     `http://localhost:PORT` and rebuilds on every change. A broken edit prints
     `error:` and the last good build keeps being served. Ctrl-C stops it.
   - Any file written inside the site root (e.g. serve's own output redirected
     into the site folder) triggers a rebuild and can loop. Keep logs outside the root.
   - `uv run deedum check [DIR]` lints built HTML: broken links, links outside the
     base path, leftover `{{`/`{%`, a missing title or canonical are errors (exit 1);
     a missing description or og:image are warnings (exit 0, `--strict` makes them
     exit 1). `deedum build --check` runs it after the build.
   - `uv run deedum init` scaffolds a new site, including a GitHub Pages workflow.

Reading the result of `build`: three lines on stdout, `pages N`, `static N`,
`extras N: paths`. Errors go to stderr as `error: ...` with an optional `hint: ...`.

If it fails, fix the cause named in the message. A hook failure names the hook
(`app hook 'load_pages' ...`); fix that method.

Do not:

- retry with `--force-clear` to get past a tracked-files refusal unless the output
  folder is meant to be committed.
- delete `_site/` by hand to "fix" a build: the build clears it itself.
- pass `--strict` to make `check` pass: fix the warning (add a description or an
  `image`) instead.
- pass `--overwrite` to `extras` without reading what it lists as skipped.

Exit codes, every config key and the template names: `uv run deedum guide tune`.

next: `uv run deedum build`
