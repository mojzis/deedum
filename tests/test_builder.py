from __future__ import annotations

import hashlib
import re
import shutil
import subprocess
from pathlib import Path

import pytest
from markupsafe import Markup

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
