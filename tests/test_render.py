from __future__ import annotations

import datetime as dt
import re
from pathlib import Path

import pytest
from PIL import Image

import deedum
import deedum.render as render_mod
from deedum import (
    ConfigError,
    Page,
    RenderError,
    Site,
    head_tags,
    load_pages,
    load_site,
    make_env,
    render_page,
)

NOW = dt.datetime(2026, 11, 18, 12, 0, tzinfo=dt.UTC)
BASE = "https://mojzis.github.io"
AESOP = "/aesop/"
EX = "https://e.x"
CDN_IMG = "https://cdn.x/a.png"
SITE_PNG = "/site.png"


def make_page(**kw) -> Page:
    kw.setdefault("url", "blog/hello/")
    kw.setdefault("output", "blog/hello/index.html")
    kw.setdefault("title", "Hello")
    kw.setdefault("description", "")
    kw.setdefault("body", "<p>Body</p>")
    kw.setdefault("source", "content/blog/hello.md")
    kw.setdefault("template", "page.html")
    return Page(**kw)


def write(root: Path, rel: str, text: str) -> None:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)


def png(root: Path, rel: str, size=(1200, 630)) -> None:
    path = root / "static" / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", size).save(path)


def full_site(root: Path, **kw) -> Site:
    kw.setdefault("title", "Aesop")
    kw.setdefault("base_url", BASE)
    kw.setdefault("base_path", AESOP)
    kw.setdefault("twitter", "mojzis")
    kw.setdefault("favicon", "icon.svg")
    kw.setdefault("feeds", ("blog",))
    kw.setdefault("analytics", "mojzis.github.io")
    return Site(root=root, **kw)


def full_page(**kw) -> Page:
    kw.setdefault("description", "Hi there")
    kw.setdefault("date", dt.date(2026, 11, 1))
    kw.setdefault("collection", "blog")
    kw.setdefault("image", "img/s.png")
    kw.setdefault("lang", "en-GB")
    kw.setdefault("alternates", {"cs": "cs/blog/hello/"})
    return make_page(**kw)


def head_of(site: Site, page: Page) -> str:
    return str(head_tags(site, page))


def test_public_exports():
    assert deedum.head_tags is head_tags
    assert deedum.make_env is make_env
    assert deedum.render_page is render_page
    assert issubclass(RenderError, deedum.DeedumError)


def test_strict_undefined_names_template_and_page(tmp_path):
    write(tmp_path, "templates/page.html", "x\n{{ page.titel }}")
    env = make_env(Site(title="T", base_url=BASE, root=tmp_path), now=NOW)
    with pytest.raises(RenderError) as exc:
        render_page(env, make_page())
    assert "page.html" in str(exc.value)
    assert "blog/hello/" in str(exc.value)
    assert "line 2" in str(exc.value)


def test_globals_resolve(tmp_path):
    site = Site(title="T", base_url=BASE, root=tmp_path)
    cols = {"blog": [make_page()]}
    env = make_env(site, collections=cols, data={"k": 1}, now=NOW)
    write(
        tmp_path,
        "templates/g.html",
        "{{ site.title }}|{{ absolute('a/') }}|{{ collections.blog|length }}|"
        "{{ data.k }}|{{ now.isoformat() }}|{{ url('a/') }}",
    )
    out = render_page(env, make_page(), template="g.html")
    assert out == f"T|{BASE}/a/|1|1|{NOW.isoformat()}|/a/"


def test_default_globals_and_now_is_utc(tmp_path):
    write(
        tmp_path, "templates/d.html", "{{ collections }}{{ data }}{{ now.utcoffset() }}"
    )
    env = make_env(Site(title="T", base_url=BASE, root=tmp_path))
    assert render_page(env, make_page(), template="d.html") == "{}{}0:00:00"


def test_undefined_name_raises(tmp_path):
    write(tmp_path, "templates/u.html", "{{ nope }}")
    env = make_env(Site(title="T", base_url=BASE, root=tmp_path))
    with pytest.raises(RenderError, match="nope"):
        render_page(env, make_page(), template="u.html")


def test_autoescape_on_for_any_template(tmp_path):
    write(tmp_path, "templates/e.txt", "{{ page.title }}")
    env = make_env(Site(title="T", base_url=BASE, root=tmp_path))
    assert render_page(env, make_page(title="<b>"), template="e.txt") == "&lt;b&gt;"


def test_missing_template(tmp_path):
    env = make_env(Site(title="T", base_url=BASE, root=tmp_path))
    with pytest.raises(RenderError, match=r"nope\.html") as exc:
        render_page(env, make_page(template="nope.html"))
    assert "blog/hello/" in str(exc.value)


def test_syntax_error_names_template_and_line(tmp_path):
    write(tmp_path, "templates/page.html", "a\nb\n{% if %}")
    env = make_env(Site(title="T", base_url=BASE, root=tmp_path))
    with pytest.raises(RenderError, match=r"page\.html, line 3"):
        render_page(env, make_page())


def test_error_in_included_template_names_it(tmp_path):
    write(tmp_path, "templates/deedum/head.html", "{{ page.titel }}")
    env = make_env(Site(title="T", base_url=BASE, root=tmp_path))
    with pytest.raises(RenderError, match=r"deedum/head.html, line 1"):
        render_page(env, make_page())


def test_target_head_replaces_builtin(tmp_path):
    write(tmp_path, "templates/deedum/head.html", '<meta name="x-override">')
    env = make_env(Site(title="T", base_url=BASE, root=tmp_path), now=NOW)
    out = render_page(env, make_page())
    assert "x-override" in out
    assert "og:title" not in out


def test_target_page_replaces_builtin(tmp_path):
    write(tmp_path, "templates/page.html", "custom {{ page.title }}")
    env = make_env(Site(title="T", base_url=BASE, root=tmp_path))
    assert render_page(env, make_page()) == "custom Hello"


def test_override_extends_builtin(tmp_path):
    write(
        tmp_path,
        "templates/deedum/head.html",
        '{% extends "builtin/deedum/head.html" %}'
        '{% block scripts %}{{ super() }}<meta name="x-added">{% endblock %}',
    )
    env = make_env(Site(title="T", base_url=BASE, root=tmp_path))
    out = render_page(env, make_page())
    assert "og:title" in out
    assert "x-added" in out


@pytest.mark.parametrize(
    ("relative", "current", "expected"),
    [
        (True, "blog/hello/", "../../about/"),
        (True, "", "about/"),
        (False, "blog/hello/", "/aesop/about/"),
    ],
)
def test_url_bound_from_page(tmp_path, relative, current, expected):
    site = Site(
        title="T",
        base_url=BASE,
        base_path=AESOP,
        relative_links=relative,
        root=tmp_path,
    )
    write(tmp_path, "templates/u.html", "{{ url('about/') }}")
    page = make_page(url=current)
    assert render_page(make_env(site), page, template="u.html") == expected


def test_url_without_page_is_root_relative(tmp_path):
    site = Site(title="T", base_url=BASE, relative_links=True, root=tmp_path)
    env = make_env(site)
    write(tmp_path, "templates/u.html", "{{ url('about/') }}")
    assert env.get_template("u.html").render() == "/about/"


def test_reference_head(tmp_path):
    png(tmp_path, "img/s.png")
    out = head_of(full_site(tmp_path), full_page())
    for expected in [
        "<title>Hello | Aesop</title>",
        '<meta name="description" content="Hi there">',
        f'rel="canonical" href="{BASE}/aesop/blog/hello/"',
        'og:type" content="article"',
        'og:site_name" content="Aesop"',
        'og:title" content="Hello"',
        'og:description" content="Hi there"',
        f'og:url" content="{BASE}/aesop/blog/hello/"',
        'og:locale" content="en_GB"',
        f'og:image" content="{BASE}/aesop/img/s.png"',
        'og:image:width" content="1200"',
        'og:image:height" content="630"',
        'twitter:card" content="summary_large_image"',
        'twitter:site" content="@mojzis"',
        'rel="icon" href="/aesop/favicon.ico" sizes="32x32"',
        'href="/aesop/favicon.svg"',
        'rel="apple-touch-icon" href="/aesop/apple-touch-icon.png"',
        'rel="manifest" href="/aesop/site.webmanifest"',
        f'href="{BASE}/aesop/blog/feed.xml"',
        'title="Aesop: blog"',
        f'hreflang="cs" href="{BASE}/aesop/cs/blog/hello/"',
        'data-domain="mojzis.github.io"',
        'src="https://plausible.io/js/script.js"',
    ]:
        assert expected in out
    assert "robots" not in out


def test_head_tag_order(tmp_path):
    png(tmp_path, "img/s.png")
    out = head_of(full_site(tmp_path, head_extra="<i>x</i>"), full_page(noindex=True))
    marks = [
        "charset",
        "<title>",
        "canonical",
        "og:type",
        "og:image",
        "twitter:card",
        'rel="icon"',
        "atom+xml",
        "hreflang",
        "robots",
        "plausible",
        "<i>x</i>",
    ]
    positions = [out.index(m) for m in marks]
    assert positions == sorted(positions)


def test_home_title_and_all_feeds(tmp_path):
    site = full_site(tmp_path, feeds=("blog", "notes", "blog"))
    out = head_of(site, make_page(url="", title="Aesop", collection=""))
    assert "<title>Aesop</title>" in out
    assert out.count("atom+xml") == 2
    assert out.index("blog/feed.xml") < out.index("notes/feed.xml")


def test_home_title_ignores_page_title(tmp_path):
    out = head_of(full_site(tmp_path), make_page(url="", title="Welcome"))
    assert "<title>Aesop</title>" in out


def test_title_not_duplicated(tmp_path):
    out = head_of(full_site(tmp_path), make_page(title="Aesop"))
    assert "<title>Aesop</title>" in out


def test_non_feed_collection_has_no_feed_link(tmp_path):
    out = head_of(full_site(tmp_path), make_page(collection="notes"))
    assert "atom+xml" not in out


def test_favicon_png_source_has_no_svg_link(tmp_path):
    out = head_of(full_site(tmp_path, favicon="Icon.PNG"), make_page())
    assert "favicon.svg" not in out
    assert "favicon.ico" in out
    out = head_of(full_site(tmp_path, favicon="Icon.SVG"), make_page())
    assert "favicon.svg" in out


def test_locale_without_region(tmp_path):
    out = head_of(full_site(tmp_path), make_page(lang="en"))
    assert 'og:locale" content="en"' in out


def test_site_image_fallback(tmp_path):
    png(tmp_path, "site.png", (10, 20))
    out = head_of(full_site(tmp_path, image=SITE_PNG), make_page())
    assert f'og:image" content="{BASE}/aesop/site.png"' in out
    assert 'og:image:width" content="10"' in out
    assert "summary_large_image" in out


def test_minimal_head_has_no_empty_or_optional_tags(tmp_path):
    site = Site(title="T", base_url=EX, root=tmp_path)
    out = head_of(site, make_page())
    assert not re.search(r'(content|href)=""', out)
    for absent in [
        "og:image",
        "twitter:site",
        'rel="icon"',
        "atom+xml",
        "hreflang",
        "noindex",
        "<script",
        "og:description",
        'name="description"',
    ]:
        assert absent not in out
    assert 'og:type" content="website"' in out
    assert 'twitter:card" content="summary"' in out


def test_empty_titles_are_dropped(tmp_path):
    site = Site(title="", base_url=EX, root=tmp_path)
    out = head_of(site, make_page(title="", lang=""))
    assert not re.search(r'(content|href)=""', out)
    assert "og:title" not in out
    assert "og:locale" not in out


@pytest.mark.parametrize(
    ("field", "value", "expected"),
    [
        ("title", "</title><script>x</script>", "&lt;/title&gt;&lt;script&gt;"),
        ("description", 'say "hi"', "say &#34;hi&#34;"),
        ("alternates", {"cs": 'a"><script>'}, "a&#34;&gt;&lt;script&gt;"),
    ],
)
def test_page_values_escaped(tmp_path, field, value, expected):
    out = head_of(full_site(tmp_path), full_page(**{field: value}))
    assert expected in out
    assert "<script>x" not in out
    assert '"><script>' not in out
    assert out.count("<title>") == 1


def test_analytics_escaped_and_head_extra_raw(tmp_path):
    site = full_site(tmp_path, analytics='a"><script>', head_extra='<meta name="raw">')
    out = head_of(site, make_page())
    assert 'data-domain="a&#34;&gt;&lt;script&gt;"' in out
    assert '<meta name="raw">' in out


@pytest.mark.parametrize(("noindex", "present"), [(True, True), (False, False)])
def test_noindex(tmp_path, noindex, present):
    out = head_of(full_site(tmp_path), make_page(noindex=noindex))
    assert ('name="robots" content="noindex"' in out) is present


@pytest.mark.parametrize(
    "image", ["img/none.png", "img/a.svg", CDN_IMG, "img/bad.png"], ids=lambda i: i[-8:]
)
def test_image_dimensions_bound(tmp_path, image):
    write(tmp_path, "static/img/a.svg", "<svg/>")
    write(tmp_path, "static/img/bad.png", "not a png")
    out = head_of(full_site(tmp_path), full_page(image=image))
    assert "og:image:width" not in out
    assert "og:image:height" not in out
    assert 'og:image" content=' in out


def test_unreadable_image_gives_no_dimensions(tmp_path, monkeypatch):
    png(tmp_path, "img/ok.png")

    def boom(_path):
        raise OSError

    monkeypatch.setattr(render_mod, "_read_size", boom)
    out = head_of(full_site(tmp_path), full_page(image="img/ok.png"))
    assert "og:image:width" not in out
    assert f'og:image" content="{BASE}{AESOP}img/ok.png"' in out


def test_external_image_emitted_unchanged(tmp_path):
    out = head_of(full_site(tmp_path), full_page(image=CDN_IMG))
    assert f'og:image" content="{CDN_IMG}"' in out


def test_image_outside_static_is_ignored(tmp_path):
    png(tmp_path, "../outside.png")
    out = head_of(full_site(tmp_path), full_page(image="../outside.png"))
    assert "og:image:width" not in out


def test_image_size_cached_per_env(tmp_path, monkeypatch):
    png(tmp_path, "img/s.png")
    calls = []
    real = render_mod._read_size

    def spy(path):
        calls.append(path)
        return real(path)

    monkeypatch.setattr(render_mod, "_read_size", spy)
    env = make_env(full_site(tmp_path), now=NOW)
    render_page(env, full_page())
    render_page(env, full_page())
    render_page(env, full_page())
    assert len(calls) == 1


def test_no_templates_site_renders_readable_page(tmp_path):
    write(tmp_path, "deedum.toml", f'title = "T"\nbase_url = "{EX}"\n')
    write(tmp_path, "content/about.md", "# About\n\nText")
    site = load_site(tmp_path)
    (page,) = load_pages(site)
    out = render_page(make_env(site, now=NOW), page)
    assert out.startswith("<!doctype html>")
    for expected in [
        '<html lang="en">',
        "<h1>About</h1>",
        "<p>Text</p>",
        "<style",
        "og:title",
        '<a href="/">T</a>',
    ]:
        assert expected in out
    assert "<script" not in out
    assert "{{" not in out


def test_head_tags_parity_and_ignores_override(tmp_path):
    png(tmp_path, "img/s.png")
    site, page = full_site(tmp_path), full_page()
    full = render_page(make_env(site, now=NOW), page)
    assert head_of(site, page) in full
    write(tmp_path, "templates/deedum/head.html", '<meta name="x-override">')
    assert "og:title" in head_of(site, page)
    assert "x-override" not in head_of(site, page)
    assert "x-override" in render_page(make_env(site, now=NOW), page)


def test_head_tags_is_markup(tmp_path):
    out = head_tags(full_site(tmp_path), make_page())
    assert hasattr(out, "__html__")


def test_render_is_deterministic(tmp_path):
    png(tmp_path, "img/s.png")
    site, page = full_site(tmp_path), full_page()
    first = render_page(make_env(site, now=NOW), page)
    assert render_page(make_env(site, now=NOW), page) == first


@pytest.mark.parametrize("bad", ["https://u:p@h.io", "https://h.io:"])
def test_load_site_rejects_leaky_base_url(tmp_path, bad):
    write(tmp_path, "deedum.toml", f'title = "T"\nbase_url = "{bad}"\n')
    with pytest.raises(ConfigError, match="base_url"):
        load_site(tmp_path)


@pytest.mark.parametrize(
    ("src", "exc_type"),
    [("{{ 1 // 0 }}", ZeroDivisionError), ("{{ 1 + 'a' }}", TypeError)],
)
def test_runtime_error_wrapped(tmp_path, src, exc_type):
    write(tmp_path, "templates/page.html", src)
    env = make_env(Site(title="T", base_url=BASE, root=tmp_path), now=NOW)
    with pytest.raises(RenderError) as exc:
        render_page(env, make_page())
    msg = str(exc.value)
    assert all(
        part in msg
        for part in ["page.html", "blog/hello/", "line 1", exc_type.__name__]
    )
    assert type(exc.value.__cause__) is exc_type


def test_builtin_page_wraps_long_text(tmp_path):
    write(tmp_path, "deedum.toml", f'title = "T"\nbase_url = "{EX}"\n')
    write(tmp_path, "content/about.md", "# A\n\nhttps://example.com/" + "a" * 300)
    site = load_site(tmp_path)
    (page,) = load_pages(site)
    out = render_page(make_env(site, now=NOW), page)
    assert "overflow-wrap:anywhere" in out
    assert "pre{overflow-x:auto}" in out


def test_image_query_keeps_dimensions(tmp_path):
    png(tmp_path, "img/s.png")
    out = head_of(full_site(tmp_path), full_page(image="img/s.png?v=2"))
    assert 'og:image:width" content="1200"' in out
    assert re.search(r'og:image" content="[^"]*/img/s\.png\?v=2"', out)
