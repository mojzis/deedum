"""llms.txt, llms-full.txt and index.md siblings (R17, decision 0011)."""

from __future__ import annotations

import re
from collections.abc import Iterable
from pathlib import Path

from deedum.extras.feeds import page_stamp
from deedum.site import Page, Site

SHORT = "llms.txt"
FULL = "llms-full.txt"
_NOT_FOUND = "404.html"
_SIBLING_OF = "index.html"
_ESCAPE = re.compile(r"([\[\]\\])")


def listed(pages: Iterable[Page]) -> list[Page]:
    """Pages the llms files cover: indexable, not the 404."""
    return [p for p in pages if not p.noindex and p.output != _NOT_FOUND]


def sibling_path(page: Page) -> str | None:
    """Site-relative ``index.md`` path for ``page``, or None when it gets none."""
    if not page.source or not page.output.endswith(_SIBLING_OF):
        return None
    return page.output.removesuffix(_SIBLING_OF) + "index.md"


def sibling_paths(pages: Iterable[Page]) -> list[str]:
    """Every ``index.md`` sibling path the listed pages would write."""
    return [s for p in listed(pages) if (s := sibling_path(p))]


def _in_group(name: str, pages: list[Page]) -> list[Page]:
    """Collection index first, dated newest first, then undated by title."""
    index = [p for p in pages if name and p.url == f"{name}/"]
    rest = [p for p in pages if p not in index]
    dated = sorted((p for p in rest if p.date is not None), key=lambda p: p.url)
    dated.sort(key=page_stamp, reverse=True)
    undated = sorted(
        (p for p in rest if p.date is None), key=lambda p: (p.title.casefold(), p.url)
    )
    return index + dated + undated


def _order(pages: list[Page]) -> list[tuple[str, list[Page]]]:
    """Groups in output order: root pages, then collections by name."""
    groups: dict[str, list[Page]] = {}
    for page in pages:
        groups.setdefault(page.collection, []).append(page)
    return [
        (name, _in_group(name, groups[name]))
        for name in sorted(groups, key=lambda n: (n != "", n))
    ]


def _header(site: Site) -> list[str]:
    lines = [f"# {site.title}", ""]
    if site.description:
        lines += [f"> {_oneline(site.description)}", ""]
    return lines


def _oneline(text: str) -> str:
    return " ".join(text.split())


def _line(site: Site, page: Page) -> str:
    title = _ESCAPE.sub(r"\\\1", _oneline(page.title))
    line = f"- [{title}]({site.absolute(page.url)})"
    if description := _oneline(page.description):
        line += f": {description}"
    return line


def _short(site: Site, groups: list[tuple[str, list[Page]]]) -> str:
    lines = _header(site)
    for name, pages in groups:
        lines += [f"## {name or 'Pages'}", ""]
        lines += [_line(site, p) for p in pages]
        lines.append("")
    return "\n".join(lines).rstrip("\n") + "\n"


def _full(site: Site, groups: list[tuple[str, list[Page]]]) -> str:
    lines = _header(site)
    for _, pages in groups:
        for page in pages:
            if page.source:
                lines += ["---", "", f"URL: {site.absolute(page.url)}", ""]
                lines += [page.source.rstrip("\n"), ""]
    return "\n".join(lines).rstrip("\n") + "\n"


def _write(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        handle.write(text)
    return path


def write_llms(site: Site, pages: Iterable[Page], out: Path) -> list[Path]:
    """Write the llms files and ``index.md`` siblings into ``out`` if enabled."""
    if not site.llms:
        return []
    chosen = listed(pages)
    groups = _order(chosen)
    written = [
        _write(out / SHORT, _short(site, groups)),
        _write(out / FULL, _full(site, groups)),
    ]
    for page in chosen:
        if (sibling := sibling_path(page)) is not None:
            (out / sibling).parent.mkdir(parents=True, exist_ok=True)
            (out / sibling).write_bytes(page.source.encode("utf-8"))
            written.append(out / sibling)
    return written
