from __future__ import annotations

import pytest

from deedum import ConfigError, Site

E_URL = "https://e.org"
E_SLASH = "https://e.org/"
PATH_URL = "https://x.io/aesop"
AESOP = "/aesop/"
TOOLS = "/aesop/tools/"


def make(**kw) -> Site:
    kw.setdefault("title", "t")
    kw.setdefault("base_url", "https://mojzis.github.io")
    kw.setdefault("base_path", "/aesop/")
    return Site(**kw)


def test_reference_case():
    s = make()
    assert s.absolute("tools/biston/") == "https://mojzis.github.io/aesop/tools/biston/"
    assert s.url("tools/biston/") == "/aesop/tools/biston/"
    assert s.url("") == "/aesop/"
    assert s.absolute("") == "https://mojzis.github.io/aesop/"


@pytest.mark.parametrize(
    "u",
    ["https://x.org/a", "mailto:a@b.c", "//cdn.x/y.js", "#top", "data:text/plain,hi"],
)
def test_passthrough(u):
    s = make(relative_links=True)
    assert s.url(u) == u
    assert s.url(u, current="a/") == u
    assert s.absolute(u) == u


def test_leading_slash_equivalence():
    s = make()
    assert s.url("/tools/") == s.url("tools/") == TOOLS  # zorilla: ignore -- URL path
    assert s.url("/") == AESOP  # zorilla: ignore -- URL path


def test_query_fragment_kept():
    s = make()
    assert s.url("a/?x=1#f") == "/aesop/a/?x=1#f"
    assert s.url("a?x=1") == "/aesop/a?x=1"
    assert s.url("?x=1") == "/aesop/?x=1"
    assert s.absolute("a#f") == "https://mojzis.github.io/aesop/a#f"


def test_trailing_slash_never_added():
    s = make()
    assert s.url("tools") == "/aesop/tools"
    assert s.url("tools/") == "/aesop/tools/"


@pytest.mark.parametrize("bp", ["/", "/aesop/"])
@pytest.mark.parametrize(
    ("target", "current", "expected"),
    [
        ("tools/biston/", "", "tools/biston/"),
        ("tools/biston/", "about/", "../tools/biston/"),
        ("tools/biston/", "blog/hello/", "../../tools/biston/"),
        ("", "blog/hello/", "../../"),
        ("blog/hello/", "blog/hello/", "./"),
        ("style.css", "404.html", "style.css"),
        ("style.css", "blog/hello/", "../../style.css"),
        ("/a/b?x=1#f", "a/", "b?x=1#f"),
        ("", "", "./"),
    ],
)
def test_relative_links(bp, target, current, expected):
    s = make(base_url=E_URL, base_path=bp, relative_links=True)
    assert s.url(target, current=current) == expected
    assert s.absolute("x/") == f"https://e.org{bp}x/"


def test_current_none_is_root_relative():
    s = make(relative_links=True)
    assert s.url("tools/") == "/aesop/tools/"


def test_current_ignored_without_relative_links():
    assert make().url("tools/", current="a/b/") == "/aesop/tools/"


def test_direct_normalisation():
    s = make(base_path="aesop", base_url=E_SLASH, twitter="me", feeds=["blog"])
    assert (s.base_path, s.base_url, s.twitter, s.feeds) == (
        "/aesop/",  # zorilla: ignore -- URL path
        E_URL,
        "@me",
        ("blog",),
    )
    assert hash(s) is not None


@pytest.mark.parametrize(
    "bad",
    [
        "e.org",
        "ftp://e.org",
        "https://e.org/p",
        "https://e.org?x",
        "https://e.org:bad",
        "https://u:p@h.io",
        "https://u@h.io",
        "https://h.io:",
    ],
)
def test_invalid_base_url(bad):
    with pytest.raises(ConfigError, match="base_url"):
        make(base_url=bad)


def test_path_in_base_url_hints_base_path():
    with pytest.raises(ConfigError) as ei:
        make(base_url=PATH_URL)
    assert "base_path" in (ei.value.hint or "")


def test_invalid_twitter():
    with pytest.raises(ConfigError, match="twitter"):
        make(twitter="a b")
