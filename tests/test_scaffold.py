from __future__ import annotations

import datetime as dt
import re
from pathlib import Path

import pytest
import yaml

from deedum import (
    ConfigError,
    ContentError,
    DeedumError,
    Site,
    build_collections,
    load_pages,
    load_site,
)
from deedum.app import build
from deedum.check import check_folder
from deedum.config import _KNOWN, pyproject_facts
from deedum.scaffold import WORKFLOW, init_site, new_entry, slugify

DAY = dt.date(2026, 11, 19)
UVX = "uvx --from git+https://github.com/mojzis/deedum deedum build --check"
UV_SYNC = "uv sync && uv run deedum build --check"
FILES = [
    "deedum.toml",
    "content/index.md",
    "templates/page.html",
    "static",
    ".github/workflows/pages.yml",
]


def put(path: Path, text: str = "x") -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def tree(root: Path) -> dict[str, tuple[int, int] | None]:
    """Every path below ``root`` with its size and mtime: a change fingerprint."""
    return {
        p.relative_to(root).as_posix(): (p.stat().st_size, p.stat().st_mtime_ns)
        for p in sorted(root.rglob("*"))
    }


@pytest.fixture
def folder(tmp_path: Path) -> Path:
    path = tmp_path / "site"
    path.mkdir()
    return path


@pytest.fixture
def site(folder: Path) -> Site:
    init_site(folder)
    return load_site(folder)


# ---- init ------------------------------------------------------------------


def test_init_writes_every_file_and_an_empty_static_folder(folder):
    report = init_site(folder)
    assert report.written == [
        "deedum.toml",
        "content/index.md",
        "templates/page.html",
        "static/",
        ".github/workflows/pages.yml",
    ]
    assert report.skipped == []
    assert report.hints == []
    assert list((folder / "static").iterdir()) == []


def test_init_creates_a_missing_target_folder(tmp_path):
    init_site(tmp_path / "new" / "deep")
    assert (tmp_path / "new" / "deep" / "deedum.toml").is_file()


def test_init_then_build_then_check(folder):
    init_site(folder)
    site = load_site(folder)
    assert build(site).pages == 1
    report = check_folder(folder / "_site", site.base_path)
    assert report.errors == 0
    assert [f.detail for f in report.findings] == ["missing og:image"]


def test_template_override_is_the_one_rendered(folder):
    init_site(folder)
    (folder / "templates" / "page.html").write_text(
        "{% extends 'deedum/base.html' %}{% block content %}MINE{% endblock %}"
    )
    build(load_site(folder))
    assert "MINE" in (folder / "_site" / "index.html").read_text()


def test_config_lists_every_key(folder):
    init_site(folder)
    text = (folder / "deedum.toml").read_text()
    keys = set(re.findall(r"^#? ?(\w+) = ", text, flags=re.M))
    assert keys == set(_KNOWN)


def test_a_rerun_changes_nothing(folder):
    init_site(folder)
    before = tree(folder)
    report = init_site(folder)
    assert report.written == []
    assert [s.split(" ")[0] for s in report.skipped] == [
        "deedum.toml",
        "content/index.md",
        "templates/page.html",
        "static/",
        ".github/workflows/pages.yml",
    ]
    assert tree(folder) == before


def test_only_missing_files_are_written(folder):
    put(folder / "content" / "index.md", "mine")
    report = init_site(folder)
    assert "content/index.md" not in report.written
    assert (folder / "content" / "index.md").read_text() == "mine"
    assert (folder / "deedum.toml").is_file()


def test_an_existing_static_folder_is_kept(folder):
    put(folder / "static" / "a.txt")
    report = init_site(folder)
    assert "static/ (exists)" in report.skipped
    assert (folder / "static" / "a.txt").is_file()


def test_a_file_where_the_workflows_folder_goes_is_skipped(folder):
    put(folder / ".github" / "workflows", "file")
    report = init_site(folder)
    assert ".github/workflows/pages.yml (.github/workflows is not a folder)" in (
        report.skipped
    )
    assert (folder / ".github" / "workflows").read_text() == "file"
    assert "deedum.toml" in report.written


def test_a_symlinked_content_folder_gets_nothing(folder, tmp_path):
    elsewhere = tmp_path / "else"
    elsewhere.mkdir()
    (folder / "content").symlink_to(elsewhere)
    report = init_site(folder)
    assert list(elsewhere.iterdir()) == []
    assert "content/index.md (content is a symlink)" in report.skipped


def test_a_symlinked_target_file_is_never_written_through(folder, tmp_path):
    elsewhere = tmp_path / "else.toml"
    (folder / "deedum.toml").symlink_to(elsewhere)
    report = init_site(folder)
    assert not elsewhere.exists()
    assert "deedum.toml (exists)" in report.skipped


def test_a_dangling_symlink_for_static_is_skipped(folder, tmp_path):
    (folder / "static").symlink_to(tmp_path / "nowhere")
    assert "static/ (exists)" in init_site(folder).skipped


def test_init_in_a_file_is_an_error(tmp_path):
    target = put(tmp_path / "f")
    with pytest.raises(ConfigError, match="not a folder"):
        init_site(target)


def test_pyproject_table_skips_the_config(folder):
    put(folder / "pyproject.toml", '[tool.deedum]\ntitle = "T"\n')
    report = init_site(folder)
    assert not (folder / "deedum.toml").exists()
    assert any("already has [tool.deedum]" in s for s in report.skipped)


def test_malformed_pyproject_writes_nothing(tmp_path):
    target = tmp_path / "site"
    put(target / "pyproject.toml", "[broken")
    before = tree(target)
    with pytest.raises(ConfigError, match="malformed TOML"):
        init_site(target)
    assert tree(target) == before


def test_workflow_without_pyproject_uses_uvx(folder):
    init_site(folder)
    flow = yaml.safe_load((folder / WORKFLOW).read_text())
    commands = [s["run"] for s in flow["jobs"]["build"]["steps"] if "run" in s]
    assert commands == [UVX]


def test_workflow_with_pyproject_uses_uv_sync_and_hints(folder):
    put(folder / "pyproject.toml", '[project]\nname = "x"\n')
    report = init_site(folder)
    flow = yaml.safe_load((folder / WORKFLOW).read_text())
    commands = [s["run"] for s in flow["jobs"]["build"]["steps"] if "run" in s]
    assert commands == [UV_SYNC]
    assert report.hints == ["hint: run uv add deedum"]


@pytest.mark.parametrize("dep", ["deedum", "Deedum>=0.1", "deedum[x]==1", "DEEDUM"])
def test_no_hint_when_deedum_is_a_dependency(folder, dep):
    put(folder / "pyproject.toml", f'[project]\nname = "x"\ndependencies = ["{dep}"]\n')
    assert init_site(folder).hints == []


def test_workflow_triggers_and_permissions(folder):
    init_site(folder)
    flow = yaml.safe_load((folder / WORKFLOW).read_text())
    assert flow["permissions"] == {
        "contents": "read",
        "pages": "write",
        "id-token": "write",
    }
    assert [flow[True]["push"]["branches"], "workflow_dispatch" in flow[True]] == [
        ["main"],
        True,
    ]


def test_workflow_jobs_and_pinned_actions(folder):
    init_site(folder)
    flow = yaml.safe_load((folder / WORKFLOW).read_text())
    steps = [s for job in flow["jobs"].values() for s in job["steps"]]
    uses = [s["uses"] for s in steps if "uses" in s]
    assert [u.split("@")[0] for u in uses] == [
        "actions/checkout",
        "astral-sh/setup-uv",
        "actions/upload-pages-artifact",
        "actions/deploy-pages",
    ]
    assert all("@v" in u for u in uses)
    assert [set(flow["jobs"]), flow["concurrency"]["group"]] == [
        {"build", "deploy"},
        "pages",
    ]


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("[project]\nname='x'\n", (False, False)),
        ("[project]\ndependencies='deedum'\n", (False, False)),
        ("[project]\ndependencies=[1, 'deedum-extra']\n", (False, False)),
        ("[project]\ndependencies=['deedum']\n[tool.deedum]\n", (True, True)),
        ("project = 3\n", (False, False)),
    ],
)
def test_pyproject_facts(tmp_path, text, expected):
    path = tmp_path / "pyproject.toml"
    path.write_text(text)
    assert pyproject_facts(path) == expected


def test_pyproject_facts_of_a_missing_file(tmp_path):
    assert pyproject_facts(tmp_path / "pyproject.toml") == (False, False)


# ---- new -------------------------------------------------------------------


def entry(site: Site, *args, **kw) -> Path:
    return new_entry(site, *args, today=DAY, **kw)


@pytest.mark.parametrize(
    ("title", "slug"),
    [
        ("Příliš žluťoučký kůň", "prilis-zlutoucky-kun"),
        ("Hello,  World!", "hello-world"),
        ("--a--b--", "a-b"),
        ("Ünï 2024", "uni-2024"),
        ("日本語", ""),
        ("!!!", ""),
        ("", ""),
    ],
)
def test_slugify(title, slug):
    assert slugify(title) == slug


def test_new_writes_the_entry_with_title_and_date(site):
    path = entry(site, "blog", "Příliš žluťoučký kůň")
    assert path == site.root / "content" / "blog" / "prilis-zlutoucky-kun.md"
    assert path.read_text(encoding="utf-8") == (
        "---\ntitle: Příliš žluťoučký kůň\ndate: 2026-11-19\n---\n\n"
    )


def test_new_entry_is_listed_in_its_collection(site):
    entry(site, "blog", "First post")
    pages = build_collections(load_pages(site))
    assert [p.title for p in pages["blog"]] == ["First post"]


def test_new_uses_today_in_local_time_by_default(site):
    path = new_entry(site, "blog", "Now")
    day = yaml.safe_load(path.read_text().split("---")[1])["date"]
    assert abs((day - dt.datetime.now().astimezone().date()).days) <= 1


@pytest.mark.parametrize(
    "title", ['Ahoj: "svět" #1', "123", "yes", "- x", "a\nb", "'q'", "{x}", "é: ü"]
)
def test_awkward_titles_round_trip(site, title):
    path = entry(site, "blog", title, slug="t")
    front = yaml.safe_load(path.read_text(encoding="utf-8").split("---")[1])
    assert front["title"] == title


def test_new_refuses_to_overwrite(site):
    path = entry(site, "blog", "Same")
    path.write_text("mine")
    with pytest.raises(ContentError, match="already exists"):
        entry(site, "blog", "Same")
    assert path.read_text() == "mine"


def test_new_refuses_an_existing_symlink_target(site, tmp_path):
    folder = site.root / "content" / "blog"
    folder.mkdir(parents=True)
    (folder / "x.md").symlink_to(tmp_path / "gone.md")
    with pytest.raises(ContentError, match="already exists"):
        entry(site, "blog", "X")
    assert not (tmp_path / "gone.md").exists()


@pytest.mark.parametrize(
    "name", ["../x", "a/b", "_drafts", ".x", "blog\n", "", "a b", "é", "-x"]
)
def test_bad_collection_names_are_config_errors(site, name):
    before = tree(site.root)
    with pytest.raises(ConfigError, match="invalid collection"):
        entry(site, name, "T")
    assert tree(site.root) == before


@pytest.mark.parametrize("name", ["../x", "a/b", "_x", "x\n", ""])
def test_bad_slug_overrides_are_config_errors(site, name):
    with pytest.raises(ConfigError, match="invalid slug"):
        entry(site, "blog", "T", slug=name)


@pytest.mark.parametrize("title", ["日本語", "!!!", ""])
def test_empty_slug_hints_at_the_flag(site, title):
    with pytest.raises(ConfigError) as caught:
        entry(site, "blog", title)
    assert caught.value.hint == "pass --slug"
    assert entry(site, "blog", title, slug="ok").name == "ok.md"


def test_collection_folder_symlink_is_refused(site, tmp_path):
    elsewhere = tmp_path / "else"
    elsewhere.mkdir()
    (site.root / "content" / "blog").symlink_to(elsewhere)
    with pytest.raises(DeedumError, match="blog is a symlink"):
        entry(site, "blog", "T")
    assert list(elsewhere.iterdir()) == []


def test_content_folder_symlink_is_refused(site, tmp_path):
    elsewhere = tmp_path / "else"
    elsewhere.mkdir()
    (site.root / "content" / "index.md").unlink()
    (site.root / "content").rmdir()
    (site.root / "content").symlink_to(elsewhere)
    with pytest.raises(DeedumError, match="content is a symlink"):
        entry(site, "blog", "T")
    assert list(elsewhere.iterdir()) == []


def test_content_folder_may_be_missing(tmp_path):
    root = tmp_path / "s"
    put(root / "deedum.toml", 'title = "T"\nbase_url = "https://e.test"\n')
    path = entry(load_site(root), "blog", "T")
    assert path.is_file()


@pytest.mark.parametrize("where", ["/abs", "../up"])
def test_content_folder_must_stay_inside_the_root(tmp_path, where):
    site = Site(title="T", base_url="https://e.test", content=where, root=tmp_path)
    with pytest.raises(ConfigError, match="inside the site root"):
        entry(site, "blog", "T")


def test_nested_content_folder(tmp_path):
    root = tmp_path / "s"
    put(
        root / "deedum.toml",
        'title = "T"\nbase_url = "https://e.test"\ncontent = "src/md"\n',
    )
    path = entry(load_site(root), "blog", "T")
    assert path == root / "src" / "md" / "blog" / "t.md"


def template(site: Site, text: str, collection: str = "blog") -> None:
    put(site.root / "templates" / "new" / f"{collection}.md", text)


def test_collection_template_is_used(site):
    template(
        site,
        "---\ntitle: {{ title | tojson }}\ndate: {{ date }}\nslug: {{ slug }}\n"
        "tags: [{{ collection }}]\n---\nBody\n",
    )
    path = entry(site, "blog", 'Ahoj: "svět" <b>')
    front = yaml.safe_load(path.read_text(encoding="utf-8").split("---")[1])
    assert front["title"] == 'Ahoj: "svět" <b>'
    assert front["tags"] == ["blog"]
    assert front["slug"] == "ahoj-svet-b"
    assert path.read_text(encoding="utf-8").endswith("Body\n")


def test_collection_template_is_not_html_escaped(site):
    template(site, "---\ntitle: x\n---\n{{ title }}\n")
    assert "<&>" in entry(site, "blog", "<&>", slug="s").read_text()


def test_other_collections_ignore_the_template(site):
    template(site, "---\ntitle: x\n---\nCUSTOM\n")
    assert "CUSTOM" not in entry(site, "notes", "T").read_text()


def test_template_with_an_undefined_variable_names_the_template(site):
    template(site, "---\ntitle: {{ nope }}\n---\n")
    before = tree(site.root)
    with pytest.raises(ContentError, match=r"new/blog\.md.*UndefinedError"):
        entry(site, "blog", "T")
    assert tree(site.root) == before


def test_template_syntax_and_runtime_errors_name_the_template(site):
    template(site, "{% if %}")
    with pytest.raises(ContentError, match=r"new/blog\.md"):
        entry(site, "blog", "T")
    template(site, "{{ 1 / 0 }}")
    with pytest.raises(ContentError, match=r"new/blog\.md.*ZeroDivision"):
        entry(site, "blog", "T")


def test_template_rendering_invalid_frontmatter_writes_nothing(site):
    template(site, "---\ntitle: [unclosed\n---\n")
    before = tree(site.root)
    with pytest.raises(ContentError, match=r"template blog\.md: would write"):
        entry(site, "blog", "T")
    assert tree(site.root) == before


def test_template_without_frontmatter_is_fine(site):
    template(site, "just {{ title }}\n")
    assert entry(site, "blog", "T").read_text() == "just T\n"


def test_unreadable_template_is_an_error(site):
    template(site, "x")
    (site.root / "templates" / "new" / "blog.md").write_bytes(b"\xff\xfe")
    with pytest.raises(ContentError, match=r"new/blog\.md"):
        entry(site, "blog", "T")
