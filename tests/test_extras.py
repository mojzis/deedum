from __future__ import annotations

import datetime as dt
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest
from markupsafe import Markup

from deedum import Page, Site, make_env
from deedum.extras import render_404, write_nojekyll, write_robots, write_sitemap

NS = "{http://www.sitemaps.org/schemas/sitemap/0.9}"
XH = "{http://www.w3.org/1999/xhtml}"
BASE = "https://ex.org"


def site_of(tmp_path: Path, **kw) -> Site:
    kw.setdefault("base_path", "/b/")
    return Site(title="T", base_url=BASE, root=tmp_path, **kw)


def page(url: str, **kw) -> Page:
    kw.setdefault("output", url + "index.html" if url.endswith("/") else url)
    return Page(
        url=url,
        title="t",
        description="",
        body=Markup(""),
        source="",
        template="page.html",
        **kw,
    )


def sitemap(tmp_path: Path, pages: list[Page], **kw) -> tuple[str, ET.Element]:
    write_sitemap(site_of(tmp_path, **kw), pages, tmp_path)
    text = (tmp_path / "sitemap.xml").read_text(encoding="utf-8")
    return text, ET.fromstring(text)  # noqa: S314 -- our own output


def locs(root: ET.Element) -> list[str]:
    return [e.text or "" for e in root.iter(f"{NS}loc")]


def test_sitemap_sorted_and_namespaced(tmp_path):
    text, root = sitemap(tmp_path, [page("b/"), page(""), page("a/")])
    assert root.tag == f"{NS}urlset"
    assert text.startswith("<?xml")
    assert locs(root) == [f"{BASE}/b/", f"{BASE}/b/a/", f"{BASE}/b/b/"]
    assert "xhtml" not in text


def test_sitemap_skips_noindex_and_404(tmp_path):
    pages = [page("a/"), page("s/", noindex=True), page("404.html")]
    _, root = sitemap(tmp_path, pages)
    assert locs(root) == [f"{BASE}/b/a/"]


def test_sitemap_lastmod_precedence(tmp_path):
    pages = [
        page("a/", date=dt.date(2024, 5, 1), updated=dt.date(2024, 6, 1)),
        page("b/", date=dt.date(2024, 5, 1)),
        page("c/"),
    ]
    pages.append(page("d/", updated=dt.datetime(2024, 7, 2, 23, 59, tzinfo=dt.UTC)))
    _, root = sitemap(tmp_path, pages)
    mods = [[m.text for m in u.iter(f"{NS}lastmod")] for u in root]
    assert mods == [["2024-06-01"], ["2024-05-01"], [], ["2024-07-02"]]


def test_sitemap_alternates_with_self_entry(tmp_path):
    alt = page("en/", lang="en", alternates={"cs": "cs/"})
    text, root = sitemap(tmp_path, [alt])
    links = [
        (e.get("hreflang"), e.get("href"), e.get("rel")) for e in root.iter(f"{XH}link")
    ]
    assert links == [
        ("cs", f"{BASE}/b/cs/", "alternate"),
        ("en", f"{BASE}/b/en/", "alternate"),
    ]
    assert "xmlns:xhtml=" in text


def test_sitemap_alternates_keep_listed_self(tmp_path):
    alt = page("en/", lang="en", alternates={"en": "en/", "cs": "cs/"})
    _, root = sitemap(tmp_path, [alt])
    assert [e.get("hreflang") for e in root.iter(f"{XH}link")] == ["cs", "en"]


def test_sitemap_escapes_ampersand(tmp_path):
    text, root = sitemap(tmp_path, [page("a/?x=1&y=2")])
    assert "&amp;" in text
    assert locs(root) == [f"{BASE}/b/a/?x=1&y=2"]


def test_robots_exact(tmp_path):
    write_robots(site_of(tmp_path), tmp_path)
    expected = f"User-agent: *\nAllow: /\n\nSitemap: {BASE}/b/sitemap.xml\n"
    assert (tmp_path / "robots.txt").read_bytes() == expected.encode()


def test_robots_extra_sitemaps(tmp_path):
    extra = (f"{BASE}/x/sitemap.xml", f"{BASE}/y/sitemap.xml")
    write_robots(site_of(tmp_path, robots_extra_sitemaps=extra), tmp_path)
    lines = (tmp_path / "robots.txt").read_text().splitlines()
    assert lines[3:] == [
        f"Sitemap: {BASE}/b/sitemap.xml",
        f"Sitemap: {extra[0]}",
        f"Sitemap: {extra[1]}",
    ]


def test_nojekyll_is_empty(tmp_path):
    path = write_nojekyll(tmp_path)
    assert path.name == ".nojekyll"
    assert path.read_bytes() == b""


@pytest.mark.parametrize("relative", [False, True])
def test_404_builtin_root_relative_noindex(tmp_path, relative):
    site = site_of(tmp_path, relative_links=relative)
    path = render_404(make_env(site), site, tmp_path)
    html = path.read_text(encoding="utf-8")
    assert path.name == "404.html"
    assert '<meta name="robots" content="noindex">' in html
    assert 'href="/b/"' in html
    assert 'href="./"' not in html


def test_404_target_template_wins(tmp_path):
    (tmp_path / "templates").mkdir()
    (tmp_path / "templates" / "404.html").write_text("custom {{ page.title }}")
    site = site_of(tmp_path)
    html = render_404(make_env(site), site, tmp_path).read_text()
    assert html == "custom Page not found"
