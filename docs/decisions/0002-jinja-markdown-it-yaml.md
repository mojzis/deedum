# 0002 Jinja2, markdown-it-py, YAML frontmatter

Date: 2026-11-18
Status: accepted

## Context

Every surveyed build uses Jinja2. ottowww uses markdown-it-py; the old `do.py` used
mistune with autoescape accidentally off.

## Decision

- Jinja2 with autoescape on and `StrictUndefined`.
- Template lookup: the target repo's template folder first, then deedum's built-ins.
  The target overrides any built-in by putting a file with the same name in its folder.
  deedum's built-ins live under a `deedum/` prefix (`deedum/head.html`, `deedum/base.html`).
- Markdown: markdown-it-py (CommonMark plus tables). Frontmatter: a leading `---` YAML
  block, parsed with PyYAML `safe_load`.

## Consequences

- Rendered markdown is marked safe once, in one place; templates never need `|safe` for it.
- A typo in a template variable fails the build instead of rendering empty.
