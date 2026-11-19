from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest
from markupsafe import Markup
from PIL import Image

from deedum import ConfigError, Page, Site, head_tags
from deedum.foreign import _url, write_extras

SVG = (
    '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64">'
    '<rect width="64" height="64" fill="#cc3333"/></svg>'
)
PAGE = "<html><head><title>x</title></head><body>hi</body></html>"
LOC = "{http://www.sitemaps.org/schemas/sitemap/0.9}loc"
ICONS = [
    "favicon.ico",
    "favicon.svg",
    "apple-touch-icon.png",
    "icon-192.png",
    "icon-512.png",
    "site.webmanifest",
]


def put(path: Path, text: str | bytes = PAGE) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(text, bytes):
        path.write_bytes(text)
    else:
        path.write_text(text, encoding="utf-8")
    return path


def make_site(tmp_path: Path, favicon: str = "", **kw) -> Site:
    root = tmp_path / "cfg"
    root.mkdir(exist_ok=True)
    kw.setdefault("base_path", "/demo/")
    return Site(title="T", base_url="https://ex.test", favicon=favicon, root=root, **kw)


def svg_site(tmp_path: Path) -> Site:
    site = make_site(tmp_path, "icon.svg")
    put(site.root / "icon.svg", SVG)
    return site


def folder(tmp_path: Path) -> Path:
    return put(tmp_path / "foreign" / "index.html").parent


def names(root: Path) -> list[str]:
    return sorted(p.name for p in root.iterdir())


def locs(path: Path) -> list[str]:
    tree = ET.parse(path)  # noqa: S314 -- our own sitemap
    return [e.text or "" for e in tree.getroot().iter(LOC)]


def state(root: Path) -> dict[str, tuple[bytes, int]]:
    return {
        p.relative_to(root).as_posix(): (p.read_bytes(), p.stat().st_mtime_ns)
        for p in sorted(root.rglob("*"))
        if p.is_file()
    }


@pytest.mark.parametrize(
    ("rel", "url"),
    [
        ("index.html", ""),
        ("x/index.html", "x/"),
        ("a/b/index.html", "a/b/"),
        ("about.html", "about.html"),
        ("a/b.html", "a/b.html"),
    ],
)
def test_url_mapping(rel, url):
    assert _url(rel) == url


def test_sitemap_lists_indexable_pages_with_absolute_urls(tmp_path):
    root = folder(tmp_path)
    put(root / "a" / "index.html")
    put(root / "about.html")
    put(root / "404.html")
    put(root / "notes.txt", "not html")
    report = write_extras(make_site(tmp_path), root)
    assert report.pages == 3
    assert locs(root / "sitemap.xml") == [
        "https://ex.test/demo/",
        "https://ex.test/demo/a/",
        "https://ex.test/demo/about.html",
    ]
    assert "lastmod" not in (root / "sitemap.xml").read_text()


def test_nested_404_is_listed_but_root_404_is_not(tmp_path):
    root = folder(tmp_path)
    put(root / "404.html")
    put(root / "sub" / "404.html")
    write_extras(make_site(tmp_path), root)
    assert locs(root / "sitemap.xml") == [
        "https://ex.test/demo/",
        "https://ex.test/demo/sub/404.html",
    ]


@pytest.mark.parametrize(
    "meta",
    [
        '<meta name="robots" content="noindex">',
        '<meta name="robots" content="NOINDEX, follow">',
        '<META NAME="Robots" CONTENT="nofollow, noindex">',
        '<meta content="noindex" name="robots">',
        "<meta name='robots' content='noindex'/>",
    ],
)
def test_noindex_pages_are_left_out(tmp_path, meta):
    root = folder(tmp_path)
    put(root / "hidden.html", f"<html><head>{meta}</head><body></body></html>")
    write_extras(make_site(tmp_path), root)
    assert locs(root / "sitemap.xml") == ["https://ex.test/demo/"]


@pytest.mark.parametrize(
    "text",
    [
        '<meta name="robots" content="index, follow">',
        '<meta name="description" content="noindex">',
        '<meta name="robots">',
        '<meta content="noindex">',
        "<p>noindex</p>",
    ],
)
def test_other_meta_tags_do_not_hide_a_page(tmp_path, text):
    root = folder(tmp_path)
    put(root / "shown.html", f"<html><head>{text}</head></html>")
    write_extras(make_site(tmp_path), root)
    assert "https://ex.test/demo/shown.html" in locs(root / "sitemap.xml")


def test_html_without_head_and_noindex_in_body(tmp_path):
    root = folder(tmp_path)
    put(root / "bare.html", "<p>no head at all")
    put(root / "late.html", '<p>x</p><meta name="robots" content="noindex">')
    write_extras(make_site(tmp_path), root)
    assert locs(root / "sitemap.xml") == [
        "https://ex.test/demo/",
        "https://ex.test/demo/bare.html",
    ]


def test_non_utf8_html_never_fails_the_run(tmp_path):
    root = folder(tmp_path)
    put(root / "latin.html", b"<html><head><title>caf\xe9</title></head></html>")
    put(
        root / "bad-noindex.html",
        b'<meta name="robots" content="noindex"><p>\xff\xfe',
    )
    report = write_extras(make_site(tmp_path), root)
    assert report.pages == 2
    assert "https://ex.test/demo/latin.html" in locs(root / "sitemap.xml")


def test_symlinks_and_dot_folders_are_not_scanned(tmp_path):
    root = folder(tmp_path)
    outside = tmp_path / "outside"
    put(outside / "leak.html")
    put(outside / "deep" / "leak2.html")
    (root / "link.html").symlink_to(outside / "leak.html")
    (root / "linkdir").symlink_to(outside, target_is_directory=True)
    put(root / ".hidden" / "x.html")
    put(root / "ok" / ".more" / "y.html")
    write_extras(make_site(tmp_path), root)
    assert locs(root / "sitemap.xml") == ["https://ex.test/demo/"]


def test_writes_robots_nojekyll_and_icons(tmp_path):
    root = folder(tmp_path)
    report = write_extras(svg_site(tmp_path), root)
    assert (report.written, report.skipped) == (
        ["sitemap.xml", "robots.txt", ".nojekyll", *ICONS],
        [],
    )
    robots = (root / "robots.txt").read_text()
    assert "Sitemap: https://ex.test/demo/sitemap.xml" in robots
    assert (root / ".nojekyll").read_bytes() == b""
    assert all((root / name).is_file() for name in ICONS)


def test_no_favicon_means_no_icons_and_no_links(tmp_path):
    root = folder(tmp_path)
    report = write_extras(make_site(tmp_path), root)
    assert report.written == ["sitemap.xml", "robots.txt", ".nojekyll"]
    assert report.links == ""
    assert not (root / "favicon.ico").exists()


def test_existing_files_are_unchanged(tmp_path):
    root = folder(tmp_path)
    put(root / "a" / "index.html", "<p>mine</p>")
    put(root / "style.css", "body{}")
    before = state(root)
    write_extras(svg_site(tmp_path), root)
    after = state(root)
    assert {k: after[k] for k in before} == before


def test_existing_targets_are_skipped_then_overwritten(tmp_path):
    root = folder(tmp_path)
    put(root / "sitemap.xml", "MINE")
    put(root / "favicon.ico", "ICO")
    site = svg_site(tmp_path)
    plain = write_extras(site, root)
    assert plain.skipped == ["sitemap.xml", "favicon.ico"]
    assert "sitemap.xml" not in plain.written
    assert [(root / n).read_text() for n in plain.skipped] == ["MINE", "ICO"]


def test_overwrite_replaces_existing_targets(tmp_path):
    root = folder(tmp_path)
    put(root / "sitemap.xml", "MINE")
    put(root / "favicon.ico", "ICO")
    forced = write_extras(svg_site(tmp_path), root, overwrite=True)
    assert forced.skipped == []
    assert locs(root / "sitemap.xml") == ["https://ex.test/demo/"]
    assert (root / "favicon.ico").read_bytes()[:4] == b"\x00\x00\x01\x00"


def test_rerun_skips_everything_and_overwrite_is_byte_identical(tmp_path):
    root = folder(tmp_path)
    site = svg_site(tmp_path)
    first = write_extras(site, root)
    snap = state(root)
    again = write_extras(site, root)
    assert (again.written, again.skipped) == ([], first.written)
    assert state(root) == snap
    write_extras(site, root, overwrite=True)
    assert {k: v[0] for k, v in state(root).items()} == {
        k: v[0] for k, v in snap.items()
    }


def test_a_target_that_is_a_folder_is_skipped_and_kept(tmp_path):
    root = folder(tmp_path)
    put(root / "robots.txt" / "keep.txt", "keep")
    put(root / "icon-192.png" / "keep.txt", "keep")
    site = svg_site(tmp_path)
    report = write_extras(site, root, overwrite=True)
    assert report.skipped == ["robots.txt", "icon-192.png"]
    assert (root / "robots.txt" / "keep.txt").read_text() == "keep"
    assert (root / "icon-192.png" / "keep.txt").read_text() == "keep"
    assert (root / "icon-512.png").is_file()


def test_symlinked_target_is_refused_even_with_overwrite(tmp_path):
    root = folder(tmp_path)
    victim = put(tmp_path / "victim.txt", "victim")
    (root / "robots.txt").symlink_to(victim)
    before = names(root)
    with pytest.raises(ConfigError, match=r"symlink") as err:
        write_extras(make_site(tmp_path), root, overwrite=True)
    assert "robots.txt" in str(err.value)
    assert victim.read_text() == "victim"
    assert names(root) == before


def test_dangling_symlink_target_is_refused(tmp_path):
    root = folder(tmp_path)
    (root / "sitemap.xml").symlink_to(tmp_path / "nowhere.xml")
    with pytest.raises(ConfigError, match="symlink"):
        write_extras(make_site(tmp_path), root)
    assert not (tmp_path / "nowhere.xml").exists()


def test_symlinked_favicon_target_is_refused(tmp_path):
    root = folder(tmp_path)
    victim = put(tmp_path / "victim.png", "victim")
    (root / "icon-512.png").symlink_to(victim)
    with pytest.raises(ConfigError, match=r"icon-512\.png"):
        write_extras(svg_site(tmp_path), root)
    assert not (root / "sitemap.xml").exists()
    assert victim.read_text() == "victim"


def test_symlinked_folder_is_refused(tmp_path):
    real = folder(tmp_path)
    link = tmp_path / "link"
    link.symlink_to(real, target_is_directory=True)
    with pytest.raises(ConfigError, match="symlink"):
        write_extras(make_site(tmp_path), link)
    assert not (real / "sitemap.xml").exists()


@pytest.mark.parametrize("sub", [".git", ".git/hooks", "x/.git/y"])
def test_git_folders_are_refused(tmp_path, sub):
    target = tmp_path / sub
    target.mkdir(parents=True)
    with pytest.raises(ConfigError, match=r"\.git"):
        write_extras(make_site(tmp_path), target)
    assert not list(target.iterdir())


@pytest.mark.parametrize("kind", ["missing", "file"])
def test_missing_or_non_folder_is_refused(tmp_path, kind):
    target = tmp_path / "nope"
    put(tmp_path / "file", "text")
    target = tmp_path / ("nope" if kind == "missing" else "file")
    with pytest.raises(ConfigError) as err:
        write_extras(make_site(tmp_path), target)
    assert str(target) in str(err.value)


def test_invalid_favicon_writes_nothing(tmp_path):
    root = folder(tmp_path)
    site = make_site(tmp_path, "small.png")
    Image.new("RGB", (100, 100)).save(site.root / "small.png")
    before = state(root)
    with pytest.raises(ConfigError, match="favicon"):
        write_extras(site, root)
    assert state(root) == before
    assert names(root) == ["index.html"]


def head_icon_lines(site: Site) -> str:
    page = Page(
        url="",
        output="index.html",
        title="T",
        description="",
        body=Markup(""),
        source="",
        template="page.html",
    )
    html = head_tags(site, page)
    keep = [ln for ln in html.splitlines() if re.search(r"icon|manifest", ln)]
    return "\n".join(keep)


def test_links_match_the_head_partial_for_svg(tmp_path):
    site = svg_site(tmp_path)
    links = write_extras(site, folder(tmp_path)).links
    assert links == head_icon_lines(site)
    assert '<link rel="icon" href="/demo/favicon.ico" sizes="32x32">' in links
    assert 'href="/demo/favicon.svg" type="image/svg+xml"' in links


def test_links_match_the_head_partial_for_png(tmp_path):
    site = make_site(tmp_path, "icon.png")
    Image.new("RGB", (512, 512)).save(site.root / "icon.png")
    links = write_extras(site, folder(tmp_path)).links
    assert links == head_icon_lines(site)
    assert "favicon.svg" not in links
    assert 'rel="manifest" href="/demo/site.webmanifest"' in links


def test_relative_links_extras_print_root_relative_favicon_links(tmp_path):
    site = make_site(tmp_path, "icon.svg", relative_links=True)
    put(site.root / "icon.svg", SVG)
    report = write_extras(site, folder(tmp_path))
    assert 'href="/demo/favicon.ico"' in report.links
    assert 'href="favicon.ico"' not in report.links


def test_upper_case_html_is_not_scanned(tmp_path):
    root = folder(tmp_path)
    put(root / "PAGE.HTML")
    write_extras(make_site(tmp_path), root)
    assert not any("PAGE" in loc for loc in locs(root / "sitemap.xml"))
