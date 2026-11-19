Not wired in here yet. Three steps, in order.

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
