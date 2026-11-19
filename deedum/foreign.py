"""Extras for a folder something else built: sitemap, robots, icons, .nojekyll (R21).

See decision 0012: existing target files are skipped unless ``overwrite``.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from html.parser import HTMLParser
from pathlib import Path

from markupsafe import Markup

from deedum.errors import ConfigError
from deedum.extras import (
    favicons,
    robots,
    sitemap,
    write_favicons,
    write_nojekyll,
    write_robots,
    write_sitemap,
)
from deedum.extras.nojekyll import NAME as NOJEKYLL
from deedum.render import favicon_links
from deedum.site import Page, Site

_NOT_FOUND = "404.html"
_INDEX = "index.html"


@dataclass(frozen=True)
class ExtrasReport:
    """What ``write_extras`` did: pages listed, files written and skipped."""

    pages: int
    written: list[str] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)
    links: str = ""


class _Robots(HTMLParser):
    """Finds ``<meta name="robots" content="...noindex...">`` anywhere in a page."""

    def __init__(self) -> None:
        super().__init__()
        self.noindex = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag != "meta":
            return
        found = {k.lower(): (v or "") for k, v in attrs}
        if found.get("name", "").strip().lower() == "robots":
            self.noindex = self.noindex or "noindex" in found.get("content", "").lower()


def _is_noindex(path: Path) -> bool:
    parser = _Robots()
    parser.feed(path.read_bytes().decode("utf-8", errors="replace"))
    parser.close()
    return parser.noindex


def _url(rel: str) -> str:
    """``x/index.html`` -> ``x/``; the root index -> ``""``; others unchanged."""
    if rel == _INDEX:
        return ""
    if rel.endswith(f"/{_INDEX}"):
        return rel.removesuffix(_INDEX)
    return rel


def _scan(site: Site, folder: Path) -> list[Page]:
    """Indexable ``*.html`` pages below ``folder``; no links, dot-folders or noindex."""
    pages = []
    for here, dirs, files in os.walk(folder):
        base = Path(here)
        dirs[:] = sorted(
            d for d in dirs if not d.startswith(".") and not (base / d).is_symlink()
        )
        for name in sorted(files):
            path = base / name
            if not name.endswith(".html") or path.is_symlink() or not path.is_file():
                continue
            rel = path.relative_to(folder).as_posix()
            if rel == _NOT_FOUND or _is_noindex(path):
                continue
            pages.append(
                Page(
                    url=_url(rel),
                    output=rel,
                    title="",
                    description="",
                    body=Markup(""),
                    source="",
                    template="",
                    lang=site.lang,
                )
            )
    return pages


def _refuse(folder: Path, why: str) -> ConfigError:
    return ConfigError(
        f"refusing to add extras to {str(folder)!r}: {why}",
        hint="pass the folder your site was built into",
    )


def _check_folder(folder: Path) -> Path:
    if folder.is_symlink():
        raise _refuse(folder, "it is a symlink")
    if not folder.is_dir():
        raise _refuse(folder, "it is not an existing folder")
    resolved = folder.resolve()
    if ".git" in resolved.parts or ".git" in folder.parts:
        raise _refuse(folder, "it is or is inside a .git folder")
    return resolved


def write_extras(site: Site, folder: Path, *, overwrite: bool = False) -> ExtrasReport:
    """Add sitemap, robots, favicons and ``.nojekyll`` to ``folder``.

    Never deletes, never edits an ``.html`` file. A target that exists is
    skipped unless ``overwrite`` (a folder is always skipped). Refuses when
    ``folder`` is a symlink or in ``.git``, or when any target is a symlink,
    before anything is written.
    """
    out = _check_folder(Path(folder))
    icons = favicons.output_names(site)
    targets = [sitemap.NAME, robots.NAME, NOJEKYLL, *icons]
    for name in targets:
        if (out / name).is_symlink():
            msg = f"{name} in {str(out)!r} is a symlink: a write could leave the folder"
            raise _refuse(out, msg)
    master = favicons.load_master(site)
    pages = _scan(site, out)
    skipped = [
        n
        for n in targets
        if (out / n).exists() and (not overwrite or (out / n).is_dir())
    ]
    if sitemap.NAME not in skipped:
        write_sitemap(site, pages, out)
    if robots.NAME not in skipped:
        write_robots(site, out)
    if NOJEKYLL not in skipped:
        write_nojekyll(out)
    write_favicons(site, out, master, skip=skipped)
    return ExtrasReport(
        pages=len(pages),
        written=[n for n in targets if n not in skipped],
        skipped=skipped,
        links=favicon_links(site),
    )
