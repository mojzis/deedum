"""Atom 1.0 feeds, one per configured collection (R16, decision 0010)."""

from __future__ import annotations

import datetime as dt
import re
import xml.etree.ElementTree as ET
from collections.abc import Iterable
from pathlib import Path

from deedum.site import Page, Site

NAME = "feed.xml"
LIMIT = 20
_NS = "http://www.w3.org/2005/Atom"
_XML = "http://www.w3.org/XML/1998/namespace"
_NOT_FOUND = "404.html"
_FORBIDDEN = re.compile("[\x00-\x08\x0b\x0c\x0e-\x1f￾￿]")


def feed_path(name: str) -> str:
    """Site-relative output path of the feed for collection ``name``."""
    return f"{name}/{NAME}"


def rfc3339(value: dt.date) -> str:
    """UTC timestamp: a date is midnight, a naive datetime is taken as UTC."""
    if isinstance(value, dt.datetime):
        if value.tzinfo is not None:
            value = value.astimezone(dt.UTC)
        return value.replace(tzinfo=None).strftime("%Y-%m-%dT%H:%M:%SZ")
    return f"{value.isoformat()}T00:00:00Z"


def _clean(text: str) -> str:
    return _FORBIDDEN.sub("", text)


def page_stamp(page: Page) -> str:
    assert page.date is not None  # noqa: S101 -- callers filter on date
    return rfc3339(page.date)


def _entries(name: str, pages: Iterable[Page]) -> list[Page]:
    chosen = [
        p
        for p in pages
        if p.collection == name
        and p.date is not None
        and not p.noindex
        and p.output != _NOT_FOUND
    ]
    # newest first, ties by URL ascending
    chosen.sort(key=lambda p: p.url)
    chosen.sort(key=page_stamp, reverse=True)
    return chosen[:LIMIT]


def _text(parent: ET.Element, tag: str, text: str, **attrs: str) -> ET.Element:
    el = ET.SubElement(parent, f"{{{_NS}}}{tag}", attrs)
    el.text = _clean(text)
    return el


def _link(parent: ET.Element, rel: str, href: str) -> None:
    ET.SubElement(parent, f"{{{_NS}}}link", {"rel": rel, "href": _clean(href)})


def _add_entry(feed: ET.Element, site: Site, page: Page) -> str:
    assert page.date is not None  # noqa: S101 -- _entries filtered on date
    url = site.absolute(page.url)
    updated = rfc3339(page.updated or page.date)
    entry = ET.SubElement(feed, f"{{{_NS}}}entry")
    _text(entry, "id", url)
    _text(entry, "title", page.title)
    _link(entry, "alternate", url)
    _text(entry, "published", rfc3339(page.date))
    _text(entry, "updated", updated)
    if page.description:
        _text(entry, "summary", page.description)
    _text(entry, "content", str(page.body), type="html").set(
        f"{{{_XML}}}base", _clean(url)
    )
    return updated


def _build(
    site: Site, name: str, pages: Iterable[Page], now: dt.datetime
) -> ET.ElementTree:
    ET.register_namespace("", _NS)
    url = site.absolute(feed_path(name))
    feed = ET.Element(f"{{{_NS}}}feed")
    _text(feed, "id", url)
    _text(feed, "title", f"{site.title}: {name}")
    _link(feed, "self", url)
    _link(feed, "alternate", site.absolute(f"{name}/"))
    author = ET.SubElement(feed, f"{{{_NS}}}author")
    _text(author, "name", site.author or site.title)
    updated_el = _text(feed, "updated", "")
    # entries go last, so build them after the feed-level elements
    stamps = [_add_entry(feed, site, p) for p in _entries(name, pages)]
    updated_el.text = stamps[0] if stamps else rfc3339(now)
    return ET.ElementTree(feed)


def write_feeds(
    site: Site, pages: Iterable[Page], out: Path, now: dt.datetime
) -> list[Path]:
    """Write ``<name>/feed.xml`` for each configured feed into ``out``."""
    pages = list(pages)
    written = []
    for name in dict.fromkeys(site.feeds):
        path = out / feed_path(name)
        path.parent.mkdir(parents=True, exist_ok=True)
        _build(site, name, pages, now).write(
            path, encoding="utf-8", xml_declaration=True
        )
        written.append(path)
    return written
