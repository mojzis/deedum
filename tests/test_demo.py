"""The demo site under examples/demo and the README (R27, R28)."""

from __future__ import annotations

import datetime as dt
import filecmp
import re
import shutil
import xml.etree.ElementTree as ET
from collections.abc import Callable
from pathlib import Path

import pytest
import yaml
from typer.testing import CliRunner

from deedum import cli
from deedum.app import build
from deedum.builder import BuildReport
from deedum.check import check_folder
from deedum.config import _KNOWN, load_site

ROOT = Path(__file__).parents[1]
DEMO = ROOT / "examples" / "demo"
README = ROOT / "README.md"
FIXED = dt.datetime(2026, 5, 1, 12, 0, tzinfo=dt.UTC)
BASE_PATH = "/demo/"
BASE = "https://example.org/demo/"
runner = CliRunner()
EXPECTED = (
    "sitemap.xml", "robots.txt", ".nojekyll", "404.html", "favicon.ico",
    "favicon.svg", "apple-touch-icon.png", "icon-192.png", "icon-512.png",
    "site.webmanifest", "blog/feed.xml", "llms.txt", "llms-full.txt", "index.md",
    "humans.txt",
)  # fmt: skip
DATED = ["third-post", "second-post", "first-post"]
UNDATED = ["undated", "hostile"]


@pytest.fixture(scope="module")
def built(tmp_path_factory: pytest.TempPathFactory) -> tuple[Path, BuildReport]:
    out = tmp_path_factory.mktemp("demo") / "out"
    return out, build(load_site(DEMO), out, now=FIXED)


@pytest.fixture(scope="module")
def out(built: tuple[Path, BuildReport]) -> Path:
    return built[0]


def indexable(out: Path) -> list[Path]:
    pages = sorted(out.rglob("index.html"))
    return [p for p in pages if "noindex" not in p.read_text(encoding="utf-8")]


def tools() -> list[dict[str, str]]:
    return yaml.safe_load((DEMO / "data" / "tools.yaml").read_text(encoding="utf-8"))


def test_report_counts_match_output(built: tuple[Path, BuildReport]) -> None:
    out, report = built
    assert report.pages == len(list(out.rglob("index.html")))
    assert report.static == 2
    assert set(report.extras) <= {
        p.relative_to(out).as_posix() for p in out.rglob("*") if p.is_file()
    }
    assert "blog/feed.xml" in report.extras


@pytest.mark.parametrize("name", EXPECTED)
def test_expected_files_exist(out: Path, name: str) -> None:
    assert (out / name).is_file()


def test_every_page_has_an_index_md_sibling(out: Path) -> None:
    for page in out.rglob("index.html"):
        assert page.with_name("index.md").is_file(), page


def test_favicon_svg_is_a_byte_copy_of_the_source(out: Path) -> None:
    assert (out / "favicon.svg").read_bytes() == (DEMO / "icon.svg").read_bytes()


def test_sitemap_and_feed_urls(out: Path) -> None:
    sitemap = ET.parse(out / "sitemap.xml").getroot()  # noqa: S314 -- our own file
    locs = [e.text or "" for e in sitemap.iter() if e.tag.endswith("loc")]
    assert locs
    assert all(loc.startswith(BASE) for loc in locs)
    feed = ET.parse(out / "blog" / "feed.xml").getroot()  # noqa: S314 -- our own file
    ns = "{http://www.w3.org/2005/Atom}"
    ids = [
        link.get("href", "")
        for link in feed.iter(f"{ns}link")
        if link.get("rel") != "self"
    ]
    entries = [
        link.get("href", "")
        for e in feed.findall(f"{ns}entry")
        for link in e.findall(f"{ns}link")
    ]
    assert entries == [f"{BASE}blog/{slug}/" for slug in DATED]
    assert all(href.startswith(BASE) for href in [*ids, *entries])


def test_undated_posts_are_listed_but_not_in_the_feed(out: Path) -> None:
    feed = (out / "blog" / "feed.xml").read_text(encoding="utf-8")
    listing = (out / "blog" / "index.html").read_text(encoding="utf-8")
    for slug in UNDATED:
        assert f"blog/{slug}/" not in feed
        assert f"/demo/blog/{slug}/" in listing


HEAD_FRAGMENTS = (
    'name="description" content="',
    'rel="canonical" href="https://example.org/demo/',
    'property="og:image" content="https://example.org/demo/social.png"',
    'og:image:width" content="1200"',
    'og:image:height" content="630"',
    'name="twitter:card" content="summary_large_image"',
    'name="theme-color" content="#2a6f97"',
    'rel="icon" href="/demo/favicon.ico"',
    'rel="icon" href="/demo/favicon.svg"',
    'rel="apple-touch-icon"',
    'rel="manifest"',
)
FEED_LINK = 'rel="alternate" type="application/atom+xml"'


def head_problems(out: Path) -> list[tuple[str, str]]:
    problems: list[tuple[str, str]] = []
    for page in indexable(out):
        head = page.read_text(encoding="utf-8").split("</head>")[0]
        rel = page.relative_to(out).parent.as_posix()
        problems += [(rel, f) for f in HEAD_FRAGMENTS if f not in head]
        if not re.search(r"<title>[^<]+</title>", head):
            problems.append((rel, "title"))
        if (FEED_LINK in head) != (rel == "." or rel.split("/")[0] == "blog"):
            problems.append((rel, "feed link"))
    return problems


def test_head_of_every_indexable_page(out: Path) -> None:
    assert len(indexable(out)) >= 12
    assert head_problems(out) == []


def tool_problems(out: Path) -> list[tuple[str, str]]:
    sitemap = (out / "sitemap.xml").read_text(encoding="utf-8")
    llms = (out / "llms.txt").read_text(encoding="utf-8")
    problems: list[tuple[str, str]] = []
    for tool in tools():
        folder = out / "tools" / tool["slug"]
        html = (folder / "index.html").read_text(encoding="utf-8")
        url = f"{BASE}tools/{tool['slug']}/"
        checks = {
            "index.md": (folder / "index.md").is_file(),
            "sitemap": url in sitemap,
            "llms": url in llms,
            "context": tool["summary"] in html and f'href="{tool["url"]}"' in html,
            "global": f'href="{BASE_PATH}tools/"' in html,
        }
        problems += [(tool["slug"], k) for k, ok in checks.items() if not ok]
    return problems


def test_tool_pages(out: Path) -> None:
    assert len(tools()) >= 3
    assert tool_problems(out) == []


def test_tools_listing_uses_filter_and_context(out: Path) -> None:
    listing = (out / "tools" / "index.html").read_text(encoding="utf-8")
    assert f"{len(tools())} tools." in listing


def test_blog_pages_use_filter_and_context(out: Path) -> None:
    post = (out / "blog" / "second-post" / "index.html").read_text(encoding="utf-8")
    others = post.split("More posts")[1]
    assert "Published 14 February 2026, updated 20 February 2026" in post
    assert 'href="/demo/blog/first-post/"' in others
    assert 'href="/demo/blog/second-post/"' not in others


def test_blog_listing_counts_every_post(out: Path) -> None:
    listing = (out / "blog" / "index.html").read_text(encoding="utf-8")
    assert f"{len(DATED) + len(UNDATED)} posts." in listing


def test_after_build_file(out: Path) -> None:
    assert (out / "humans.txt").read_text(encoding="utf-8") == (
        "Site: Deedum demo\nAuthor: Demo Author\nLanguage: en\nTools: 3\n"
    )


def leaks(out: Path) -> list[str]:
    names = ("sitemap.xml", "llms.txt", "blog/feed.xml", "llms-full.txt")
    needles = ("draft", "_notes", "private notes")
    return [
        f"{name}: {needle}"
        for name in names
        for needle in needles
        if needle in (out / name).read_text(encoding="utf-8").lower()
    ]


def test_draft_and_underscore_file_make_no_output(out: Path) -> None:
    assert not (out / "blog" / "draft").exists()
    assert not (out / "blog" / "_notes").exists()
    assert leaks(out) == []


def test_check_finds_nothing(out: Path) -> None:
    report = check_folder(out, BASE_PATH)
    assert report.pages == 13
    assert report.findings == []


def test_cli_round_trip(tmp_path: Path) -> None:
    result = runner.invoke(
        cli.app,
        [
            "build", "--config", str(DEMO / "deedum.toml"),
            "--out", str(tmp_path / "site"), "--check",
        ],
    )  # fmt: skip
    assert result.exit_code == 0, result.output
    assert "checked 13 pages: 0 errors, 0 warnings" in result.output
    assert (tmp_path / "site" / "index.html").is_file()


def test_two_builds_are_identical(tmp_path: Path) -> None:
    one, two = tmp_path / "one", tmp_path / "two"
    build(load_site(DEMO), one, now=FIXED)
    build(load_site(DEMO), two, now=FIXED)

    def same(cmp: filecmp.dircmp[str]) -> bool:
        return (
            not cmp.diff_files
            and not cmp.left_only
            and not cmp.right_only
            and not cmp.funny_files
            and all(same(sub) for sub in cmp.subdirs.values())
        )

    cmp = filecmp.dircmp(one, two)
    assert list((one / "blog").iterdir())
    assert same(cmp)
    # dircmp compares by stat first; compare the bytes of the dated outputs too.
    for name in ("sitemap.xml", "blog/feed.xml", "llms-full.txt", "humans.txt"):
        assert (one / name).read_bytes() == (two / name).read_bytes()


def demo_copy(tmp_path: Path) -> Path:
    copy = tmp_path / "demo"
    shutil.copytree(DEMO, copy, ignore=shutil.ignore_patterns("_site", "__pycache__"))
    return copy


def edit_tools(copy: Path, edit: Callable[[list[dict[str, str]]], None]) -> None:
    path = copy / "data" / "tools.yaml"
    entries = yaml.safe_load(path.read_text(encoding="utf-8"))
    edit(entries)
    path.write_text(yaml.safe_dump(entries), encoding="utf-8")


def drop_slug(entries: list[dict[str, str]]) -> None:
    del entries[0]["slug"]


def dup_slug(entries: list[dict[str, str]]) -> None:
    entries[1]["slug"] = entries[0]["slug"]


def not_a_mapping(entries: list[dict[str, str]]) -> None:
    entries.insert(0, "ruff")  # ty: ignore[invalid-argument-type]


@pytest.mark.parametrize(
    ("edit", "message"),
    [
        (drop_slug, "entry 1: missing or empty 'slug'"),
        (dup_slug, "entry 2: duplicate slug 'ruff'"),
        (not_a_mapping, "entry 1: expected a mapping"),
    ],
)
def test_malformed_tool_data(
    tmp_path: Path, edit: Callable[[list[dict[str, str]]], None], message: str
) -> None:
    copy = demo_copy(tmp_path)
    edit_tools(copy, edit)
    out = tmp_path / "out"
    result = runner.invoke(
        cli.app,
        ["build", "--config", str(copy / "deedum.toml"), "--out", str(out)],
    )
    assert result.exit_code == 1
    assert "app hook 'load_pages' (demo_app:DemoApp) failed" in result.output
    assert message in result.output
    assert not out.exists()


def test_tools_file_that_is_not_a_list(tmp_path: Path) -> None:
    copy = demo_copy(tmp_path)
    (copy / "data" / "tools.yaml").write_text("a: 1\n", encoding="utf-8")
    result = runner.invoke(cli.app, ["build", "--config", str(copy / "deedum.toml")])
    assert result.exit_code == 1
    assert "must be a list of entries" in result.output
    assert not (copy / "_site").exists()


def test_tool_slug_clashing_with_a_page_names_both(tmp_path: Path) -> None:
    copy = demo_copy(tmp_path)
    (copy / "content" / "tools").mkdir()
    (copy / "content" / "tools" / "ruff.md").write_text("# Ruff\n", encoding="utf-8")
    result = runner.invoke(cli.app, ["build", "--config", str(copy / "deedum.toml")])
    assert result.exit_code == 1
    assert "tools/ruff/" in result.output
    assert "written by both" in result.output


def test_example_is_left_clean() -> None:
    assert not list(DEMO.rglob("__pycache__"))
    assert "examples/demo/_site/" in (ROOT / ".gitignore").read_text(encoding="utf-8")


# ---- README ---------------------------------------------------------------

HEADINGS = (
    "What deedum does", "Install and first run", "The three ways in",
    "deedum extras", "Commands", "Config reference", "Templates", "Notes",
    "The demo",
)  # fmt: skip


def readme() -> str:
    return README.read_text(encoding="utf-8")


@pytest.mark.parametrize("key", _KNOWN)
def test_readme_lists_every_config_key(key: str) -> None:
    assert f"| `{key}` |" in readme()


def test_readme_install_line_and_no_pypi() -> None:
    text = readme()
    assert "uvx --from git+https://github.com/mojzis/deedum deedum guide" in text
    assert "uv add git+https://github.com/mojzis/deedum" in text
    assert "deedum@latest" not in text


def test_readme_sections_in_order() -> None:
    text = readme()
    # The first section is the intro under the title; "deedum extras" is a heading.
    found = re.findall(r"^## (.+)$", text, flags=re.MULTILINE)
    assert found == [*HEADINGS[1:3], "`deedum extras`", *HEADINGS[4:]]
    assert text.startswith("# deedum\n")
    assert "What a build writes:" in text


def test_readme_names_the_three_ways_in() -> None:
    text = readme()
    ways = re.findall(r"^### (\d)\. (.+)$", text, flags=re.MULTILINE)
    assert ways == [
        ("1", "Convention build"), ("2", "An `App` subclass"), ("3", "The Python API"),
    ]  # fmt: skip


def test_readme_python_example_runs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    section = readme().split("### 3. The Python API")[1]
    block = re.search(r"```python\n(.*?)```", section, flags=re.DOTALL)
    assert block
    site = tmp_path / "site"
    (site / "content").mkdir(parents=True)
    (site / "deedum.toml").write_text(
        'title = "T"\nbase_url = "https://example.org"\n', encoding="utf-8"
    )
    (site / "content" / "index.md").write_text("# Home\n\nHi.\n", encoding="utf-8")
    monkeypatch.chdir(site)
    exec(compile(block.group(1), "README.md", "exec"), {})  # noqa: S102 -- the README's own example
    assert (site / "_site" / "index.html").is_file()
    assert (site / "_site" / "sitemap.xml").is_file()
    assert "<title>T</title>" in capsys.readouterr().out
