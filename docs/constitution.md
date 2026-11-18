---
title: deedum
pitch: Static HTML for small sites. The target repo brings content and templates; deedum handles the boring parts (head tags, favicons, sitemaps, robots, feeds, llms.txt).
created: 2026-11-18
updated: 2026-11-18
---

# deedum

## Purpose

Several small sites are built by their own short Python scripts, and every one of them
handles the boring parts differently: Open Graph and Twitter tags, canonical URLs,
favicons, sitemaps, robots.txt, feeds, llms.txt, `.nojekyll`, 404 pages. None has all of
them, and the same build skeleton is copied between repos
([research](research/existing-site-builds.md)). deedum does those parts once, well, and
leaves the look and the content to the site.

## Goals

- A site gets correct head tags, favicons, sitemap, robots and feed without thinking
  about them.
- The target repo owns its templates and content. It can override any template deedum
  ships, including the head.
- Three ways in, from least to most code in the target repo:
  1. `deedum build` from folder conventions and a small config file.
  2. A `deedum.App` subclass in the target repo that overrides a few hooks.
  3. A plain Python API for repos that keep their own build script.
- `deedum extras` adds the boring parts to a folder built by something else (an SSG or
  hand-written HTML).
- Small enough to read in one sitting, like the old `do.py`.

## Non-goals

- A general-purpose static site generator with themes and a plugin ecosystem.
- Deployment. Sites keep their GitHub Pages workflow.
- Asset pipelines: bundling, minifying, hashing.
- Fetching anything from the network at build time.

## Principles

- Conventions first, config second, code third.
- Every URL that leaves the site (canonical, OG, sitemap, feed) is absolute.
- Safe by default: autoescape on, undefined variables fail the build, the output folder
  is never something that holds sources.
- A build needs no network and no system libraries beyond what wheels bring.
- Fail with a message that names the file and the key.

## Open questions

- Plugins (Plausible, link previews, notebooks, deploy) after the first cut: entry
  points, or plain App subclasses?
- deedum's own documentation site, built with deedum.
