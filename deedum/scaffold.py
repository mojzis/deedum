"""Write new files into a user's site: ``init`` (R23) and ``new`` (R24).

Nothing here overwrites, deletes or writes through a symlink: every file is
created with exclusive create, and every folder on the way is checked first.
"""

from __future__ import annotations

import datetime as dt
import re
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path

import jinja2
import yaml

from deedum.config import DEEDUM_TOML, PYPROJECT, pyproject_facts
from deedum.content import validate_entry
from deedum.errors import ConfigError, ContentError, DeedumError
from deedum.site import Site

_NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]*")
_REPO = "https://github.com/mojzis/deedum"
WORKFLOW = ".github/workflows/pages.yml"

_CONFIG = """\
# deedum config. Every other key is listed by `deedum guide tune`.
title = "My site"                       # change me: the site title
base_url = "https://example.github.io"  # change me: scheme://host, no path
# base_path = "/repo/"          # path prefix; only for a project site
# description = ""              # default meta description
# lang = "en"                   # default page language
# author = ""                   # site author
# image = ""                    # default social image, a path under static/
# favicon = ""                  # square PNG (512 px or more) or SVG: makes the icon set
# theme_color = "#ffffff"       # #rgb or #rrggbb, for the web manifest
# twitter = ""                  # handle for twitter:site
# analytics = ""                # Plausible domain
# head_extra = ""               # raw HTML added to every head (trusted)
# relative_links = false        # page-relative instead of root-relative links
# feeds = []                    # collection names that get <name>/feed.xml
# llms = false                  # write llms.txt, llms-full.txt and index.md siblings
# robots_extra_sitemaps = []    # more absolute sitemap URLs for robots.txt
# content = "content"           # markdown folder, relative to this file
# templates = "templates"       # template overrides folder
# static = "static"             # files copied as they are
# data = "data"                 # yaml, toml or json files for templates
# out = "_site"                 # output folder; the build clears it
# app = "module:Class"          # a deedum.App subclass in a file next to this one
# allow_tracked_out = false     # let the build clear tracked files in out
"""

_HOME = """\
# Welcome

This is the home page. Edit `content/index.md`, then run `deedum build`.
"""

_PAGE = """\
{# An override example: this file replaces deedum's built-in page.html.
   Any template in this folder with the same name wins over the built-in one. #}
{% extends "deedum/base.html" %}
{% block content %}
<article><h1>{{ page.title }}</h1>{{ page.body }}</article>
{% endblock %}
"""

_WORKFLOW = """\
name: Pages
on:
  push:
    branches: [main]
  workflow_dispatch:
permissions:
  contents: read
  pages: write
  id-token: write
concurrency:
  group: pages
  cancel-in-progress: false
jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v7
      - uses: astral-sh/setup-uv@v10.3.3
        with:
          enable-cache: true
      - run: {command}
      - uses: actions/upload-pages-artifact@v5
        with:
          path: _site
  deploy:
    needs: build
    runs-on: ubuntu-latest
    environment:
      name: github-pages
      url: ${{{{ steps.deployment.outputs.page_url }}}}
    steps:
      - id: deployment
        uses: actions/deploy-pages@v5
"""


@dataclass(frozen=True)
class InitReport:
    """What ``init_site`` did: paths written, paths skipped (with why), hints."""

    written: list[str] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)
    hints: list[str] = field(default_factory=list)


def _prepare(root: Path, parts: tuple[str, ...]) -> str | None:
    """Create the folders ``parts`` below ``root``; why not, when one is in the way."""
    here = root
    for i, part in enumerate(parts):
        here = here / part
        name = "/".join(parts[: i + 1])
        if here.is_symlink():
            return f"{name} is a symlink"
        if not here.exists():
            here.mkdir()
        elif not here.is_dir():
            return f"{name} is not a folder"
    return None


def _create(root: Path, rel: str, text: str | None) -> str | None:
    """Write ``rel`` (a folder when ``text`` is None); the reason it was skipped."""
    parts = tuple(rel.rstrip("/").split("/"))
    if why := _prepare(root, parts[:-1]):
        return why
    path = root.joinpath(*parts)
    if text is None:
        if path.exists() or path.is_symlink():
            return "exists"
        path.mkdir()
        return None
    try:
        with path.open("x", encoding="utf-8") as handle:
            handle.write(text)
    except FileExistsError:
        return "exists"
    return None


def init_site(folder: Path) -> InitReport:
    """Scaffold a site in ``folder``: config, home page, template override, workflow.

    A path that exists is skipped and listed, never overwritten. A malformed
    ``pyproject.toml`` raises ConfigError before anything is written.
    """
    folder = Path(folder)
    has_table, listed = pyproject_facts(folder / PYPROJECT)
    pyproject = (folder / PYPROJECT).is_file()
    command = (
        "uv sync && uv run deedum build --check"
        if pyproject
        else f"uvx --from git+{_REPO} deedum build --check"
    )
    if folder.exists() and not folder.is_dir():
        msg = f"cannot init {str(folder)!r}: it is not a folder"
        raise ConfigError(msg)
    folder.mkdir(parents=True, exist_ok=True)
    plan: list[tuple[str, str | None]] = [
        (DEEDUM_TOML, _CONFIG),
        ("content/index.md", _HOME),
        ("templates/page.html", _PAGE),
        ("static/", None),
        (WORKFLOW, _WORKFLOW.format(command=command)),
    ]
    report = InitReport()
    for rel, text in plan:
        if rel == DEEDUM_TOML and has_table:
            why = f"{PYPROJECT} already has [tool.deedum]"
        else:
            why = _create(folder, rel, text)
        if why is None:
            report.written.append(rel)
        else:
            report.skipped.append(f"{rel} ({why})")
    if pyproject and not listed:
        report.hints.append("hint: run uv add deedum")
    return report


# ---- new -------------------------------------------------------------------


def slugify(title: str) -> str:
    """ASCII, lowercase, runs of other characters become one ``-``."""
    folded = unicodedata.normalize("NFKD", title).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "-", folded.lower()).strip("-")


def _valid_name(value: str, what: str) -> str:
    if not _NAME.fullmatch(value):
        msg = (
            f"invalid {what} {value!r}: use letters, digits, '-' and '_', "
            "starting with a letter or digit"
        )
        raise ConfigError(msg)
    return value


def _render(site: Site, collection: str, values: dict[str, str]) -> str | None:
    """The per-collection template's output, or None when there is no template."""
    rel = f"{site.templates}/new/{collection}.md"
    path = site.root / rel
    if not path.is_file():
        return None
    env = jinja2.Environment(
        undefined=jinja2.StrictUndefined,
        keep_trailing_newline=True,
        autoescape=False,  # noqa: S701 -- renders markdown, not HTML
    )
    try:
        return env.from_string(path.read_text(encoding="utf-8")).render(**values)
    except Exception as err:
        msg = f"template {rel}: {type(err).__name__}: {err}"
        raise ContentError(msg) from err


def _starter(title: str, when: dt.date) -> str:
    front = yaml.safe_dump(
        {"title": title, "date": when}, sort_keys=False, allow_unicode=True
    )
    return f"---\n{front}---\n\n"


def new_entry(
    site: Site,
    collection: str,
    title: str,
    *,
    slug: str | None = None,
    today: dt.date | None = None,
) -> Path:
    """Create ``<content>/<collection>/<slug>.md`` and return its path.

    Raises ConfigError for a bad collection, slug or empty derived slug, and
    DeedumError when the file exists or a folder on the way is a symlink.
    """
    _valid_name(collection, "collection")
    name = slugify(title) if slug is None else _valid_name(slug, "slug")
    if not name:
        msg = f"cannot derive a slug from {title!r}"
        raise ConfigError(msg, hint="pass --slug")
    when = today or dt.datetime.now().astimezone().date()
    rel = f"{site.content}/{collection}/{name}.md"
    values = {"title": title, "date": when.isoformat(), "slug": name}
    values["collection"] = collection
    rendered = _render(site, collection, values)
    text = _starter(title, when) if rendered is None else rendered
    try:
        validate_entry(text, rel)
    except ContentError as err:
        template = "" if rendered is None else f"template {collection}.md: "
        msg = f"{template}would write an invalid entry: {err}"
        raise ContentError(msg) from err
    content = Path(site.content)
    if content.is_absolute() or ".." in content.parts:
        msg = f"content folder {site.content!r} must be inside the site root"
        raise ConfigError(msg)
    if why := _prepare(site.root, (*content.parts, collection)):
        msg = f"refusing to write {rel}: {why}"
        raise DeedumError(msg)
    path = site.root / rel
    try:
        with path.open("x", encoding="utf-8") as handle:
            handle.write(text)
    except FileExistsError:
        msg = f"{rel} already exists"
        raise ContentError(msg, hint="pass --slug for a different file") from None
    return path
