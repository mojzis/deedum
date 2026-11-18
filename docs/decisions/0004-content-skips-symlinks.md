# 0004 Content loading skips symlinks

Date: 2026-11-18
Status: accepted

## Context

`load_pages` walks `content/` recursively. Following a symlink could read files from
outside the site, or loop.

## Decision

Content loading skips every symlink, file or folder. No error, no warning.

## Consequences

- A build can't be tricked into publishing files from outside the repo via content.
- A site that symlinks content in must copy it instead.
- Templates are different: they are the repo owner's code, so Jinja's default
  (symlinks followed) stays. See 0005.
