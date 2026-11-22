from __future__ import annotations

import colorsys
import datetime as dt
import hashlib
import site as stdlib_site
import sys
from pathlib import Path

import pytest

import deedum
from deedum import App, ConfigError, ContentError, DeedumError, Page, Site
from deedum.app import build, load_app

NOW = dt.datetime(2026, 1, 2, 3, 4, 5, tzinfo=dt.UTC)

APP_SRC = """
import deedum


class Site(deedum.App):
    def load_pages(self):
        pages = super().load_pages()
        for row in self.data["people"]:
            pages.append(
                self.page(
                    f"people/{row['slug']}/",
                    title=row["name"],
                    template="person.html",
                    body=f"<p>about {row['name']}</p>",
                    nick=row["slug"],
                )
            )
        return pages

    def context(self, page):
        return {"extra": "CTX-" + page.url}

    def filters(self):
        return {"shout": lambda s: str(s).upper() + "!"}

    def globals(self):
        return {"motto": "GLOBAL-MOTTO"}

    def after_build(self, out):
        (out / "marker.txt").write_text("done", encoding="utf-8")
"""


def put(path: Path, text: str = "x") -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def make_site(tmp_path: Path, app: str = "", **kw) -> Site:
    root = tmp_path / "site"
    put(root / "content" / "index.md", "# Home\n\nHello there.\n")
    put(root / "content" / "blog" / "one.md", "# One\n\nFirst post.\n")
    return Site(title="T", base_url="https://ex.test", root=root, app=app, **kw)


def snapshot(folder: Path) -> dict[str, str]:
    return {
        p.relative_to(folder).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in sorted(folder.rglob("*"))
        if p.is_file()
    }


def app_site(tmp_path: Path, source: str = APP_SRC, app: str = "site:Site") -> Site:
    site = make_site(tmp_path, app=app)
    put(site.root / "site.py", source)
    return site


def hooks_site(tmp_path: Path, body: str) -> Site:
    return app_site(tmp_path, f"import deedum\nclass Site(deedum.App):\n{body}\n")


def test_default_app_matches_plain_build(tmp_path):
    site = make_site(tmp_path)
    report = build(site, now=NOW)
    assert report.pages == 2
    assert "404.html" in report.extras
    assert (site.root / "_site" / "blog" / "one" / "index.html").is_file()


def test_each_hook_shows_in_output(tmp_path):
    site = app_site(tmp_path)
    put(
        site.root / "data" / "people.yaml",
        "- {slug: ann, name: Ann}\n- {slug: bob, name: Bob}\n",
    )
    put(
        site.root / "templates" / "person.html",
        "{{ page.title | shout }}|{{ extra }}|{{ motto }}|"
        "{{ page.nick }}|{{ page.body }}",
    )
    report = build(site, now=NOW)
    out = site.root / "_site"
    assert report.pages == 4
    ann = (out / "people" / "ann" / "index.html").read_text(encoding="utf-8")
    assert ann == "ANN!|CTX-people/ann/|GLOBAL-MOTTO|ann|<p>about Ann</p>"
    assert (out / "marker.txt").read_text(encoding="utf-8") == "done"
    assert "https://ex.test/people/bob/" in (out / "sitemap.xml").read_text()


def test_filters_and_globals_reach_the_404_page(tmp_path):
    site = app_site(tmp_path)
    put(site.root / "data" / "people.yaml", "[]\n")
    put(site.root / "templates" / "404.html", "{{ 'x' | shout }} {{ motto }}")
    build(site, now=NOW)
    assert (site.root / "_site" / "404.html").read_text() == "X! GLOBAL-MOTTO"


def test_page_helper_fields_and_meta(tmp_path):
    app = App(make_site(tmp_path))
    page = app.page("x/", title="X", date=dt.date(2026, 1, 1), tag="t", lang="cs")
    assert (page.lang, page.date, page.tag) == ("cs", dt.date(2026, 1, 1), "t")
    assert (app.page("y/", title="Y").lang, app.page("y/", title="Y").template) == (
        "en",
        "page.html",
    )


def test_page_helper_output_paths(tmp_path):
    app = App(make_site(tmp_path))
    assert app.page("", title="H").output == "index.html"
    assert app.page("a/", title="A").output == "a/index.html"
    assert app.page("a/b.html", title="B").output == "a/b.html"
    with pytest.raises(ContentError, match=r"'\.\.'"):
        app.page("../x/", title="bad")


def test_stdlib_named_module_loads_from_the_site(tmp_path):
    assert "site" in sys.modules
    app = load_app(app_site(tmp_path))
    assert type(app).__name__ == "Site"
    assert sys.modules["site"] is stdlib_site
    assert not [m for m in sys.modules if m.startswith("_deedum_app_")]


def test_package_module_and_sibling_imports(tmp_path):
    site = make_site(tmp_path, app="pkg.sub:Mine")
    put(site.root / "helpers.py", "VALUE = 'sib'\n")
    put(
        site.root / "pkg" / "sub" / "__init__.py",
        "import deedum, helpers\n"
        "class Mine(deedum.App):\n"
        "    def globals(self):\n"
        "        return {'v': helpers.VALUE}\n",
    )
    assert load_app(site).globals() == {"v": "sib"}
    assert str(site.root) not in sys.path


def test_sys_path_restored_after_failed_import(tmp_path):
    before = list(sys.path)
    site = app_site(tmp_path, "raise ImportError('x')\n")
    with pytest.raises(ConfigError):
        load_app(site)
    assert sys.path == before


@pytest.mark.parametrize(
    ("source", "app", "needle"),
    [
        ("", "nosuch:Site", "nosuch"),
        ("import deedum\n", "site:Nope", "Nope"),
        ("class Site:\n    pass\n", "site:Site", "subclass of deedum.App"),
        ("Site = 5\n", "site:Site", "subclass of deedum.App"),
        ("raise ImportError('x')\n", "site:Site", "ImportError"),
        ("raise SystemExit(3)\n", "site:Site", "SystemExit"),
        (
            "import deedum\nclass Site(deedum.App):\n"
            "    def __init__(self, s):\n        raise KeyError('k')\n",
            "site:Site",
            "KeyError",
        ),
    ],
)
def test_app_config_errors_name_the_app(tmp_path, source, app, needle):
    site = make_site(tmp_path, app=app)
    put(site.root / "site.py", source)
    with pytest.raises(ConfigError, match="app") as err:
        build(site, now=NOW)
    assert app in str(err.value)
    assert needle in str(err.value)
    assert not (site.root / "_site").exists()


def test_app_constructor_deedum_error_passes_through(tmp_path):
    site = app_site(tmp_path)
    put(site.root / "data" / "people.json", "{nope")
    with pytest.raises(ContentError, match=r"people\.json"):
        build(site, now=NOW)


@pytest.mark.parametrize("hook", ["load_pages", "context", "filters", "globals"])
def test_hook_failures_name_the_hook(tmp_path, hook):
    args = "self, page" if hook == "context" else "self"
    site = hooks_site(
        tmp_path, f"    def {hook}({args}):\n        raise ValueError('boom')\n"
    )
    with pytest.raises(DeedumError) as err:
        build(site, now=NOW)
    msg = str(err.value)
    assert f"app hook '{hook}' (site:Site) failed: ValueError: boom" == msg


def test_after_build_failure_leaves_complete_output(tmp_path):
    site = hooks_site(
        tmp_path, "    def after_build(self, out):\n        raise ValueError('boom')\n"
    )
    with pytest.raises(DeedumError, match=r"after_build.*boom"):
        build(site, now=NOW)
    assert (site.root / "_site" / "sitemap.xml").is_file()


def test_deedum_error_in_hook_keeps_type_hint_and_gains_name(tmp_path):
    site = hooks_site(
        tmp_path,
        "    def load_pages(self):\n"
        "        raise deedum.ConfigError('bad thing', hint='fix it')\n",
    )
    with pytest.raises(ConfigError) as err:
        build(site, now=NOW)
    assert str(err.value) == "app hook 'load_pages' (site:Site) failed: bad thing"
    assert err.value.hint == "fix it"


@pytest.mark.parametrize(
    ("hook", "ret", "needle"),
    [
        ("load_pages", "{}", "list of Page"),
        ("load_pages", "['a']", "list of Page"),
        ("context", "[]", "dict"),
        ("context", "{'page': 1}", "must not contain page"),
        ("context", "{'template': 1}", "must not contain template"),
        ("context", "{1: 2}", "keys must be strings"),
        ("filters", "[]", "dict"),
        ("filters", "{1: len}", "keys must be strings"),
        ("filters", "{'f': 3}", "'f' is not callable"),
        ("globals", "[]", "dict"),
        ("globals", "{1: 2}", "keys must be strings"),
        ("globals", "{'site': 1}", "site is a built-in global"),
        ("globals", "{'url': 1, 'data': 2}", "data, url is a built-in global"),
    ],
)
def test_bad_hook_return_values(tmp_path, hook, ret, needle):
    args = "self, page" if hook == "context" else "self"
    site = hooks_site(tmp_path, f"    def {hook}({args}):\n        return {ret}\n")
    with pytest.raises(DeedumError) as err:
        build(site, now=NOW)
    assert f"app hook '{hook}'" in str(err.value)
    assert needle in str(err.value)


def test_failing_load_pages_leaves_existing_output(tmp_path):
    site = make_site(tmp_path)
    build(site, now=NOW)
    before = snapshot(site.root / "_site")
    put(
        site.root / "site.py",
        "import deedum\nclass Site(deedum.App):\n"
        "    def load_pages(self):\n        raise ValueError('boom')\n",
    )
    broken = Site(
        title="T", base_url="https://ex.test", root=site.root, app="site:Site"
    )
    with pytest.raises(DeedumError, match="load_pages"):
        build(broken, now=NOW)
    assert snapshot(site.root / "_site") == before


def test_failing_env_hook_leaves_existing_output(tmp_path):
    site = make_site(tmp_path)
    build(site, now=NOW)
    before = snapshot(site.root / "_site")
    put(
        site.root / "site.py",
        "import deedum\nclass Site(deedum.App):\n"
        "    def globals(self):\n        return {'site': 1}\n",
    )
    broken = Site(
        title="T", base_url="https://ex.test", root=site.root, app="site:Site"
    )
    with pytest.raises(DeedumError, match="globals"):
        build(broken, now=NOW)
    assert snapshot(site.root / "_site") == before


def test_duplicate_urls_from_load_pages(tmp_path):
    site = hooks_site(
        tmp_path,
        "    def load_pages(self):\n"
        "        return super().load_pages() + [self.page('blog/one/', title='dup')]\n",
    )
    with pytest.raises(ContentError, match="written by both"):
        build(site, now=NOW)


def test_reload_is_fresh_on_every_build(tmp_path):
    site = app_site(tmp_path)
    put(site.root / "data" / "people.yaml", "[]\n")
    build(site, now=NOW)
    assert (site.root / "_site" / "marker.txt").read_text() == "done"
    put(site.root / "site.py", APP_SRC.replace('"done"', '"changed"'))
    build(site, now=NOW)
    assert (site.root / "_site" / "marker.txt").read_text() == "changed"


def test_rebuild_with_same_now_is_byte_identical(tmp_path):
    site = make_site(tmp_path)
    build(site, now=NOW)
    first = snapshot(site.root / "_site")
    build(site, now=NOW)
    assert snapshot(site.root / "_site") == first


def test_app_exported():
    assert deedum.App is App
    assert Page


def test_unloadable_spec_is_an_app_error(tmp_path, monkeypatch):
    site = app_site(tmp_path)
    monkeypatch.setattr(
        "deedum.app.importlib.util.spec_from_file_location", lambda *a, **k: None
    )
    with pytest.raises(ConfigError, match="cannot load"):
        load_app(site)


HELPER_APP = """
import deedum
from helpers import VALUE


class S(deedum.App):
    def load_pages(self):
        return [self.page("", title="H", body=VALUE)]
"""


def test_rebuild_sees_edited_sibling_and_forgets_it(tmp_path):
    site = app_site(tmp_path, HELPER_APP, "site:S")
    helpers = put(site.root / "helpers.py", "VALUE = 'ONE'\n")
    path_before = list(sys.path)
    build(site, tmp_path / "out1")
    assert "helpers" not in sys.modules
    helpers.write_text("VALUE = 'TWO'\n", encoding="utf-8")
    build(site, tmp_path / "out2")
    assert "ONE" in (tmp_path / "out1" / "index.html").read_text(encoding="utf-8")
    assert "TWO" in (tmp_path / "out2" / "index.html").read_text(encoding="utf-8")
    assert sys.path == path_before


def test_package_from_venv_under_root_stays_loaded(tmp_path, monkeypatch):
    site = app_site(
        tmp_path,
        "import deedum, venvpkg\nclass S(deedum.App):\n    pass\n",
        "site:S",
    )
    packages = site.root / ".venv" / "lib" / "python3" / "site-packages"
    put(packages / "venvpkg" / "__init__.py", "LOADS = 1\n")
    monkeypatch.syspath_prepend(str(packages))
    monkeypatch.delitem(sys.modules, "venvpkg", raising=False)
    load_app(site)
    assert sys.modules["venvpkg"].LOADS == 1


def test_sibling_shadowing_stdlib_does_not_stay(tmp_path):
    site = app_site(
        tmp_path,
        "import deedum, colorsys\nclass S(deedum.App):\n    pass\n",
        "myapp:S",
    )
    put(
        site.root / "myapp.py",
        "import deedum, colorsys\nclass S(deedum.App):\n    pass\n",
    )
    put(site.root / "colorsys.py", "MINE = 1\n")
    load_app(site)
    assert sys.modules["colorsys"] is colorsys
    assert not hasattr(sys.modules.get("colorsys"), "MINE")


@pytest.mark.parametrize("key", ["url", "output"])
def test_page_helper_refuses_reserved_kwargs(tmp_path, key):
    app = App(make_site(tmp_path))
    with pytest.raises(DeedumError, match=key):
        app.page("y/", title="Y", **{key: "z"})
