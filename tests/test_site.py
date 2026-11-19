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


@pytest.mark.parametrize("field", ["base_url", "base_path", "twitter"])
def test_non_string_fields_raise_config_error(field):
    with pytest.raises(ConfigError, match=rf"Site\({field}\)"):
        make(**{field: 1})


@pytest.mark.parametrize("bad", ["../x", "a/b", ".git", "", ".hidden", "a b", "a\\b"])
def test_unsafe_feed_names_rejected(bad):
    with pytest.raises(ConfigError, match="feeds"):
        make(feeds=("blog", bad))


def test_non_string_feed_name_rejected():
    with pytest.raises(ConfigError, match="feeds"):
        make(feeds=(1,))


@pytest.mark.parametrize("name", ["blog", "_n", "a.b-c", "9"])
def test_safe_feed_names_accepted(name):
    assert make(feeds=(name,)).feeds == (name,)


@pytest.mark.parametrize("bad", ["white", "#12345", "#ggg", "ffffff", "#ffff", 5])
def test_invalid_theme_color(bad):
    with pytest.raises(ConfigError, match="theme_color"):
        make(theme_color=bad)


@pytest.mark.parametrize("good", ["#fff", "#FFFFFF", "#1a73e8"])
def test_valid_theme_color(good):
    assert make(theme_color=good).theme_color == good


@pytest.mark.parametrize("name", ["blog\n", "CNAME"])
def test_feed_name_trailing_newline_and_cname_rejected(name):
    with pytest.raises(ConfigError, match="feeds"):
        make(feeds=(name,))


def test_theme_color_trailing_newline_rejected():
    with pytest.raises(ConfigError, match="theme_color"):
        make(theme_color="#fff\n")


@pytest.mark.parametrize("field", ["feeds", "robots_extra_sitemaps"])
def test_bare_string_list_fields_rejected(field):
    with pytest.raises(ConfigError, match=field):
        make(**{field: "blog"})
