# 0001 Library plus convention CLI

Date: 2026-11-18
Status: accepted

## Context

The target repos differ: some have a Python build script with Jinja templates (aesop,
ottowww, podcast-template), some are owned by an SSG (orch, mkdocs and mdBook repos),
some are hand-written HTML (saints-calendar). The old `do.py` plan asked: a boilerplate
script per site, or a module whose `App` class a site subclasses?

## Decision

Both, in layers:

- A Python API (site config, pages, a builder, the head partial, extras writers) that a
  repo can call from its own build script.
- `deedum build`, which builds a site from folder conventions and a config file with no
  code in the target repo. A repo that needs code points the config at a `deedum.App`
  subclass and overrides hooks.
- `deedum extras`, which writes only the boring parts into a folder something else built.

## Consequences

- Every adopter can start where it is; nothing forces a rewrite.
- The convention build is a thin layer over the API, so the API must be enough for it.
- No plugin system in the first cut; an App subclass covers customisation.
