from __future__ import annotations

from pathlib import Path

import pytest

from deedum import ConfigError
from deedum.check import Finding, _srcset_urls, check_folder

HEAD = (
    "<title>T</title>"
    '<link rel="canonical" href="https://e.test/">'
    '<meta name="description" content="d">'
    '<meta property="og:image" content="https://e.test/i.png">'
)

DEMO = "/demo/"
ROOT = "/"


def page(body: str = "", head: str = HEAD) -> str:
    return f"<!doctype html><html><head>{head}</head><body>{body}</body></html>"


def put(folder: Path, rel: str, text: str | bytes) -> Path:
    path = folder / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(text, bytes):
        path.write_bytes(text)
    else:
        path.write_text(text, encoding="utf-8")
    return path


def lines(folder: Path, base_path: str = ROOT) -> list[str]:
    return [str(f) for f in check_folder(folder, base_path).findings]


def bad_folder(tmp_path: Path, kind: str) -> Path:
    """A folder ``check_folder`` must refuse, of the given ``kind``."""
    target = tmp_path / "t"
    if kind == "file":
        target.write_text("x")
    elif kind == "symlink":
        real = tmp_path / "real"
        real.mkdir()
        target.symlink_to(real)
    elif kind == "git":
        target = tmp_path / ".git" / "o"
        target.mkdir(parents=True)
    return target


@pytest.fixture
def out(tmp_path: Path) -> Path:
    folder = tmp_path / "out"
    folder.mkdir()
    return folder


def test_clean_page_has_no_findings(out):
    put(out, "index.html", page())
    report = check_folder(out)
    assert report.pages == 1
    assert report.findings == []
    assert report.summary == "checked 1 pages: 0 errors, 0 warnings"


def test_empty_folder_checks_zero_pages(out):
    assert check_folder(out).summary == "checked 0 pages: 0 errors, 0 warnings"


def test_each_metadata_kind(out):
    put(out, "a/index.html", page(head="<title> </title>"))
    assert lines(out) == [
        "error a/index.html: missing canonical link",
        "error a/index.html: missing or empty <title>",
        "warning a/index.html: missing meta description",
        "warning a/index.html: missing og:image",
    ]


def test_missing_title_element_and_blank_canonical(out):
    put(out, "index.html", page(head='<link rel="canonical" href=" ">'))
    found = lines(out)
    assert "error index.html: missing or empty <title>" in found
    assert "error index.html: missing canonical link" in found


def test_noindex_page_skips_metadata_but_not_links(out):
    head = '<meta name="robots" content="noindex">'
    put(out, "404.html", page('<a href="/gone/">x</a>{{ y }}', head=head))
    found = lines(out)
    assert len(found) == 2
    assert all(f.startswith("error 404.html: line 1:") for f in found)


def test_counts_split_errors_and_warnings(out):
    put(out, "index.html", page(head=HEAD.replace("<title>T</title>", "")))
    report = check_folder(out)
    assert (report.errors, report.warnings) == (1, 0)


@pytest.mark.parametrize(
    ("href", "base", "ok"),
    [
        ("about/", "/", True),
        ("/about/", "/", True),
        ("/about", "/", True),
        ("/demo/about/", "/demo/", True),
        ("/demo", "/demo/", True),
        ("/demo/about/?q=1#x", "/demo/", True),
        ("/about/", "/demo/", False),
        ("/", "/demo/", False),
        ("nowhere/", "/", False),
        ("about/index.html", "/", True),
        ("about%20us/", "/", True),
        ("about/%2e%2e/%2e%2e/x", "/", False),
        ("../../../etc/passwd", "/", False),
        ("/demo/../../etc/passwd", "/demo/", False),
        ("mailto:a@b", "/", True),
        ("https://x.test/y", "/", True),
        ("data:,x", "/", True),
        ("javascript:void(0)", "/", True),
        ("//cdn.test/x", "/", True),
        ("#top", "/", True),
        ("?q=1", "/", True),
        ("", "/", True),
        ("about/%00", "/", False),
    ],
)
def test_link_resolution(out, href, base, ok):
    put(out, "about/index.html", page())
    put(out, "about us/index.html", page())
    put(out, "index.html", page(f'<a href="{href}">x</a>'))
    found = [f for f in lines(out, base) if "line" in f]
    assert (found == []) is ok, found


def test_error_kinds_in_messages(out):
    put(out, "index.html", page('<a href="/a/">a</a><a href="b/">b</a>'))
    put(out, "x/y/index.html", page('<a href="../../../../z">z</a>'))
    assert lines(out, DEMO) == [
        "error index.html: line 1: /a/ is outside base path /demo/",
        "error index.html: line 1: b/ is missing",
        "error x/y/index.html: line 1: ../../../../z climbs above the site root",
    ]


@pytest.mark.parametrize("depth", [0, 1, 2])
def test_relative_links_at_every_depth(out, depth):
    here = "d/" * depth
    put(out, "t.css", "x")
    up = "../" * depth
    put(out, f"{here}index.html", page(f'<link rel="stylesheet" href="{up}t.css">'))
    assert lines(out) == []


def test_folder_target_needs_an_index(out):
    (out / "empty").mkdir()
    put(out, "index.html", page('<a href="empty/">e</a>'))
    assert lines(out) == ["error index.html: line 1: empty/ is missing"]


@pytest.mark.parametrize(
    "tag",
    [
        '<a href="m.png">',
        '<link href="m.png">',
        '<area href="m.png">',
        '<img src="m.png">',
        '<script src="m.png"></script>',
        '<iframe src="m.png"></iframe>',
        '<source src="m.png">',
        '<audio src="m.png"></audio>',
        '<video src="m.png"></video>',
        '<video poster="m.png"></video>',
        '<track src="m.png">',
        '<embed src="m.png">',
        '<object data="m.png"></object>',
        '<img srcset="m.png 1x">',
        '<source srcset="m.png">',
    ],
)
def test_every_link_attribute_is_checked(out, tag):
    put(out, "index.html", page(tag))
    assert lines(out) == ["error index.html: line 1: m.png is missing"]


def test_other_attributes_are_not_links(out):
    put(out, "index.html", page('<div src="m.png" data="m.png"></div><p href="x">'))
    assert lines(out) == []


def test_srcset_reports_only_the_missing_candidate(out):
    put(out, "a.png", "x")
    put(out, "index.html", page('<img srcset="a.png 1x, b.png 2x">'))
    assert lines(out) == ["error index.html: line 1: b.png is missing"]


@pytest.mark.parametrize(
    ("value", "urls"),
    [
        ("a.png 1x, b.png 2x", ["a.png", "b.png"]),
        ("a.png 100w", ["a.png"]),
        ("a.png, b.png 2x", ["a.png", "b.png"]),
        ("data:,x 1x, c.png", ["data:,x", "c.png"]),
        ("  ", []),
        ("", []),
    ],
)
def test_srcset_parsing(value, urls):
    assert _srcset_urls(value) == urls


def test_leftover_syntax_in_text_and_attributes(out):
    put(out, "index.html", page('<p title="{% if %}">a {{ x }}</p>'))
    found = lines(out)
    assert any("in attribute 'title' of <p>" in f for f in found)
    assert any(f.endswith("in text") for f in found)


@pytest.mark.parametrize("tag", ["pre", "code", "script", "style", "textarea"])
def test_leftover_syntax_is_ignored_in_quiet_tags(out, tag):
    put(out, "index.html", page(f"<{tag}>{{{{ x }}}} {{% y %}}</{tag}><p>ok</p>"))
    assert lines(out) == []


def test_leftover_syntax_after_a_quiet_tag_counts_again(out):
    put(out, "index.html", page("<pre><code>{{ a }}</code></pre><p>{{ b }}</p>"))
    assert len(lines(out)) == 1


def test_stray_end_tags_do_not_underflow(out):
    put(out, "index.html", page("</pre></code><p>{{ b }}</p>"))
    assert len(lines(out)) == 1


def test_malformed_and_binary_html_never_raises(out):
    put(out, "a.html", "<html><head><title>x<body><a href='/unclosed")
    put(out, "b.html", b"\xff\xfe<title>\x80</title><a href=\xc3(>")
    put(out, "c.html", "<<<>>><a href=")
    report = check_folder(out)
    assert report.pages == 3


def test_line_numbers_and_order_are_deterministic(out):
    put(out, "z.html", page('<a href="/b/">b</a>'))
    put(out, "a.html", page("\n\n<a href='n/'>n</a>\n<a href='m/'>m</a>"))
    first = lines(out)
    assert first == lines(out)
    assert first == [
        "error a.html: line 3: n/ is missing",
        "error a.html: line 4: m/ is missing",
        "error z.html: line 1: /b/ is missing",
    ]


def test_only_lowercase_html_files_count(out):
    put(out, "a.HTML", "x")
    put(out, "b.htm", "x")
    put(out, "c.txt", "x")
    assert check_folder(out).pages == 0


def test_symlinks_and_dot_folders_are_skipped(out, tmp_path):
    elsewhere = tmp_path / "else"
    put(elsewhere, "x.html", "<p>{{ bad }}</p>")
    (out / "link.html").symlink_to(elsewhere / "x.html")
    (out / "dir").symlink_to(elsewhere)
    put(out, ".hidden/h.html", "<p>{{ bad }}</p>")
    assert check_folder(out).pages == 0


def test_symlinked_link_targets_count_as_missing(out, tmp_path):
    elsewhere = tmp_path / "else"
    put(elsewhere, "x.png", "x")
    (out / "x.png").symlink_to(elsewhere / "x.png")
    (out / "d").symlink_to(elsewhere)
    put(out, "index.html", page('<img src="x.png"><img src="d/x.png">'))
    assert len(lines(out)) == 2


def test_dangling_target_resolves_to_missing(out):
    put(out, "index.html", page('<a href="a/../b">b</a>'))
    assert lines(out) == ["error index.html: line 1: a/../b is missing"]


@pytest.mark.parametrize("kind", ["missing", "file", "symlink", "git"])
def test_bad_folders_are_config_errors(tmp_path, kind):
    with pytest.raises(ConfigError, match="cannot check"):
        check_folder(bad_folder(tmp_path, kind))


def test_finding_without_line_prints_no_line():
    assert str(Finding("a.html", 0, "warning", "x")) == "warning a.html: x"
