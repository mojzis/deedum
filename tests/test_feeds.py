from __future__ import annotations

import datetime as dt
import xml.etree.ElementTree as ET
from pathlib import Path, PurePosixPath

import pytest
from markupsafe import Markup

from deedum import Page, Site
from deedum.extras.feeds import rfc3339, write_feeds

A = "{http://www.w3.org/2005/Atom}"
XML_BASE = "{http://www.w3.org/XML/1998/namespace}base"
NOW = dt.datetime(2026, 11, 18, 12, 0, tzinfo=dt.UTC)


def naive(y: int, m: int, d: int, hh: int = 0, mm: int = 0):
    return dt.datetime(y, m, d, hh, mm)  # noqa: DTZ001 -- naive on purpose


def make_site(**kw) -> Site:
    kw.setdefault("feeds", ("blog",))
    return Site(title="T", base_url="https://ex.org", base_path="/sub/", **kw)


def post(slug: str, date=dt.date(2026, 1, 1), collection="blog", **kw) -> Page:
    kw.setdefault("title", slug)
    return Page(
        url=f"{collection}/{slug}/",
        output=f"{collection}/{slug}/index.html",
        description=kw.pop("description", ""),
        body=kw.pop("body", Markup("<p>body</p>")),
        source="",
        template="page.html",
        date=date,
        collection=collection,
        **kw,
    )


def build(tmp_path: Path, pages, name="blog", **kw) -> ET.Element:
    out = tmp_path / "out"
    out.mkdir(exist_ok=True)
    write_feeds(make_site(**kw), pages, out, NOW)
    return ET.parse(out / name / "feed.xml").getroot()  # noqa: S314 -- our own file


def slugs(root: ET.Element) -> list[str]:
    return [PurePosixPath(i).name for i in entry_ids(root)]


def href(el: ET.Element | None) -> str | None:
    assert el is not None
    return el.get("href")


def entry_ids(root: ET.Element) -> list[str]:
    return [e.findtext(f"{A}id", "") for e in root.findall(f"{A}entry")]


def test_atom_structure(tmp_path):
    root = build(tmp_path, [post("a", description="sum", updated=dt.date(2026, 2, 2))])
    assert root.tag == f"{A}feed"
    got = [root.findtext(f"{A}{t}") for t in ("id", "title", "author/" + A + "name")]
    assert got == ["https://ex.org/sub/blog/feed.xml", "T: blog", "T"]
    links = {e.get("rel"): e.get("href") for e in root.findall(f"{A}link")}
    assert links == {
        "self": "https://ex.org/sub/blog/feed.xml",
        "alternate": "https://ex.org/sub/blog/",
    }


def test_declaration_and_encoding(tmp_path):
    build(tmp_path, [post("a")])
    head = (tmp_path / "out/blog/feed.xml").read_bytes()[:40]
    assert head.startswith(b"<?xml version='1.0' encoding='utf-8'?>")


A_URL = "https://ex.org/sub/blog/a/"


def test_entry_fields(tmp_path):
    page = post("a", description="sum", updated=dt.date(2026, 2, 2))
    (entry,) = build(tmp_path, [page]).findall(f"{A}entry")
    got = [
        entry.findtext(f"{A}id"),
        href(entry.find(f"{A}link")),
        entry.findtext(f"{A}published"),
        entry.findtext(f"{A}updated"),
        entry.findtext(f"{A}summary"),
    ]
    assert got == [A_URL, A_URL, "2026-01-01T00:00:00Z", "2026-02-02T00:00:00Z", "sum"]


def test_entry_content_carries_html_and_base(tmp_path):
    (entry,) = build(tmp_path, [post("a")]).findall(f"{A}entry")
    content = entry.find(f"{A}content")
    assert content is not None
    assert (content.get("type"), content.get(XML_BASE)) == ("html", A_URL)
    assert content.text == "<p>body</p>"


def test_no_summary_without_description(tmp_path):
    (entry,) = build(tmp_path, [post("a")]).findall(f"{A}entry")
    assert entry.find(f"{A}summary") is None
    assert entry.findtext(f"{A}updated") == entry.findtext(f"{A}published")


def test_author_from_site(tmp_path):
    root = build(tmp_path, [post("a")], author="Me")
    assert root.findtext(f"{A}author/{A}name") == "Me"


def test_cap_of_twenty_newest_first(tmp_path):
    pages = [post(f"p{i:02}", dt.date(2026, 1, 1) + dt.timedelta(i)) for i in range(25)]
    root = build(tmp_path, pages)
    ids = entry_ids(root)
    assert len(ids) == 20
    assert [PurePosixPath(i).name for i in (ids[0], ids[-1])] == ["p24", "p05"]
    assert root.findtext(f"{A}updated") == "2026-01-25T00:00:00Z"


def test_ties_broken_by_url_ascending(tmp_path):
    root = build(tmp_path, [post("b"), post("a"), post("c")])
    assert slugs(root) == ["a", "b", "c"]


def test_excluded_pages(tmp_path):
    pages = [
        post("ok"),
        post("undated", date=None),
        post("hidden", noindex=True),
        post("other", collection="news"),
        Page(
            url="blog/404.html",
            output="404.html",
            title="x",
            description="",
            body=Markup(""),
            source="",
            template="t",
            date=dt.date(2026, 1, 1),
            collection="blog",
        ),
    ]
    assert entry_ids(build(tmp_path, pages)) == ["https://ex.org/sub/blog/ok/"]


def test_feed_updated_is_newest_entrys_updated(tmp_path):
    pages = [
        post("new", dt.date(2026, 3, 1)),
        post("old", dt.date(2026, 1, 1), updated=dt.date(2026, 9, 9)),
    ]
    assert build(tmp_path, pages).findtext(f"{A}updated") == "2026-03-01T00:00:00Z"


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (dt.date(2026, 3, 4), "2026-03-04T00:00:00Z"),
        (naive(2026, 3, 4, 10, 5), "2026-03-04T10:05:00Z"),
        (
            dt.datetime(2026, 3, 4, 10, tzinfo=dt.timezone(dt.timedelta(hours=2))),
            "2026-03-04T08:00:00Z",
        ),
    ],
)
def test_rfc3339(value, expected):
    assert rfc3339(value) == expected


def test_mixed_dates_sort_and_end_in_z(tmp_path):
    plus2 = dt.timezone(dt.timedelta(hours=2))
    pages = [
        post("date", dt.date(2026, 3, 4)),
        post("naive", naive(2026, 3, 4, 9)),
        post("aware", dt.datetime(2026, 3, 4, 10, tzinfo=plus2)),
    ]
    root = build(tmp_path, pages)
    assert slugs(root) == ["naive", "aware", "date"]
    stamps = [e.text or "" for e in root.iter(f"{A}published")]
    assert all(s.endswith("Z") for s in stamps)


def test_empty_feed_uses_now(tmp_path):
    root = build(
        tmp_path, [post("x", collection="other")], feeds=("news",), name="news"
    )
    assert root.findall(f"{A}entry") == []
    assert root.findtext(f"{A}updated") == "2026-11-18T12:00:00Z"


def test_no_pages_at_all(tmp_path):
    root = build(tmp_path, [])
    assert root.findtext(f"{A}updated") == "2026-11-18T12:00:00Z"


def test_hostile_text_round_trips(tmp_path):
    title = "A & <b> ]]> \x0b é"
    body = Markup("<p>x &amp; ]]> \x0c é</p>")
    page = post("h", title=title, description="d\x00&<", body=body)
    (entry,) = build(tmp_path, [page]).findall(f"{A}entry")
    assert entry.findtext(f"{A}title") == "A & <b> ]]>  é"
    assert entry.findtext(f"{A}summary") == "d&<"
    assert entry.findtext(f"{A}content") == "<p>x &amp; ]]>  é</p>"


def test_control_char_in_url_is_stripped(tmp_path):
    page = post("a\x0bb")
    (entry,) = build(tmp_path, [page]).findall(f"{A}entry")
    assert href(entry.find(f"{A}link")) == A_URL.replace("a/", "ab/")


def test_duplicate_names_write_once(tmp_path):
    out = tmp_path / "out"
    out.mkdir()
    written = write_feeds(make_site(feeds=("blog", "news", "blog")), [], out, NOW)
    assert [p.relative_to(out).as_posix() for p in written] == [
        "blog/feed.xml",
        "news/feed.xml",
    ]


def test_no_feeds_writes_nothing(tmp_path):
    out = tmp_path / "out"
    out.mkdir()
    assert write_feeds(make_site(feeds=()), [post("a")], out, NOW) == []
    assert list(out.iterdir()) == []


def test_deterministic(tmp_path):
    pages = [post("a"), post("b", dt.date(2026, 2, 1))]
    first = build(tmp_path, pages)
    bytes_one = (tmp_path / "out/blog/feed.xml").read_bytes()
    build(tmp_path, pages)
    assert (tmp_path / "out/blog/feed.xml").read_bytes() == bytes_one
    assert first.tag == f"{A}feed"
