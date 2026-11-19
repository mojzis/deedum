"""Lint a built folder: links, leftover template syntax, head metadata (R25).

See decision 0013 for what is an error and what is a warning. Read-only: never
follows a symlinked file or folder, and malformed HTML never raises.
"""

from __future__ import annotations

import posixpath
import re
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import unquote

from deedum.errors import ConfigError
from deedum.foreign import _INDEX, _Robots, html_files

_SCHEME = re.compile(r"^[A-Za-z][A-Za-z0-9+.-]*:")
_SRCSET_URL = re.compile(r"[\s,]*(\S+)")
_LEFTOVER = ("{{", "{%")
_QUIET = frozenset({"code", "pre", "script", "style", "textarea"})
_LINKS = {
    ("a", "href"),
    ("link", "href"),
    ("area", "href"),
    ("img", "src"),
    ("script", "src"),
    ("iframe", "src"),
    ("source", "src"),
    ("audio", "src"),
    ("video", "src"),
    ("track", "src"),
    ("embed", "src"),
    ("video", "poster"),
    ("object", "data"),
    ("img", "srcset"),
    ("source", "srcset"),
}


@dataclass(frozen=True, order=True)
class Finding:
    """One problem on one page. ``line`` 0 means the page as a whole."""

    page: str
    line: int
    level: str
    detail: str

    def __str__(self) -> str:
        where = f"line {self.line}: " if self.line else ""
        return f"{self.level} {self.page}: {where}{self.detail}"


@dataclass(frozen=True)
class CheckReport:
    """Pages checked and every finding, sorted by page then line."""

    pages: int
    findings: list[Finding] = field(default_factory=list)

    @property
    def errors(self) -> int:
        """How many findings are errors."""
        return sum(f.level == "error" for f in self.findings)

    @property
    def warnings(self) -> int:
        """How many findings are warnings."""
        return len(self.findings) - self.errors

    @property
    def summary(self) -> str:
        """The closing line of the printed report."""
        return (
            f"checked {self.pages} pages: "
            f"{self.errors} errors, {self.warnings} warnings"
        )


def _srcset_urls(value: str) -> list[str]:
    """Every URL of a ``srcset``, descriptors dropped."""
    urls, pos = [], 0
    while match := _SRCSET_URL.match(value, pos):
        url, pos = match.group(1), match.end()
        if url.endswith(","):
            url = url.rstrip(",")
        else:  # a descriptor follows, up to the next comma
            comma = value.find(",", pos)
            pos = len(value) if comma < 0 else comma + 1
        urls.append(url)
    return urls


class _Scan(_Robots):
    """Collects what the checks need from one page in a single pass."""

    def __init__(self) -> None:
        super().__init__()
        self.title: str | None = None
        self.canonical = False
        self.description = False
        self.og_image = False
        self.links: list[tuple[int, str]] = []
        self.leftovers: list[tuple[int, str]] = []
        self._quiet = 0
        self._in_title = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        super().handle_starttag(tag, attrs)
        line = self.getpos()[0]
        found = {k.lower(): (v or "") for k, v in attrs}
        self._quiet += tag in _QUIET
        if tag == "title":
            self._in_title = True
            self.title = self.title or ""
        for name, value in found.items():
            if any(mark in value for mark in _LEFTOVER):
                self.leftovers.append((line, f"in attribute {name!r} of <{tag}>"))
            if (tag, name) in _LINKS:
                urls = _srcset_urls(value) if name == "srcset" else [value]
                self.links.extend((line, url) for url in urls)
        self._note_head(tag, found)

    def _note_head(self, tag: str, found: dict[str, str]) -> None:
        rel = found.get("rel", "").lower().split()
        if tag == "link" and "canonical" in rel and found.get("href", "").strip():
            self.canonical = True
        if tag != "meta" or not found.get("content", "").strip():
            return
        if found.get("name", "").strip().lower() == "description":
            self.description = True
        if found.get("property", "").strip().lower() == "og:image":
            self.og_image = True

    def handle_endtag(self, tag: str) -> None:
        if tag in _QUIET:
            self._quiet = max(0, self._quiet - 1)
        if tag == "title":
            self._in_title = False

    def handle_data(self, data: str) -> None:
        if self._in_title:
            self.title = (self.title or "") + data
        if not self._quiet and any(mark in data for mark in _LEFTOVER):
            self.leftovers.append((self.getpos()[0], "in text"))


class _Resolver:
    """Decides whether a link from a page lands on something in the folder."""

    def __init__(self, folder: Path, base_path: str) -> None:
        self.folder = folder
        self.base_path = base_path
        self._exists: dict[str, bool] = {}

    def problem(self, page: str, url: str) -> str | None:
        """Why ``url`` (found on ``page``) is broken, or None when it is fine."""
        url = url.strip()
        if not url or _SCHEME.match(url) or url.startswith(("//", "#")):
            return None
        path = unquote(re.split(r"[?#]", url, maxsplit=1)[0])
        if not path:  # a bare query: the page itself
            return None
        if path.startswith("/"):
            if f"{path.rstrip('/')}/" == self.base_path:
                path = self.base_path
            if not path.startswith(self.base_path):
                return f"{url} is outside base path {self.base_path}"
            target = posixpath.normpath(path.removeprefix(self.base_path))
        else:
            target = posixpath.normpath(posixpath.join(posixpath.dirname(page), path))
        if target == ".." or target.startswith("../"):
            return f"{url} climbs above the site root"
        return None if self._found(target) else f"{url} is missing"

    def _found(self, target: str) -> bool:
        if target not in self._exists:
            self._exists[target] = self._lookup(target)
        return self._exists[target]

    def _lookup(self, target: str) -> bool:
        here = self.folder
        if target != ".":
            for part in target.split("/"):
                here = here / part
                if here.is_symlink():
                    return False
        return here.is_file() or (here / _INDEX).is_file()


def _check_page(page: str, text: str, resolver: _Resolver) -> list[Finding]:
    scan = _Scan()
    scan.feed(text)
    scan.close()
    found = [
        Finding(page, line, "error", f"leftover template syntax {where}")
        for line, where in scan.leftovers
    ]
    for line, url in scan.links:
        if why := resolver.problem(page, url):
            found.append(Finding(page, line, "error", why))
    if not scan.noindex:
        if not (scan.title or "").strip():
            found.append(Finding(page, 0, "error", "missing or empty <title>"))
        if not scan.canonical:
            found.append(Finding(page, 0, "error", "missing canonical link"))
        if not scan.description:
            found.append(Finding(page, 0, "warning", "missing meta description"))
        if not scan.og_image:
            found.append(Finding(page, 0, "warning", "missing og:image"))
    return found


def check_folder(folder: Path, base_path: str = "/") -> CheckReport:
    """Check every ``*.html`` page below ``folder`` served under ``base_path``.

    Raises ConfigError when ``folder`` is missing, not a folder, a symlink or in
    ``.git``.
    """
    folder = Path(folder)
    if folder.is_symlink() or not folder.is_dir():
        why = "a symlink" if folder.is_symlink() else "not an existing folder"
        msg = f"cannot check {str(folder)!r}: it is {why}"
        raise ConfigError(msg, hint="pass the folder your site was built into")
    if ".git" in folder.resolve().parts or ".git" in folder.parts:
        msg = f"cannot check {str(folder)!r}: it is or is inside a .git folder"
        raise ConfigError(msg, hint="pass the folder your site was built into")
    resolver = _Resolver(folder, base_path)
    findings: list[Finding] = []
    pages = 0
    for rel, path in html_files(folder):
        pages += 1
        text = path.read_bytes().decode("utf-8", errors="replace")
        findings.extend(_check_page(rel, text, resolver))
    return CheckReport(pages=pages, findings=sorted(findings))
