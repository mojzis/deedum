# 0011 llms files

Date: 2026-11-19
Status: accepted

## Context

With `llms = true`, sites publish `llms.txt`, `llms-full.txt` and a markdown copy of
each page so language models can read the site without parsing HTML.

## Decision

- Listed pages are the recorded pages that are not `noindex` and not `404.html`.
  `noindex` pages appear in none of the files, not even as siblings.
- `llms.txt`: `# title`, then `> description` when there is one, then one `## ` group
  per collection. Root pages come first under `## Pages`, then collections sorted by
  name. Inside a group: the collection's own index page (`url == name + "/"`), then
  dated pages newest first, then undated pages by title. Lines are
  `- [Title](absolute URL): description`; the `: description` is left out when empty,
  `[`, `]` and `\` in titles are escaped and newlines in descriptions collapse to spaces.
- `llms-full.txt`: the same header, then every listed page with a non-empty `source`,
  in the same order. Each is a `---` line, a blank line, `URL: <absolute URL>`, a blank
  line and the raw source.
- `index.md` siblings are written for each listed page whose output ends in
  `index.html` and whose `source` is non-empty, holding the source verbatim. A page
  that renders to another `.html` file gets none, because there is no folder URL for
  an `index.md` to answer.
- `llms.txt` and `llms-full.txt` are UTF-8 with LF and a trailing newline. Siblings are
  the source bytes as they are.
- All of these are extras: a static file at any of the paths is a collision (0006),
  checked before anything is written.

## Consequences

- With `llms = false` none of the files exist.
- A page with no markdown source (a plain `render()` call) is listed in `llms.txt` but
  not in `llms-full.txt` and has no sibling.
