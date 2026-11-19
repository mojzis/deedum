from __future__ import annotations

import datetime as dt
from pathlib import Path

from markupsafe import Markup

from deedum import Page, Site
from deedum.extras.llms import sibling_paths, write_llms

BASE = "https://ex.org/sub/"


def make_site(**kw) -> Site:
    kw.setdefault("llms", True)
    kw.setdefault("description", "About things")
    return Site(title="T", base_url="https://ex.org", base_path="/sub/", **kw)


def page(url: str, title: str = "", source: str = "src", **kw) -> Page:
    output = f"{url}index.html" if url.endswith("/") or not url else url
    return Page(
        url=url,
        output=output,
        title=title or url,
        description=kw.pop("description", ""),
        body=Markup(""),
        source=source,
        template="page.html",
        **kw,
    )


def run(tmp_path: Path, pages, **kw) -> Path:
    out = tmp_path / "out"
    out.mkdir(exist_ok=True)
    write_llms(make_site(**kw), pages, out)
    return out


def short(out: Path) -> str:
    return (out / "llms.txt").read_text(encoding="utf-8")


def lines(out: Path) -> list[str]:
    return short(out).splitlines()


def test_header_with_description(tmp_path):
    assert short(run(tmp_path, [])).startswith("# T\n\n> About things\n")


def test_header_without_description(tmp_path):
    assert short(run(tmp_path, [], description="")) == "# T\n"


def test_description_newlines_collapsed(tmp_path):
    out = run(tmp_path, [], description="a\n\nb  c")
    assert lines(out)[2] == "> a b c"


def test_group_and_in_group_order(tmp_path):
    pages = [
        page("blog/old/", "Old", date=dt.date(2026, 1, 1), collection="blog"),
        page("blog/", "Blog", collection="blog"),
        page("blog/new/", "New", date=dt.date(2026, 2, 1), collection="blog"),
        page("blog/zz/", "Zed", collection="blog"),
        page("blog/aa/", "aardvark", collection="blog"),
        page("about/", "About"),
        page("", "Home"),
        page("tools/x/", "X", collection="tools"),
    ]
    got = [x for x in lines(run(tmp_path, pages)) if x.startswith(("##", "- "))]
    assert got == [
        "## Pages",
        f"- [About]({BASE}about/)",
        f"- [Home]({BASE})",
        "## blog",
        f"- [Blog]({BASE}blog/)",
        f"- [New]({BASE}blog/new/)",
        f"- [Old]({BASE}blog/old/)",
        f"- [aardvark]({BASE}blog/aa/)",
        f"- [Zed]({BASE}blog/zz/)",
        "## tools",
        f"- [X]({BASE}tools/x/)",
    ]


def test_dated_ties_by_url(tmp_path):
    same = dt.date(2026, 1, 1)
    pages = [
        page("b/", "B", date=same, collection="c"),
        page("a/", "A", date=same, collection="c"),
    ]
    got = [x for x in lines(run(tmp_path, pages)) if x.startswith("- ")]
    assert got == [f"- [A]({BASE}a/)", f"- [B]({BASE}b/)"]


def test_description_and_escaped_title(tmp_path):
    pages = [
        page("a/", "[x] \\ y", description="line1\nline2"),
        page("b/", "B"),
    ]
    got = [x for x in lines(run(tmp_path, pages)) if x.startswith("- ")]
    assert got == [
        f"- [\\[x\\] \\\\ y]({BASE}a/): line1 line2",
        f"- [B]({BASE}b/)",
    ]


def test_noindex_and_404_excluded_everywhere(tmp_path):
    pages = [
        page("keep/", "Keep"),
        page("secret/", "Secret", noindex=True),
        page("404.html", "Not found"),
    ]
    out = run(tmp_path, pages)
    text = short(out) + (out / "llms-full.txt").read_text(encoding="utf-8")
    assert "keep/" in text
    assert "secret" not in text
    assert "404" not in text
    assert not (out / "secret").exists()


def test_full_format(tmp_path):
    pages = [
        page("a/", "A", source="# A\n\ntext\n"),
        page("b/", "B", source=""),
        page("c/", "C", source="c body"),
    ]
    out = run(tmp_path, pages)
    assert (out / "llms-full.txt").read_text(encoding="utf-8") == (
        "# T\n\n> About things\n\n"
        f"---\n\nURL: {BASE}a/\n\n# A\n\ntext\n\n"
        f"---\n\nURL: {BASE}c/\n\nc body\n"
    )


def test_siblings_only_for_index_html_with_source(tmp_path):
    pages = [
        page("blog/hello/", "H", source="hello *md*"),
        page("", "Home", source="home"),
        page("empty/", "E", source=""),
        page("x.html", "X", source="x"),
        page("hid/", "Hid", source="h", noindex=True),
    ]
    out = run(tmp_path, pages)
    found = sorted(p.relative_to(out).as_posix() for p in out.rglob("index.md"))
    assert found == ["blog/hello/index.md", "index.md"]
    assert (out / "blog/hello/index.md").read_text(encoding="utf-8") == "hello *md*"
    assert sibling_paths(pages) == ["blog/hello/index.md", "index.md"]


def test_sibling_is_verbatim(tmp_path):
    text = "line1\r\nline2 é"
    out = run(tmp_path, [page("a/", "A", source=text)])
    assert (out / "a/index.md").read_bytes() == text.encode("utf-8")


def test_lf_and_trailing_newline(tmp_path):
    out = run(tmp_path, [page("a/", "A", source="x\r\ny")])
    for name in ("llms.txt", "llms-full.txt"):
        data = (out / name).read_bytes()
        assert data.endswith(b"\n")
        assert not data.endswith(b"\n\n")


def test_returns_every_written_path(tmp_path):
    out = tmp_path / "out"
    out.mkdir()
    written = write_llms(make_site(), [page("a/", "A")], out)
    assert [p.relative_to(out).as_posix() for p in written] == [
        "llms.txt",
        "llms-full.txt",
        "a/index.md",
    ]


def test_nothing_written_when_off(tmp_path):
    out = tmp_path / "out"
    out.mkdir()
    assert write_llms(make_site(llms=False), [page("a/", "A")], out) == []
    assert list(out.iterdir()) == []
