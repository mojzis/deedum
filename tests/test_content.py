from __future__ import annotations

import copy
import pickle
from collections.abc import Mapping
from datetime import UTC, date, datetime
from pathlib import Path

import pytest
from markupsafe import Markup

from deedum import (
    ContentError,
    Site,
    build_collections,
    load_data,
    load_pages,
)

DEEP = "blog/2024/deep/"


def make_site(tmp_path: Path, files: Mapping[str, str | bytes], **kw) -> Site:
    for name, content in files.items():
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        if isinstance(content, bytes):
            path.write_bytes(content)
        else:
            path.write_text(content, encoding="utf-8")
    kw.setdefault("title", "Demo")
    return Site(base_url="https://e.org", root=tmp_path, **kw)


def pages_of(tmp_path: Path, files: Mapping[str, str | bytes], **kw):
    return {p.url: p for p in load_pages(make_site(tmp_path, files, **kw))}


def one(tmp_path: Path, text: str | bytes, name: str = "content/x.md", **kw):
    return pages_of(tmp_path, {name: text}, **kw)["x/"]


FM = "---\n{}\n---\n"

TREE = {
    "content/index.md": "Welcome.",
    "content/about.md": "A",
    "content/blog/index.md": "---\ntitle: Blog\n---\n",
    "content/blog/hello.md": "H",
    "content/blog/second.md": "---\nslug: other\n---\nS",
    "content/blog/2024/deep.md": "D",
    "content/_partial.md": "x",
    "content/blog/_x.md": "x",
    "content/_drafts/y.md": "x",
    "content/.hidden/z.md": "x",
    "content/blog/wip.md": "---\ndraft: true\n---\nx",
    "content/blog/notes.txt": "not markdown",
}


def test_path_mapping_and_skips(tmp_path):
    pages = load_pages(make_site(tmp_path, TREE))
    assert [(p.url, p.output) for p in pages] == [
        ("", "index.html"),
        ("about/", "about/index.html"),
        ("blog/", "blog/index.html"),
        (DEEP, "blog/2024/deep/index.html"),
        ("blog/hello/", "blog/hello/index.html"),
        ("blog/other/", "blog/other/index.html"),
    ]
    assert pages[0].source_path == tmp_path / "content/index.md"


def test_missing_content_and_data(tmp_path):
    site = make_site(tmp_path, {})
    assert load_pages(site) == []
    assert load_data(site) == {}


def test_empty_md(tmp_path):
    p = one(tmp_path, "")
    assert (p.title, p.description, str(p.body)) == ("x", "", "")


@pytest.mark.parametrize(
    "files",
    [
        {"content/about.md": "a", "content/about/index.md": "b"},
        {"content/a.md": "a", "content/b.md": "---\nslug: a\n---\n"},
    ],
)
def test_collision_names_both(tmp_path, files):
    with pytest.raises(ContentError) as exc:
        load_pages(make_site(tmp_path, files))
    for name in files:
        assert name in str(exc.value)


@pytest.mark.parametrize(
    ("name", "slug"),
    [
        ("content/index.md", "a"),
        ("content/x.md", "a/b"),
        ("content/x.md", ""),
        ("content/x.md", ".."),
        ("content/x.md", "."),
        ("content/x.md", "[1]"),
    ],
)
def test_bad_slug(tmp_path, name, slug):
    text = FM.format(f"slug: {slug!r}" if slug != "[1]" else "slug: [1]")
    with pytest.raises(ContentError, match=name):
        load_pages(make_site(tmp_path, {name: text}))


def test_slug_on_nested(tmp_path):
    p = pages_of(tmp_path, {"content/a/b.md": FM.format("slug: c")})
    assert list(p) == ["a/c/"]


@pytest.mark.parametrize("text", ["---\n---\nhi", "---\n# only comment\n---\nhi"])
def test_empty_frontmatter(tmp_path, text):
    assert one(tmp_path, text).meta == {}


def test_bom_is_fine(tmp_path):
    assert one(tmp_path, "\ufeff---\ntitle: T\n---\nhi").title == "T"


def test_no_frontmatter(tmp_path):
    p = one(tmp_path, "no frontmatter\n---\nnot closed either")
    assert (p.meta, p.source[:14]) == ({}, "no frontmatter")


def test_unknown_keys_kept(tmp_path):
    p = one(tmp_path, FM.format("tags: [a, b]\nn: 3"))
    assert p.tags == ["a", "b"]
    assert p.meta["n"] == 3
    with pytest.raises(AttributeError):
        p.nope  # noqa: B018
    with pytest.raises(AttributeError):
        p._private  # noqa: B018


def test_page_copy_and_pickle(tmp_path):
    p = one(tmp_path, FM.format("tags: [a]"))
    assert copy.copy(p).tags == ["a"]
    assert copy.deepcopy(p).tags == ["a"]
    assert pickle.loads(pickle.dumps(p)).tags == ["a"]  # noqa: S301
    assert isinstance(hash(p), int)


MALFORMED = [
    ("---\ntitle: [unclosed\n---\n", ""),
    ("---\ntitle: x", ""),
    ("---\n- a\n---\n", ""),
    (FM.format("draft: 'yes'"), "draft"),
    (FM.format("noindex: 1"), "noindex"),
    (FM.format("date: last tuesday"), "date"),
    (FM.format("updated: last tuesday"), "updated"),
    (FM.format("date: 5"), "date"),
    (FM.format("title: [a]"), "title"),
    (FM.format("image: 3"), "image"),
    (FM.format("url: /x/"), "url"),
    (FM.format("output: a"), "output"),
    (FM.format("collection: a"), "collection"),
    (FM.format("1: a"), "1"),
    (FM.format("alternates: x"), "alternates"),
    (FM.format("alternates: {de: 3}"), "alternates"),
    (b"\xff\xfe\x00", ""),
]


@pytest.mark.parametrize(("text", "key"), MALFORMED)
def test_malformed_md(tmp_path, text, key):
    files = {"content/ok.md": "fine", "content/bad.md": text}
    with pytest.raises(ContentError) as exc:
        load_pages(make_site(tmp_path, files))
    assert "content/bad.md" in str(exc.value)
    assert key in str(exc.value)


def test_unreadable_md(tmp_path, monkeypatch):
    site = make_site(tmp_path, {"content/a.md": "x"})
    real = Path.read_text

    def deny(self, *args, **kwargs):
        if self.name == "a.md":
            raise PermissionError(13, "Permission denied")
        return real(self, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", deny)
    with pytest.raises(ContentError, match=r"content/a\.md"):
        load_pages(site)


def test_title_fallbacks(tmp_path):
    files = {
        "content/index.md": "text",
        "content/blog/index.md": "text",
        "content/stem.md": "text",
        "content/h.md": "intro\n\n# *Real* `title`\n\nmore",
        "content/ft.md": "---\ntitle: FM\n---\n# Heading\n",
    }
    p = pages_of(tmp_path, files)
    assert p[""].title == "Demo"
    assert p["blog/"].title == "blog"
    assert p["stem/"].title == "stem"
    assert p["h/"].title == "Real title"
    assert "<h1>" not in p["h/"].body
    assert "<p>intro</p>" in p["h/"].body
    assert p["ft/"].title == "FM"
    assert "<h1>Heading</h1>" in p["ft/"].body


def test_only_first_h1_removed(tmp_path):
    p = one(tmp_path, "# One\n\n# Two\n")
    assert p.title == "One"
    assert "<h1>Two</h1>" in p.body


def test_description_frontmatter_wins(tmp_path):
    assert one(tmp_path, FM.format("description: D") + "Para").description == "D"


def test_description_plain_text(tmp_path):
    text = "# T\n\nFirst *para* with [link](u) ![alt](x.png) and `code`\nnext.\n"
    assert one(tmp_path, text).description == "First para with link and code next."
    assert one(tmp_path, "a  \nb").description == "a b"


@pytest.mark.parametrize(
    "text", ["- item\n\n> quote\n", "# only heading\n", "- a\n- b\n"]
)
def test_description_skips_nested_paragraphs(tmp_path, text):
    assert one(tmp_path, text).description == ""


def test_description_nested_then_top_level(tmp_path):
    assert one(tmp_path, "> quote\n\nTop.\n").description == "Top."


def test_description_truncated_at_word(tmp_path):
    d = one(tmp_path, "word " * 60).description
    assert len(d) <= 160
    assert d.endswith("word…")


def test_description_long_word(tmp_path):
    d = one(tmp_path, "x" * 300).description
    assert d == "x" * 159 + "…"


def test_description_boundary_at_cut(tmp_path):
    text = "a" * 158 + " " + "b" * 50
    assert one(tmp_path, text).description == "a" * 158 + "…"


def test_description_exactly_160_uncut(tmp_path):
    text = "a" * 79 + " " + "b" * 80
    assert one(tmp_path, text).description == text
    assert len(one(tmp_path, text + "c").description) <= 160


def test_body_and_source(tmp_path):
    p = one(tmp_path, FM.format("title: T") + "| a | b |\n|---|---|\n| 1 | 2 |\n")
    assert isinstance(p.body, Markup)
    assert "<table>" in p.body
    assert (p.source.startswith("| a | b |"), "title" in p.source) == (True, False)


def test_raw_html_passes_through(tmp_path):
    assert "<b>raw</b>" in one(tmp_path, "<b>raw</b> html").body


def test_template_choice(tmp_path):
    files = {
        "templates/blog.html": "",
        "content/blog/index.md": "i",
        "content/blog/a.md": "a",
        "content/blog/b.md": FM.format("template: custom.html"),
        "content/about.md": "x",
        "content/misc/c.md": "c",
    }
    p = pages_of(tmp_path, files)
    assert p["blog/a/"].template == "blog.html"
    assert p["blog/"].template == "blog.html"
    assert p["blog/b/"].template == "custom.html"
    assert p["about/"].template == "page.html"
    assert p["misc/c/"].template == "page.html"


def test_dates(tmp_path):
    p = one(tmp_path, FM.format("date: 2024-03-01\nupdated: 2024-03-02T10:00:00"))
    assert (p.date, p.updated) == (
        date(2024, 3, 1),
        datetime(2024, 3, 2, 10, tzinfo=UTC),
    )
    assert not isinstance(p.date, datetime)


def test_iso_string_dates(tmp_path):
    q = one(tmp_path, FM.format("date: '2024-03-01'\nupdated: '2024-03-02T10:00:00'"))
    assert (q.date, q.updated) == (
        date(2024, 3, 1),
        datetime(2024, 3, 2, 10, tzinfo=UTC),
    )


def test_aware_datetime_kept_and_undated(tmp_path):
    r = one(tmp_path, FM.format("date: 2024-03-02T10:00:00+02:00"))
    assert r.date.utcoffset().total_seconds() == 7200
    assert one(tmp_path, "x").date is None


def test_defaults(tmp_path):
    p = one(tmp_path, "x", lang="cs")
    assert (p.lang, p.image, p.noindex, p.alternates, p.collection) == (
        "cs",
        "",
        False,
        {},
        "",
    )


def test_overrides(tmp_path):
    q = one(tmp_path, FM.format("lang: de\nimage: i.png\nnoindex: true"))
    assert (q.lang, q.image, q.noindex) == ("de", "i.png", True)


def test_alternates(tmp_path):
    alt = {"en": "en/index.html"}
    assert one(tmp_path, FM.format(f"alternates: {alt}")).alternates == alt


def test_deterministic(tmp_path):
    site = make_site(tmp_path, TREE)
    a, b = load_pages(site), load_pages(site)
    assert [(p.url, p.title, p.description, str(p.body)) for p in a] == [
        (p.url, p.title, p.description, str(p.body)) for p in b
    ]


def test_collections_order(tmp_path):
    files = {
        "content/index.md": "h",
        "content/about.md": "a",
        "content/blog/index.md": "i",
        "content/blog/d.md": FM.format("date: 2024-03-01"),
        "content/blog/dt.md": FM.format("date: 2024-05-02T10:00:00"),
        "content/blog/deep/x.md": FM.format("date: 2023-01-01"),
        "content/blog/u2.md": "Z",
        "content/blog/u1.md": "A",
        "content/only/index.md": "i",
        "content/news/a.md": FM.format("date: 2024-03-01T00:00:00+00:00"),
        "content/news/b.md": FM.format("date: 2024-03-01"),
    }
    cols = build_collections(load_pages(make_site(tmp_path, files)))
    assert [p.url for p in cols["blog"]] == [
        "blog/dt/",
        "blog/d/",
        "blog/deep/x/",
        "blog/u1/",
        "blog/u2/",
    ]
    assert [p.url for p in cols["news"]] == ["news/a/", "news/b/"]  # tie: title
    assert set(cols) == {"blog", "news"}


def test_collections_tie_breaks_on_url(tmp_path):
    files = {
        "content/c/a.md": FM.format("title: T\ndate: 2024-01-01"),
        "content/c/b.md": FM.format("title: T\ndate: 2024-01-01"),
    }
    cols = build_collections(load_pages(make_site(tmp_path, files)))
    assert [p.url for p in cols["c"]] == ["c/a/", "c/b/"]


def test_load_data(tmp_path):
    files = {
        "data/tools.yaml": "- name: biston",
        "data/meta.json": '{"v": 1}',
        "data/conf.toml": "k = 2",
        "data/other.yml": "a: 1",
        "data/empty.yaml": "",
        "data/notes.txt": "ignored",
        "data/sub/deep.json": "{",
    }
    assert load_data(make_site(tmp_path, files)) == {
        "tools": [{"name": "biston"}],
        "meta": {"v": 1},
        "conf": {"k": 2},
        "other": {"a": 1},
        "empty": None,
    }


@pytest.mark.parametrize(
    ("name", "text"),
    [
        ("x.toml", "k = "),
        ("x.json", "{"),
        ("x.yaml", "a: [unclosed"),
        ("x.yml", "a: [unclosed"),
        ("x.json", b"\xff\xfe\x00"),
    ],
)
def test_data_parse_error(tmp_path, name, text):
    with pytest.raises(ContentError, match=f"data/{name}"):
        load_data(make_site(tmp_path, {f"data/{name}": text}))


def test_data_duplicate_stem(tmp_path):
    site = make_site(tmp_path, {"data/tools.yaml": "a: 1", "data/tools.json": "{}"})
    with pytest.raises(ContentError) as exc:
        load_data(site)
    assert "data/tools.yaml" in str(exc.value)
    assert "data/tools.json" in str(exc.value)
