"""sitemap.xml with optional hreflang alternates (R13)."""

from __future__ import annotations

import datetime as dt
import xml.etree.ElementTree as ET
from collections.abc import Iterable
from pathlib import Path

from deedum.site import Page, Site

NAME = "sitemap.xml"
_NS = "http://www.sitemaps.org/schemas/sitemap/0.9"
_XHTML = "http://www.w3.org/1999/xhtml"
_NOT_FOUND = "404.html"


def _lastmod(page: Page) -> str:
    value = page.updated or page.date
    if value is None:
        return ""
    if isinstance(value, dt.datetime):
        value = value.date()
    return value.isoformat()


def _alternates(site: Site, page: Page) -> dict[str, str]:
    """Language -> absolute URL, including the page itself when it has any."""
    if not page.alternates:
        return {}
    langs = {lang: site.absolute(path) for lang, path in page.alternates.items()}
    langs.setdefault(page.lang, site.absolute(page.url))
    return dict(sorted(langs.items()))


def write_sitemap(site: Site, pages: Iterable[Page], out: Path) -> Path:
    """Write ``sitemap.xml`` for the indexable pages into ``out``."""
    ET.register_namespace("", _NS)
    ET.register_namespace("xhtml", _XHTML)
    entries = sorted(
        (
            (site.absolute(p.url), p)
            for p in pages
            if not p.noindex and p.output != _NOT_FOUND
        ),
        key=lambda e: e[0],
    )
    root = ET.Element(f"{{{_NS}}}urlset")
    for loc, page in entries:
        url = ET.SubElement(root, f"{{{_NS}}}url")
        ET.SubElement(url, f"{{{_NS}}}loc").text = loc
        if lastmod := _lastmod(page):
            ET.SubElement(url, f"{{{_NS}}}lastmod").text = lastmod
        for lang, href in _alternates(site, page).items():
            ET.SubElement(
                url,
                f"{{{_XHTML}}}link",
                {"rel": "alternate", "hreflang": lang, "href": href},
            )
    path = out / NAME
    ET.ElementTree(root).write(path, encoding="utf-8", xml_declaration=True)
    return path
