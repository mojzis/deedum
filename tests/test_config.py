from __future__ import annotations

from pathlib import Path

import pytest

from deedum import ConfigError, load_site

E_URL = "https://e.org"
ENV_URL = "https://env.org"
FLAG_URL = "https://flag.org"
FILE_URL = "https://file.org"
PATH_URL = "https://x.io/p"
OK_URL = "https://ok.org"
REAL_URL = "https://real.org"
DEMO_PATH = "/demo/"
BASE = 'title = "Demo"\nbase_url = "https://e.org/"\n'


def write(root: Path, text: str, name: str = "deedum.toml") -> Path:
    path = root / name
    path.write_text(text, encoding="utf-8")
    return path


def test_defaults(tmp_path):
    write(tmp_path, BASE + 'base_path = "demo"\n')
    s = load_site(tmp_path, environ={})
    assert (s.base_url, s.base_path, s.lang, s.out) == (
        E_URL,
        "/demo/",  # zorilla: ignore -- URL path, not an external resource
        "en",
        "_site",
    )
    assert (s.content, s.templates, s.static, s.data) == (
        "content",
        "templates",
        "static",
        "data",
    )
    assert (s.relative_links, s.llms, s.theme_color, s.root) == (
        False,
        False,
        "#ffffff",
        tmp_path,
    )
    assert s.feeds == () and s.app == ""


def test_load_all_keys(tmp_path):
    write(
        tmp_path,
        BASE
        + 'feeds = ["blog"]\nrobots_extra_sitemaps = ["https://a.org/sitemap.xml"]\n'
        'relative_links = true\napp = "site:Site"\ntwitter = "mojzis"\n',
    )
    s = load_site(tmp_path, environ={})
    assert s.feeds == ("blog",) and s.relative_links
    assert s.robots_extra_sitemaps == ("https://a.org/sitemap.xml",)
    assert s.twitter == "@mojzis"


def test_pyproject_fallback(tmp_path):
    write(tmp_path, '[project]\nname = "x"\n\n[tool.deedum]\n' + BASE, "pyproject.toml")
    s = load_site(tmp_path, environ={})
    assert s.title == "Demo" and s.root == tmp_path


def test_pyproject_without_table_and_no_files(tmp_path):
    with pytest.raises(ConfigError, match="no deedum config") as ei:
        load_site(tmp_path, environ={})
    assert str(tmp_path) in str(ei.value)
    write(tmp_path, '[project]\nname = "x"\n', "pyproject.toml")
    with pytest.raises(ConfigError, match=r"pyproject\.toml"):
        load_site(tmp_path, environ={})


def test_both_configs(tmp_path):
    write(tmp_path, BASE)
    write(tmp_path, "[tool.deedum]\n" + BASE, "pyproject.toml")
    with pytest.raises(ConfigError) as ei:
        load_site(tmp_path, environ={})
    assert "deedum.toml" in str(ei.value) and "pyproject.toml" in str(ei.value)


def test_deedum_toml_wins_over_pyproject_without_table(tmp_path):
    write(tmp_path, BASE)
    write(tmp_path, '[project]\nname = "x"\n', "pyproject.toml")
    assert load_site(tmp_path, environ={}).title == "Demo"


def test_unrelated_malformed_pyproject_ignored_when_deedum_toml_exists(tmp_path):
    write(tmp_path, BASE)
    write(tmp_path, "[[[", "pyproject.toml")
    assert load_site(tmp_path, environ={}).title == "Demo"


def test_malformed_toml(tmp_path):
    write(tmp_path, 'title = "a"\nbad\n')
    with pytest.raises(ConfigError, match=r"deedum\.toml.*malformed TOML.*line 2"):
        load_site(tmp_path, environ={})


def test_non_utf8(tmp_path):
    (tmp_path / "deedum.toml").write_bytes(b'title = "\xff\xfe"')
    with pytest.raises(ConfigError, match=r"deedum\.toml.*UTF-8"):
        load_site(tmp_path, environ={})


def test_unreadable_config(tmp_path):
    (tmp_path / "deedum.toml").mkdir()
    with pytest.raises(ConfigError, match=r"deedum\.toml.*cannot read"):
        load_site(tmp_path, config=tmp_path / "deedum.toml", environ={})


def test_tool_deedum_not_a_table(tmp_path):
    write(tmp_path, "[tool]\ndeedum = 3\n", "pyproject.toml")
    with pytest.raises(ConfigError, match=r"pyproject\.toml.*table"):
        load_site(tmp_path, environ={})


def test_unknown_key_with_hint(tmp_path):
    write(tmp_path, BASE + 'basepath = "/a/"\n')
    with pytest.raises(ConfigError) as ei:
        load_site(tmp_path, environ={})
    assert "deedum.toml" in str(ei.value) and "basepath" in str(ei.value)
    assert "base_path" in (ei.value.hint or "")


def test_unknown_key_without_close_match(tmp_path):
    write(tmp_path, BASE + "zzzzzzzzzz = 1\n")
    with pytest.raises(ConfigError) as ei:
        load_site(tmp_path, environ={})
    assert ei.value.hint is None


@pytest.mark.parametrize(
    ("line", "key", "word"),
    [
        ('relative_links = "yes"', "relative_links", "bool"),
        ("llms = 1", "llms", "bool"),
        ("lang = true", "lang", "string"),
        ('feeds = "blog"', "feeds", "array"),
        ("feeds = ['a', 2]", "feeds", "integer"),
    ],
)
def test_wrong_types(tmp_path, line, key, word):
    write(tmp_path, BASE + line + "\n")
    with pytest.raises(ConfigError) as ei:
        load_site(tmp_path, environ={})
    msg = str(ei.value)
    assert "deedum.toml" in msg and key in msg and word in msg


@pytest.mark.parametrize(
    "text",
    [
        f'base_url = "{E_URL}"\n',
        f'title = ""\nbase_url = "{E_URL}"\n',
        f'title = "  "\nbase_url = "{E_URL}"\n',
    ],
)
def test_missing_or_empty_title(tmp_path, text):
    write(tmp_path, text)
    with pytest.raises(ConfigError, match=r"key 'title'"):
        load_site(tmp_path, environ={})


@pytest.mark.parametrize("text", ['title = "t"\n', 'title = "t"\nbase_url = ""\n'])
def test_missing_or_empty_base_url(tmp_path, text):
    write(tmp_path, text)
    with pytest.raises(ConfigError, match=r"deedum\.toml.*base_url"):
        load_site(tmp_path, environ={})


def test_base_url_only_from_env(tmp_path):
    write(tmp_path, 'title = "t"\n')
    s = load_site(tmp_path, environ={"DEEDUM_BASE_URL": ENV_URL})
    assert s.base_url == ENV_URL


def test_base_url_precedence(tmp_path):
    write(tmp_path, f'title = "t"\nbase_url = "{FILE_URL}"\n')
    env = {"DEEDUM_BASE_URL": ENV_URL}
    assert load_site(tmp_path, environ={}).base_url == FILE_URL
    assert load_site(tmp_path, environ=env).base_url == ENV_URL
    assert load_site(tmp_path, environ=env, base_url=FLAG_URL).base_url == FLAG_URL
    assert load_site(tmp_path, environ={"DEEDUM_BASE_URL": ""}).base_url == FILE_URL


def test_base_path_precedence(tmp_path):
    write(tmp_path, BASE + 'base_path = "file"\n')
    env = {"DEEDUM_BASE_PATH": "env"}
    assert load_site(tmp_path, environ={}).base_path == "/file/"
    assert load_site(tmp_path, environ=env).base_path == "/env/"
    assert load_site(tmp_path, environ=env, base_path="flag").base_path == "/flag/"
    assert load_site(tmp_path, environ={"DEEDUM_BASE_PATH": ""}).base_path == "/file/"
    assert load_site(tmp_path, environ=env, base_path="").base_path == "/"


def test_invalid_override_names_source(tmp_path):
    write(tmp_path, BASE)
    with pytest.raises(ConfigError, match="DEEDUM_BASE_URL") as ei:
        load_site(tmp_path, environ={"DEEDUM_BASE_URL": "env.org"})
    assert "deedum.toml" not in str(ei.value)
    with pytest.raises(ConfigError, match="--base-url"):
        load_site(tmp_path, environ={}, base_url=PATH_URL)


def test_invalid_file_base_url_names_file_and_key(tmp_path):
    write(tmp_path, 'title = "t"\nbase_url = "mojzis.github.io"\n')
    with pytest.raises(ConfigError, match=r"deedum\.toml.*base_url"):
        load_site(tmp_path, environ={})


def test_valid_override_replaces_invalid_file_value(tmp_path):
    write(tmp_path, 'title = "t"\nbase_url = "nope"\n')
    s = load_site(tmp_path, environ={}, base_url=OK_URL)
    assert s.base_url == OK_URL


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("", "/"),
        ("aesop", "/aesop/"),
        ("/aesop", "/aesop/"),
        ("//a//b//", "/a/b/"),
        ("/", "/"),
    ],
)
def test_base_path_normalisation(tmp_path, raw, expected):
    write(tmp_path, BASE)
    assert load_site(tmp_path, environ={}, base_path=raw).base_path == expected


def test_relative_sitemap_rejected(tmp_path):
    write(tmp_path, BASE + 'robots_extra_sitemaps = ["/sitemap.xml"]\n')
    with pytest.raises(ConfigError, match=r"deedum\.toml.*robots_extra_sitemaps"):
        load_site(tmp_path, environ={})


@pytest.mark.parametrize("app", ["site:Site", "pkg.mod:App_1"])
def test_app_ok(tmp_path, app):
    write(tmp_path, BASE + f'app = "{app}"\n')
    assert load_site(tmp_path, environ={}).app == app


@pytest.mark.parametrize("app", ["site", "site.Site", "1x:Y", "a:b:c", "a:"])
def test_app_bad(tmp_path, app):
    write(tmp_path, BASE + f'app = "{app}"\n')
    with pytest.raises(ConfigError, match=r"deedum\.toml.*app"):
        load_site(tmp_path, environ={})


def test_twitter_at_added_and_kept(tmp_path):
    write(tmp_path, BASE + 'twitter = "@mojzis"\n')
    assert load_site(tmp_path, environ={}).twitter == "@mojzis"


def test_twitter_invalid(tmp_path):
    write(tmp_path, BASE + 'twitter = "a b"\n')
    with pytest.raises(ConfigError, match=r"deedum\.toml.*twitter"):
        load_site(tmp_path, environ={})


def test_explicit_plain_config(tmp_path):
    cfg = write(tmp_path / ".", BASE, "site.toml")
    (tmp_path / "deedum.toml").write_text("garbage = [", encoding="utf-8")
    s = load_site(tmp_path / "elsewhere", config=cfg, environ={})
    assert s.title == "Demo" and s.root == tmp_path


def test_explicit_pyproject(tmp_path):
    cfg = write(tmp_path, "[tool.deedum]\n" + BASE, "pyproject.toml")
    assert load_site(tmp_path, config=cfg, environ={}).root == tmp_path


def test_explicit_pyproject_without_table(tmp_path):
    cfg = write(tmp_path, "[project]\nname='x'\n", "pyproject.toml")
    with pytest.raises(ConfigError, match=r"pyproject\.toml.*tool\.deedum"):
        load_site(tmp_path, config=cfg, environ={})


def test_real_environ_used_by_default(tmp_path, monkeypatch):
    write(tmp_path, 'title = "t"\n')
    monkeypatch.setenv("DEEDUM_BASE_URL", REAL_URL)
    assert load_site(tmp_path).base_url == REAL_URL
