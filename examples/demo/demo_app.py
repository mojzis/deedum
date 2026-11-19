"""The demo's App: pages from data, and one small use of every other hook."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

import deedum
from deedum import DeedumError, Page

_FIELDS = ("slug", "name", "summary", "url")


def _plural(count: int, word: str) -> str:
    return f"{count} {word}" if count == 1 else f"{count} {word}s"


def _human_date(value: Any) -> str:
    return f"{value:%-d %B %Y}"


class DemoApp(deedum.App):
    """Adds one page per entry of ``data/tools.yaml`` to the markdown pages."""

    def __init__(self, site: deedum.Site) -> None:
        """Keep the pages ``load_pages`` made, for ``context``."""
        super().__init__(site)
        self._posts: list[Page] = []
        self._tools: list[dict[str, str]] = []

    def _entries(self) -> list[dict[str, str]]:
        entries = self.data.get("tools")
        if not isinstance(entries, list):
            msg = "data/tools.yaml must be a list of entries"
            raise DeedumError(msg)
        seen: set[str] = set()
        for number, entry in enumerate(entries, start=1):
            if not isinstance(entry, dict):
                msg = f"data/tools.yaml entry {number}: expected a mapping"
                raise DeedumError(msg)
            for key in _FIELDS:
                if not isinstance(entry.get(key), str) or not entry[key].strip():
                    msg = f"data/tools.yaml entry {number}: missing or empty {key!r}"
                    raise DeedumError(msg)
            if entry["slug"] in seen:
                msg = (
                    f"data/tools.yaml entry {number}: duplicate slug {entry['slug']!r}"
                )
                raise DeedumError(msg)
            seen.add(entry["slug"])
        return entries

    def load_pages(self) -> list[Page]:
        """The markdown pages, a tools listing and one page per tool."""
        pages = super().load_pages()
        self._posts = [p for p in pages if p.collection == "blog" and p.url != "blog/"]
        self._tools = self._entries()
        pages.append(
            self.page(
                "tools/",
                title="Tools",
                description="The tools this demo is about.",
                template="tool.html",
                collection="tools",
                source="# Tools\n\n"
                + "\n".join(f"- {t['name']}: {t['summary']}" for t in self._tools),
            )
        )
        pages.extend(
            self.page(
                f"tools/{tool['slug']}/",
                title=tool["name"],
                description=tool["summary"],
                template="tool.html",
                collection="tools",
                source=f"# {tool['name']}\n\n{tool['summary']}\n",
            )
            for tool in self._tools
        )
        return pages

    def context(self, page: Page) -> dict[str, Any]:
        """``tools`` for the listing, ``tool`` on a tool page, ``related`` on posts."""
        if page.url == "tools/":
            return {"tools": self._tools}
        if page.url.startswith("tools/"):
            slug = page.url.split("/")[1]
            return {"tool": next(t for t in self._tools if t["slug"] == slug)}
        if page.collection == "blog" and page.url != "blog/":
            return {"related": [p for p in self._posts if p.url != page.url]}
        return {}

    def filters(self) -> dict[str, Callable[..., Any]]:
        """``human_date`` and ``plural`` for the templates."""
        return {"human_date": _human_date, "plural": _plural}

    def globals(self) -> dict[str, Any]:
        """The navigation links every page shows."""
        return {
            "nav": [
                ("Home", ""),
                ("Blog", "blog/"),
                ("Tools", "tools/"),
                ("About", "about/"),
            ]
        }

    def after_build(self, out: Path) -> None:
        """Write ``humans.txt`` from the config; nothing in it varies per run."""
        lines = [
            f"Site: {self.site.title}",
            f"Author: {self.site.author}",
            f"Language: {self.site.lang}",
            f"Tools: {len(self._tools)}",
        ]
        (out / "humans.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
