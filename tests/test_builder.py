from __future__ import annotations

import datetime as dt
import filecmp
import hashlib
import re
import shutil
import subprocess
from pathlib import Path

import pytest
from markupsafe import Markup
from PIL import Image

import deedum.builder as builder_mod
from deedum import (
    Builder,
    BuildReport,
    ConfigError,
    ContentError,
    DeedumError,
    Page,
    RenderError,
    Site,
)

BASE = "https://ex.org"
ABOUT = "about/"


def make_site(tmp_path: Path, **kw) -> Site:
    kw.setdefault("base_path", "/b/")
    root = tmp_path / "site"
    root.mkdir(exist_ok=True)
    return Site(title="T", base_url=BASE, root=root, **kw)


def put(path: Path, text: str = "x") -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def snapshot(root: Path) -> dict[str, str]:
    return {
        str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in sorted(root.rglob("*"))
        if p.is_file() and not p.is_symlink()
    }


def about_page(**kw) -> Page:
    return Page(
        url=ABOUT,
        output="about/index.html",
        title="About",
        description="d",
        body=Markup("<p>hi</p>"),
        source="",
        template="page.html",
        **kw,
    )


def files(out: Path) -> list[str]:
    return sorted(p.relative_to(out).as_posix() for p in out.rglob("*") if p.is_file())


def test_full_build(tmp_path):
    site = make_site(tmp_path)
    put(site.root / "static/css/s.css", "body{}")
    out = tmp_path / "out"
    b = Builder(site, out)
    b.render("page.html", ABOUT, page=about_page())
    b.render("page.html", "", title="Home")
    assert b.copy_static() == 1
    report = b.finish()
    assert files(out) == [
        ".nojekyll",
        "404.html",
        "about/index.html",
        "css/s.css",
        "index.html",
        "robots.txt",
        "sitemap.xml",
    ]
    assert report == BuildReport(
        pages=2, static=1, extras=["404.html", "sitemap.xml", "robots.txt", ".nojekyll"]
    )


def test_context_reaches_template(tmp_path):
    b = Builder(make_site(tmp_path), tmp_path / "out")
    assert "<h1>Home</h1>" in b.render("page.html", "", title="Home").read_text()


@pytest.mark.parametrize(
    ("path", "expected"),
    [
        ("", "index.html"),
        ("a/", "a/index.html"),
        ("a/b/", "a/b/index.html"),
        ("feed.xml", "feed.xml"),
        ("x.html", "x.html"),
    ],
)
def test_path_mapping(tmp_path, path, expected):
    b = Builder(make_site(tmp_path), tmp_path / "out")
    assert b.render("page.html", path) == b.out / expected


def test_render_defaults_page_from_site(tmp_path):
    site = make_site(tmp_path, description="site desc", lang="cs")
    b = Builder(site, tmp_path / "out")
    html = b.render("page.html", "x/").read_text()
    assert 'lang="cs"' in html
    assert "site desc" in html


def test_default_out_and_relative_out_resolve_against_root(tmp_path, monkeypatch):
    site = make_site(tmp_path)
    monkeypatch.chdir(tmp_path)
    assert Builder(site).out == (site.root / "_site").resolve()
    assert Builder(site, "build").out == (site.root / "build").resolve()


def test_page_output_mismatch(tmp_path):
    b = Builder(make_site(tmp_path), tmp_path / "out")
    with pytest.raises(ContentError, match=re.escape("not 'other/index.html'")):
        b.render("page.html", "other/", page=about_page())


@pytest.mark.parametrize(
    "path", ["../x/", "/etc/x.html", "a/../../x/", "a\\b/", "a\0b/", "a/../b/"]
)
def test_escaping_paths_rejected(tmp_path, path):
    out = tmp_path / "out"
    b = Builder(make_site(tmp_path), out)
    with pytest.raises(ContentError, match="invalid page path"):
        b.render("page.html", path)
    assert files(out) == []
    assert not (tmp_path / "x").exists()


def test_symlinked_subfolder_cannot_escape(tmp_path):
    out = tmp_path / "out"
    b = Builder(make_site(tmp_path), out)
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    (out / "link").symlink_to(elsewhere, target_is_directory=True)
    with pytest.raises(ContentError, match="outside the output folder"):
        b.render("page.html", "link/x.html")
    assert list(elsewhere.iterdir()) == []


def test_render_error_leaves_partial_output(tmp_path):
    site = make_site(tmp_path)
    put(site.root / "templates/bad.html", "{{ nope }}")
    b = Builder(site, tmp_path / "out")
    b.render("page.html", "ok/")
    with pytest.raises(RenderError):
        b.render("bad.html", "bad/")
    assert files(b.out) == ["ok/index.html"]


def test_missing_out_is_created(tmp_path):
    out = tmp_path / "deep" / "out"
    Builder(make_site(tmp_path), out)
    assert out.is_dir()


def sources(site: Site) -> None:
    for name in ("content", "templates", "static", "data"):
        put(site.root / name / "keep.txt")


@pytest.fixture
def home(tmp_path, monkeypatch) -> Path:
    h = tmp_path / "home"
    h.mkdir()
    monkeypatch.setattr(builder_mod, "_home", lambda: h)
    return h


def test_refuses_site_root(tmp_path):
    site = make_site(tmp_path)
    put(site.root / "a.txt")
    before = snapshot(site.root)
    with pytest.raises(ConfigError, match="site root"):
        Builder(site, site.root)
    assert snapshot(site.root) == before


def test_refuses_parent_of_root(tmp_path):
    site = make_site(tmp_path)
    put(tmp_path / "other.txt")
    before = snapshot(tmp_path)
    with pytest.raises(ConfigError, match="parent"):
        Builder(site, tmp_path)
    assert snapshot(tmp_path) == before


def test_refuses_home(tmp_path, home):
    site = make_site(tmp_path)
    put(home / "doc.txt")
    with pytest.raises(ConfigError, match="home"):
        Builder(site, home)
    assert files(home) == ["doc.txt"]


def test_refuses_filesystem_root(tmp_path, home):
    with pytest.raises(ConfigError, match="filesystem root"):
        Builder(make_site(tmp_path), Path(tmp_path.anchor))


def test_refuses_folder_containing_content(tmp_path, home):
    site = make_site(tmp_path, content="work/content")
    sources(site)
    before = snapshot(site.root)
    with pytest.raises(ConfigError, match="contains or equals"):
        Builder(site, site.root / "work")
    assert snapshot(site.root) == before


def test_refuses_equal_to_source_folder(tmp_path, home):
    site = make_site(tmp_path)
    sources(site)
    before = snapshot(site.root)
    with pytest.raises(ConfigError, match="contains or equals"):
        Builder(site, site.root / "templates")
    assert snapshot(site.root) == before


def test_refuses_inside_static(tmp_path, home):
    site = make_site(tmp_path)
    sources(site)
    before = snapshot(site.root)
    with pytest.raises(ConfigError, match="inside the source folder"):
        Builder(site, site.root / "static" / "sub")
    assert snapshot(site.root) == before


def test_refuses_symlink(tmp_path, home):
    site = make_site(tmp_path)
    target = tmp_path / "target"
    put(target / "precious.txt")
    link = tmp_path / "link"
    link.symlink_to(target, target_is_directory=True)
    with pytest.raises(ConfigError, match="symlink"):
        Builder(site, link)
    assert files(target) == ["precious.txt"]


def test_refuses_file(tmp_path, home):
    site = make_site(tmp_path)
    f = put(tmp_path / "afile")
    with pytest.raises(ConfigError, match="not a folder"):
        Builder(site, f)
    assert f.read_text() == "x"


def test_clearing_keeps_git_and_cname(tmp_path):
    out = tmp_path / "out"
    put(out / "stale.html")
    put(out / "old/deep/x.html")
    put(out / ".git/HEAD", "ref")
    put(out / "CNAME", "ex.org")
    precious = put(tmp_path / "precious.txt", "keep me")
    (out / "link").symlink_to(precious)
    (out / "dirlink").symlink_to(tmp_path, target_is_directory=True)
    Builder(make_site(tmp_path), out)
    assert sorted(p.name for p in out.iterdir()) == [".git", "CNAME"]
    assert snapshot(out) == {
        ".git/HEAD": hashlib.sha256(b"ref").hexdigest(),
        "CNAME": hashlib.sha256(b"ex.org").hexdigest(),
    }
    assert precious.read_text() == "keep me"


def test_rerun_removes_stale_files(tmp_path):
    site = make_site(tmp_path)
    out = tmp_path / "out"
    first = Builder(site, out)
    first.render("page.html", "old/")
    second = Builder(site, out)
    second.render("page.html", "new/")
    assert files(out) == ["new/index.html"]


def git_repo(site: Site) -> None:
    git = shutil.which("git")
    assert git
    for args in (["init", "-q"], ["config", "user.email", "a@b.c"]):
        subprocess.run([git, *args], cwd=site.root, check=True)  # noqa: S603


def track(site: Site, rel: str) -> Path:
    git = shutil.which("git")
    assert git
    f = put(site.root / rel)
    subprocess.run([git, "add", rel], cwd=site.root, check=True)  # noqa: S603
    return f


def track_many(site: Site, count: int) -> None:
    for i in range(count):
        track(site, f"_site/f{i}.html")


def test_tracked_file_blocks_clearing(tmp_path):
    site = make_site(tmp_path)
    git_repo(site)
    keep = track(site, "_site/keep.html")
    other = put(site.root / "_site/other.html")
    with pytest.raises(ConfigError, match=r"keep\.html") as ei:
        Builder(site)
    assert "1 tracked" in str(ei.value)
    assert keep.exists()
    assert other.exists()


def test_tracked_listing_is_capped(tmp_path):
    site = make_site(tmp_path)
    git_repo(site)
    track_many(site, 7)
    with pytest.raises(ConfigError, match="7 tracked") as ei:
        Builder(site)
    assert "f4.html" in str(ei.value)
    assert "f5.html" not in str(ei.value)
    assert "..." in str(ei.value)


def test_force_clear_overrides_tracked_guard(tmp_path):
    site = make_site(tmp_path)
    git_repo(site)
    keep = track(site, "_site/keep.html")
    Builder(site, force_clear=True)
    assert not keep.exists()


def test_allow_tracked_out_overrides_tracked_guard(tmp_path):
    site = make_site(tmp_path, allow_tracked_out=True)
    git_repo(site)
    keep = track(site, "_site/keep.html")
    Builder(site)
    assert not keep.exists()


def test_not_a_repo_clears(tmp_path, monkeypatch):
    site = make_site(tmp_path)
    monkeypatch.setenv("GIT_CEILING_DIRECTORIES", str(tmp_path))
    stale = put(site.root / "_site/stale.html")
    Builder(site)
    assert not stale.exists()


def test_no_git_on_path_clears(tmp_path, monkeypatch):
    site = make_site(tmp_path)
    monkeypatch.setattr(builder_mod.shutil, "which", lambda _name: None)
    stale = put(site.root / "_site/stale.html")
    Builder(site)
    assert not stale.exists()


@pytest.mark.parametrize("exc", [OSError("boom"), subprocess.TimeoutExpired("git", 1)])
def test_git_failure_skips_guard(tmp_path, monkeypatch, exc):
    site = make_site(tmp_path)
    stale = put(site.root / "_site/stale.html")

    def boom(*_a, **_k):
        raise exc

    monkeypatch.setattr(builder_mod.subprocess, "run", boom)
    Builder(site)
    assert not stale.exists()


def test_static_symlinks_and_git_skipped(tmp_path):
    site = make_site(tmp_path)
    static = site.root / "static"
    put(static / "a.txt")
    put(static / "sub/b.txt")
    put(static / ".git/config")
    put(static / ".well-known/x")
    outside = put(tmp_path / "outside.txt")
    (static / "link.txt").symlink_to(outside)
    (static / "dirlink").symlink_to(tmp_path, target_is_directory=True)
    b = Builder(site, tmp_path / "out")
    assert b.copy_static() == 3
    assert files(b.out) == [".well-known/x", "a.txt", "sub/b.txt"]


def test_missing_static_copies_nothing(tmp_path):
    assert Builder(make_site(tmp_path), tmp_path / "out").copy_static() == 0


def test_copy_static_custom_src(tmp_path):
    other = tmp_path / "assets"
    put(other / "z.txt")
    b = Builder(make_site(tmp_path), tmp_path / "out")
    assert b.copy_static(other) == 1
    assert files(b.out) == ["z.txt"]


def test_static_cname_overwrites_preserved(tmp_path):
    site = make_site(tmp_path)
    put(site.root / "static/CNAME", "new.org")
    out = tmp_path / "out"
    put(out / "CNAME", "old.org")
    Builder(site, out).copy_static()
    assert (out / "CNAME").read_text() == "new.org"


def test_static_then_page_collision(tmp_path):
    site = make_site(tmp_path)
    put(site.root / "static/about/index.html")
    b = Builder(site, tmp_path / "out")
    b.copy_static()
    with pytest.raises(ContentError) as ei:
        b.render("page.html", ABOUT, page=about_page())
    assert "static file" in str(ei.value)
    assert "about/" in str(ei.value)


def test_page_then_static_collision(tmp_path):
    site = make_site(tmp_path)
    put(site.root / "static/about/index.html")
    b = Builder(site, tmp_path / "out")
    b.render("page.html", ABOUT, page=about_page())
    with pytest.raises(ContentError) as ei:
        b.copy_static()
    assert "static file" in str(ei.value)
    assert "page 'about/'" in str(ei.value)


def test_page_page_collision(tmp_path):
    b = Builder(make_site(tmp_path), tmp_path / "out")
    b.render("page.html", ABOUT)
    with pytest.raises(ContentError, match="both"):
        b.render("page.html", ABOUT)


def test_static_vs_extra_collision(tmp_path):
    site = make_site(tmp_path)
    put(site.root / "static/robots.txt")
    b = Builder(site, tmp_path / "out")
    b.copy_static()
    with pytest.raises(ContentError) as ei:
        b.finish()
    assert "robots.txt" in str(ei.value)
    assert "extra:robots" in str(ei.value)
    assert files(b.out) == ["robots.txt"]


def test_finish_twice_and_use_after_finish(tmp_path):
    b = Builder(make_site(tmp_path), tmp_path / "out")
    b.finish()
    for call in (
        b.finish,
        lambda: b.render("page.html", "x/"),
        b.copy_static,
    ):
        with pytest.raises(DeedumError, match="finished"):
            call()


def test_sitemap_lists_only_html_pages(tmp_path):
    b = Builder(make_site(tmp_path), tmp_path / "out")
    b.render("page.html", "a/")
    b.render("page.html", "feed.xml")
    b.finish()
    text = (b.out / "sitemap.xml").read_text()
    assert "https://ex.org/b/a/" in text
    assert "feed.xml" not in text


def git_tree_hash(root: Path) -> str:
    h = hashlib.sha256()
    for p in sorted(root.rglob("*")):
        h.update(str(p.relative_to(root)).encode())
        if p.is_file():
            h.update(p.read_bytes())
    return h.hexdigest()


@pytest.mark.parametrize("out", [".git", ".git/x"])
def test_out_inside_dot_git_refused(tmp_path, out):
    site = make_site(tmp_path)
    git_repo(site)
    track(site, "a.txt")
    before = git_tree_hash(site.root / ".git")
    with pytest.raises(ConfigError, match=r"\.git folder"):
        Builder(site, out)
    assert git_tree_hash(site.root / ".git") == before


def test_out_absolute_through_other_dot_git_refused(tmp_path):
    site = make_site(tmp_path)
    put(tmp_path / "other/.git/HEAD", "ref")
    with pytest.raises(ConfigError, match=r"\.git folder"):
        Builder(site, tmp_path / "other/.git/sub")
    assert (tmp_path / "other/.git/HEAD").read_text() == "ref"


@pytest.mark.parametrize("path", [".git/config", ".git/hooks/x/", ".git/", "CNAME"])
def test_render_reserved_paths_refused(tmp_path, path):
    site = make_site(tmp_path)
    out = tmp_path / "out"
    put(out / ".git/config", "cfg")
    put(out / "CNAME", "ex.org")
    b = Builder(site, out)
    before = snapshot(out)
    with pytest.raises(ContentError):
        b.render("page.html", path)
    assert snapshot(out) == before
    assert before == {
        ".git/config": hashlib.sha256(b"cfg").hexdigest(),
        "CNAME": hashlib.sha256(b"ex.org").hexdigest(),
    }


def test_static_dot_git_file_skipped_and_cname_overwrites(tmp_path):
    site = make_site(tmp_path)
    put(site.root / "static/.git", "gitfile")
    put(site.root / "static/sub/.git", "gitfile")
    put(site.root / "static/CNAME", "new.org")
    out = tmp_path / "out"
    put(out / ".git/config", "cfg")
    b = Builder(site, out)
    assert b.copy_static() == 1
    assert files(b.out) == [".git/config", "CNAME"]
    assert (out / "CNAME").read_text() == "new.org"


def test_copy_static_src_overlapping_out_refused(tmp_path):
    site = make_site(tmp_path)
    put(site.root / "keep.txt")
    b = Builder(site, "o4")
    for src in (b.out, site.root):
        with pytest.raises(ContentError, match="inside the other"):
            b.copy_static(src)
    assert files(b.out) == []
    assert not (b.out / "o4").exists()


def test_guard_checks_repo_holding_out(tmp_path):
    site = make_site(tmp_path)
    git_repo(site)
    (tmp_path / "b").mkdir()
    other = make_site(tmp_path / "b")
    git_repo(other)
    keep = track(other, "pub/t.html")
    with pytest.raises(ConfigError, match=r"t\.html"):
        Builder(site, keep.parent)
    assert keep.exists()


def test_finish_retry_reports_real_collision(tmp_path):
    site = make_site(tmp_path)
    put(site.root / "static/robots.txt")
    b = Builder(site, tmp_path / "out")
    b.copy_static()
    for _ in range(2):
        with pytest.raises(ContentError, match=r"robots\.txt.*extra:robots"):
            b.finish()


@pytest.mark.parametrize("path", ["a//b/", "./a/", "a/./b/", "a/."])
def test_render_rejects_empty_and_dot_segments(tmp_path, path):
    b = Builder(make_site(tmp_path), tmp_path / "out")
    with pytest.raises(ContentError, match=r"empty or '\.' segment"):
        b.render("page.html", path)


SVG = (
    '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 8 8">'
    '<rect width="8" height="8" fill="#cc3333"/></svg>'
)
NOW = dt.datetime(2026, 11, 18, 12, tzinfo=dt.UTC)
FIXED_PUBLISHED = dt.date(2026, 3, 4)


def post(slug: str, **kw) -> Page:
    kw.setdefault("date", FIXED_PUBLISHED)
    return Page(
        url=f"blog/{slug}/",
        output=f"blog/{slug}/index.html",
        title=slug,
        description="d",
        body=Markup("<p>b</p>"),
        source=f"# {slug}\n",
        template="page.html",
        collection="blog",
        **kw,
    )


def rich_site(tmp_path: Path, **kw) -> Site:
    kw.setdefault("favicon", "icon.svg")
    kw.setdefault("feeds", ("blog",))
    kw.setdefault("llms", True)
    site = make_site(tmp_path, **kw)
    put(site.root / "icon.svg", SVG)
    return site


def build_rich(site: Site, out: Path) -> BuildReport:
    b = Builder(site, out, now=NOW)
    b.render("page.html", "", title="Home")
    b.render("page.html", "blog/hi/", page=post("hi"))
    return b.finish()


def test_finish_writes_new_extras_in_order(tmp_path):
    out = tmp_path / "out"
    report = build_rich(rich_site(tmp_path), out)
    assert report.extras == [
        "404.html",
        "sitemap.xml",
        "robots.txt",
        ".nojekyll",
        "favicon.ico",
        "favicon.svg",
        "apple-touch-icon.png",
        "icon-192.png",
        "icon-512.png",
        "site.webmanifest",
        "blog/feed.xml",
        "llms.txt",
        "llms-full.txt",
        "blog/hi/index.md",
    ]
    assert Image.open(out / "icon-512.png").size == (512, 512)
    assert "blog/hi/" in (out / "blog/feed.xml").read_text(encoding="utf-8")
    assert (out / "blog/hi/index.md").read_text(encoding="utf-8") == "# hi\n"


def test_sitemap_still_lists_only_html_pages(tmp_path):
    out = tmp_path / "out"
    build_rich(rich_site(tmp_path), out)
    sitemap = (out / "sitemap.xml").read_text(encoding="utf-8")
    assert "index.md" not in sitemap
    assert "feed.xml" not in sitemap


def test_png_source_head_links(tmp_path):
    site = make_site(tmp_path, favicon="icon.png")
    Image.new("RGB", (512, 512), "red").save(site.root / "icon.png")
    b = Builder(site, tmp_path / "out")
    html = b.render("page.html", "").read_text(encoding="utf-8")
    assert b.finish().extras.count("favicon.svg") == 0
    assert 'href="/b/site.webmanifest"' in html
    assert "favicon.svg" not in html


def test_nothing_new_without_config(tmp_path):
    out = tmp_path / "out"
    b = Builder(make_site(tmp_path), out)
    b.render("page.html", ABOUT, page=about_page())
    b.finish()
    assert files(out) == [
        ".nojekyll",
        "404.html",
        "about/index.html",
        "robots.txt",
        "sitemap.xml",
    ]


def test_llms_off_writes_no_llms_files(tmp_path):
    out = tmp_path / "out"
    build_rich(rich_site(tmp_path, llms=False), out)
    assert not (out / "llms.txt").exists()
    assert list(out.rglob("index.md")) == []


def test_now_defaults_to_current_utc_time_once(tmp_path):
    site = make_site(tmp_path, feeds=("blog",))
    before = dt.datetime.now(dt.UTC).replace(microsecond=0)
    b = Builder(site, tmp_path / "out")
    b.finish()
    feed = (tmp_path / "out/blog/feed.xml").read_text(encoding="utf-8")
    stamp = re.search(r"<updated>([^<]+)</updated>", feed)
    assert stamp is not None
    written = dt.datetime.strptime(stamp.group(1), "%Y-%m-%dT%H:%M:%SZ").replace(
        tzinfo=dt.UTC
    )
    assert before <= written <= dt.datetime.now(dt.UTC)


@pytest.mark.parametrize(
    ("static", "label"),
    [
        ("favicon.ico", "extra:favicon"),
        ("favicon.svg", "extra:favicon"),
        ("site.webmanifest", "extra:favicon"),
        ("blog/feed.xml", "extra:feed:blog"),
        ("llms.txt", "extra:llms"),
        ("llms-full.txt", "extra:llms"),
        ("blog/hi/index.md", "extra:llms"),
    ],
)
def test_static_vs_new_extra_collision(tmp_path, static, label):
    site = rich_site(tmp_path)
    src = put(site.root / "static" / static)
    out = tmp_path / "out"
    b = Builder(site, out, now=NOW)
    b.render("page.html", "blog/hi/", page=post("hi"))
    b.copy_static()
    before = files(out)
    for _ in range(2):
        with pytest.raises(ContentError) as ei:
            b.finish()
        assert str(src) in str(ei.value)
        assert label in str(ei.value)
    assert files(out) == before


def test_favicon_collision_hints_at_source_outside_static(tmp_path):
    site = rich_site(tmp_path, favicon="static/favicon.svg")
    put(site.root / "static/favicon.svg", SVG)
    b = Builder(site, tmp_path / "out")
    b.copy_static()
    with pytest.raises(ContentError) as ei:
        b.finish()
    assert "outside the static folder" in (ei.value.hint or "")


def test_favicon_hint_is_neutral_when_static_file_is_not_the_source(tmp_path):
    site = rich_site(tmp_path, favicon="icon.png")
    put(site.root / "static/apple-touch-icon.png")
    b = Builder(site, tmp_path / "out")
    b.copy_static()
    with pytest.raises(ContentError) as ei:
        b.finish()
    assert (ei.value.hint or "").startswith("remove the static file")


def failed_twice(b: Builder, *names: str) -> list[str]:
    """Run finish() twice, expect the same ContentError naming ``names``."""
    messages = []
    for _ in range(2):
        with pytest.raises(ContentError) as ei:
            b.finish()
        assert all(n in str(ei.value) for n in names)
        messages.append(str(ei.value))
    return messages


def test_static_file_vs_feed_folder_checked_before_any_write(tmp_path):
    site = make_site(tmp_path, feeds=("news",))
    put(site.root / "static/news")
    out = tmp_path / "out"
    b = Builder(site, out, now=NOW)
    b.copy_static()
    first, second = failed_twice(b, "'news'", "extra:feed:news")
    assert first == second
    assert files(out) == ["news"]


def test_feed_named_like_an_extra_is_checked_before_any_write(tmp_path):
    site = make_site(tmp_path, feeds=("404.html",))
    out = tmp_path / "out"
    b = Builder(site, out, now=NOW)
    first, second = failed_twice(b, "404.html/feed.xml", "extra:404")
    assert first == second
    assert files(out) == []


def test_page_vs_page_prefix_collision(tmp_path):
    b = Builder(make_site(tmp_path), tmp_path / "out")
    b.render("page.html", "a")
    with pytest.raises(ContentError, match=r"'a/index.html'.*'a'"):
        b.render("page.html", "a/")


def test_static_file_vs_page_folder_collision(tmp_path):
    site = make_site(tmp_path)
    put(site.root / "static/blog")
    b = Builder(site, tmp_path / "out")
    b.render("page.html", "blog/hello/")
    with pytest.raises(ContentError, match="blog"):
        b.copy_static()


def test_page_at_feed_path_collides(tmp_path):
    site = rich_site(tmp_path)
    b = Builder(site, tmp_path / "out", now=NOW)
    b.render("page.html", "blog/feed.xml", title="x")
    with pytest.raises(ContentError, match=r"blog/feed\.xml.*extra:feed:blog"):
        b.finish()


def test_page_at_sibling_path_collides(tmp_path):
    b = Builder(rich_site(tmp_path), tmp_path / "out", now=NOW)
    b.render("page.html", "blog/hi/", page=post("hi"))
    b.render("page.html", "blog/hi/index.md", title="x")
    with pytest.raises(ContentError, match=r"index\.md.*extra:llms"):
        b.finish()


def test_sibling_collision_only_for_pages_with_a_sibling(tmp_path):
    site = rich_site(tmp_path)
    put(site.root / "static/blog/other/index.md")
    out = tmp_path / "out"
    b = Builder(site, out, now=NOW)
    b.render("page.html", "blog/hi/", page=post("hi"))
    b.copy_static()
    assert "blog/other/index.md" not in b.finish().extras


def favicon_failure(b: Builder) -> str:
    with pytest.raises(ConfigError, match="favicon") as ei:
        b.finish()
    return str(ei.value)


@pytest.mark.parametrize(
    "favicon",
    ["missing.png", "small.png", "wide.png", "fake.png", "bad.svg"],
)
def test_bad_favicon_writes_nothing_and_retries_same_error(tmp_path, favicon):
    site = rich_site(tmp_path, favicon=favicon)
    Image.new("RGB", (256, 256)).save(site.root / "small.png")
    Image.new("RGB", (600, 512)).save(site.root / "wide.png")
    Image.new("RGB", (600, 600)).save(site.root / "fake.png", format="JPEG")
    put(site.root / "bad.svg", "<svg")
    out = tmp_path / "out"
    b = Builder(site, out, now=NOW)
    b.render("page.html", "blog/hi/", page=post("hi"))
    first = favicon_failure(b)
    assert favicon_failure(b) == first
    assert favicon in first
    assert files(out) == ["blog/hi/index.html"]


def test_determinism_with_frozen_now(tmp_path):
    first, second = tmp_path / "one", tmp_path / "two"
    site = rich_site(tmp_path)
    report = build_rich(site, first)
    build_rich(site, second)
    match, mismatch, errors = filecmp.cmpfiles(
        first, second, report.extras, shallow=False
    )
    assert (sorted(match), mismatch, errors) == (sorted(report.extras), [], [])
