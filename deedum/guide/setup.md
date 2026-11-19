Not wired in here yet. Quickest: `uv add deedum`, then `uv run deedum init`. It writes
the config, a home page, a template override example, an empty `static/` and a GitHub
Pages workflow, and never overwrites anything. Or do it by hand, three steps in order.

1. Add the dependency: `uv add deedum`.
2. Create `deedum.toml` next to your content, with the two keys that matter:

   ```toml
   title = "My site"
   base_url = "https://example.github.io"
   base_path = "/my-repo/"   # only for a project site
   ```

3. Put markdown in `content/` (`content/index.md` is the home page,
   `content/blog/first.md` becomes `/blog/first/`). Optional folders next to it:
   `templates/`, `static/` (copied as is), `data/` (yaml, toml or json).

Build:

```
uv run deedum build
```

See it live with `uv run deedum serve` (rebuilds on every save). Lint the result with
`uv run deedum check`, or build and lint in one go with `uv run deedum build --check`.
Add a post with `uv run deedum new blog "My first post"`.

Done looks like exit 0, stdout of exactly three lines (`pages N`, `static N`,
`extras N: ...`) and the site in `_site/`. Nothing on stderr.

Already have a folder of HTML built by something else? Skip all of the above:

```
uv run deedum extras path/to/folder --base-url https://example.github.io
```

Do not:

- point `--out` at a folder you care about: the build clears it.
- edit files in `_site/`: the next build deletes them.
- commit `_site/` unless `allow_tracked_out = true` is set.

Every config key is listed by `uv run deedum guide tune`.

next: `uv run deedum build`
