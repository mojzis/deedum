# 0010 Atom feeds

Date: 2026-11-19
Status: accepted

## Context

`site.feeds` names collections that get a feed. The head already links
`<name>/feed.xml`. The Python API (R12) lets a caller render pages without the
convention build, so feeds must not depend on a loaded collections mapping.

## Decision

- Entries come from the pages the Builder **recorded** (`.html` renders), not from the
  `collections` argument. A page is in feed `name` when `page.collection == name`, it
  has a `date`, is not `noindex` and is not `404.html`.
- Newest 20 by date, descending, ties by URL ascending.
- Atom 1.0 built with ElementTree, UTF-8 with an XML declaration. Each entry has an
  absolute `id` and `link`, `published`, `updated` (`updated` or `date`), an optional
  `summary` and the full HTML body as `content type="html"` with `xml:base` set to the
  absolute page URL, so relative links in the body resolve.
- Timestamps are RFC 3339 UTC: a date is midnight, a naive datetime is taken as UTC,
  an aware one is converted.
- The feed's `updated` is the newest entry's `updated`. A configured feed with no
  qualifying pages is still written, as a valid feed with no entries whose `updated` is
  the Builder's `now`. That is the only place build time appears in output. The Builder
  takes `now` once and reuses it.
- Characters XML 1.0 forbids (C0 controls except tab, LF, CR) are stripped from all
  text and attribute values, so the file always parses.
- Feed names are validated in `Site`: one path segment matching
  `[A-Za-z0-9_-][A-Za-z0-9._-]*`. That stops `../x`, `a/b`, `.git` and the empty name
  before they become paths. Duplicate names produce one file.

## Consequences

- Undated pages never appear in a feed; give posts a `date`.
- Two builds with the same inputs and the same `now` are byte-identical.
- A site that wants a feed must put its posts in a collection of that name.
