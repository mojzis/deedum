"""Builder: clear the output folder safely, write pages, static files, extras.

See decisions 0006 (static vs extras), 0007 (tracked output) and 0008
(copying and clearing).
"""

from __future__ import annotations

import datetime as dt
import posixpath
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from markupsafe import Markup

from deedum.errors import ConfigError, ContentError, DeedumError
from deedum.extras import favicons as favicons_mod
from deedum.extras import feeds as feeds_mod
from deedum.extras import llms as llms_mod
from deedum.extras import (
    render_404,
    write_favicons,
    write_feeds,
    write_llms,
    write_nojekyll,
    write_robots,
    write_sitemap,
)
from deedum.render import make_env, render_page
from deedum.site import Page, Site

_KEEP = frozenset({".git", "CNAME"})
_MAX_LISTED = 5
_FAVICON_HINT = (
    "remove the static file, or keep the favicon source outside the static folder"
)
_GIT_TIMEOUT = 10
_EXTRAS = {
    "404.html": "404",
    "sitemap.xml": "sitemap",
    "robots.txt": "robots",
    ".nojekyll": "nojekyll",
}


@dataclass
class _Claims:
    """Output keys claimed so far. Two keys conflict when equal or nested."""

    origins: dict[str, str] = field(default_factory=dict)
    folders: dict[str, str] = field(default_factory=dict)

    def conflict(self, key: str) -> tuple[str, str] | None:
        """The (key, origin) already claimed that clashes with ``key``, if any."""
        if key in self.origins:
            return key, self.origins[key]
        if key in self.folders:
            below = self.folders[key]
            return below, self.origins[below]
        parts = key.split("/")
        for i in range(1, len(parts)):
            above = "/".join(parts[:i])
            if above in self.origins:
                return above, self.origins[above]
        return None

    def add(self, key: str, origin: str) -> None:
        """Record ``key`` and register each of its parent folders."""
        self.origins[key] = origin
        parts = key.split("/")
        for i in range(1, len(parts)):
            self.folders.setdefault("/".join(parts[:i]), key)

    def copy(self) -> _Claims:
        """An independent copy, for trial claims."""
        return _Claims(dict(self.origins), dict(self.folders))


def _clash(key: str, origin: str, other: tuple[str, str]) -> ContentError:
    other_key, other_origin = other
    if other_key == key:
        msg = f"output {key!r} is written by both {other_origin} and {origin}"
    else:
        msg = (
            f"output {key!r} ({origin}) clashes with {other_key!r} "
            f"({other_origin}): one is a file inside the other"
        )
    return ContentError(msg)


def _home() -> Path:
    """The user's home folder; a seam so tests never touch the real one."""
    return Path.home()


@dataclass(frozen=True)
class BuildReport:
    """What a finished build wrote: counts and the extras' output paths."""

    pages: int
    static: int
    extras: list[str] = field(default_factory=list)


def _refuse(out: Path, reason: str) -> ConfigError:
    return ConfigError(
        f"refusing to use {str(out)!r} as the output folder: {reason}",
        hint="pick a dedicated folder such as _site, or run `deedum extras` instead",
    )


def _check_out(site: Site, out: Path, raw: Path) -> None:
    """Raise ConfigError unless ``out`` is safe to clear (R19)."""
    if ".git" in out.parts or ".git" in raw.parts:
        raise _refuse(out, "it is or is inside a .git folder")
    if raw.is_symlink():
        raise _refuse(out, "it is a symlink")
    if out.exists() and not out.is_dir():
        raise _refuse(out, "it exists and is not a folder")
    if out.parent == out:
        raise _refuse(out, "it is the filesystem root")
    if out == _home().resolve():
        raise _refuse(out, "it is the home folder")
    root = site.root.resolve()
    if out == root or out in root.parents:
        raise _refuse(out, "it is the site root or a parent of it")
    for name in (site.content, site.templates, site.static, site.data):
        src = (root / name).resolve()
        if out == src or out in src.parents:
            raise _refuse(out, f"it contains or equals the source folder {name!r}")
        if src in out.parents:
            raise _refuse(out, f"it is inside the source folder {name!r}")


def _tracked_files(out: Path) -> list[str]:
    """Tracked files under ``out`` in the repo holding it; empty if unknowable."""
    git = shutil.which("git")
    if git is None:
        return []
    try:
        done = subprocess.run(  # noqa: S603 -- fixed argv, resolved git path, no shell
            [git, "ls-files", "-z"],
            cwd=out,
            capture_output=True,
            check=False,
            timeout=_GIT_TIMEOUT,
        )
    except (OSError, subprocess.TimeoutExpired):
        return []
    if done.returncode != 0:
        return []
    return [f.decode("utf-8", "replace") for f in done.stdout.split(b"\0") if f]


def _guard_tracked(out: Path) -> None:
    tracked = _tracked_files(out)
    if not tracked:
        return
    shown = ", ".join(tracked[:_MAX_LISTED])
    msg = (
        f"refusing to clear {str(out)!r}: {len(tracked)} tracked file(s) "
        f"under it ({shown}{', ...' if len(tracked) > _MAX_LISTED else ''})"
    )
    raise ConfigError(
        msg,
        hint="set allow_tracked_out = true in deedum.toml if you commit your output",
    )


def _clear(out: Path) -> None:
    """Delete every top-level entry but ``.git`` and ``CNAME``; never follow links."""
    for entry in out.iterdir():
        if entry.name in _KEEP:
            continue
        if entry.is_symlink() or not entry.is_dir():
            entry.unlink()
        else:
            shutil.rmtree(entry)


def output_for(path: str) -> str:
    """Site-relative URL path -> output file path, or ContentError."""
    if "\0" in path or "\\" in path or path.startswith("/"):
        msg = f"invalid page path {path!r}: must be relative, without NUL or backslash"
        raise ContentError(msg)
    if ".." in path.split("/"):
        msg = f"invalid page path {path!r}: must not contain '..'"
        raise ContentError(msg)
    segments = path.removesuffix("/").split("/") if path else []
    if any(seg in {"", "."} for seg in segments):
        msg = f"invalid page path {path!r}: empty or '.' segment"
        raise ContentError(msg)
    if path == "" or path.endswith("/"):
        path += "index.html"
    return posixpath.normpath(path)


class Builder:
    """Write one site build into ``out``.

    Construction validates the output folder, refuses when clearing it could
    destroy something that is not build output, then clears it. A failure
    mid-build (say a template error in ``render``) leaves the files already
    written in place: the output is partial and there is no rollback.
    ``finish`` is then never reached, so no sitemap claims a full site.
    A failed ``render`` keeps its path claimed, so restart the build with a
    new Builder.
    """

    def __init__(  # noqa: PLR0913 -- one keyword per documented knob
        self,
        site: Site,
        out: Path | str | None = None,
        *,
        force_clear: bool = False,
        collections: dict[str, Any] | None = None,
        data: dict[str, Any] | None = None,
        now: dt.datetime | None = None,
    ) -> None:
        """Validate and clear ``out`` (default ``site.root / site.out``)."""
        self.site = site
        raw = site.root / (site.out if out is None else out)
        self.out = raw.resolve()
        _check_out(site, self.out, raw)
        if self.out.exists() and not (force_clear or site.allow_tracked_out):
            _guard_tracked(self.out)
        self.out.mkdir(parents=True, exist_ok=True)
        _clear(self.out)
        self._now = now if now is not None else dt.datetime.now(dt.UTC)
        self.env = make_env(site, collections=collections, data=data, now=self._now)
        self._claims = _Claims()
        self._pages: list[Page] = []
        self._rendered = 0
        self._static = 0
        self._finished = False

    def _claim(self, output: str, origin: str) -> Path:
        """Record ``output`` as written by ``origin``; return its safe target."""
        key = posixpath.normpath(output)
        if ".git" in key.split("/"):
            msg = f"{origin} would write to a reserved path: {output!r}"
            raise ContentError(msg)
        if (other := self._claims.conflict(key)) is not None:
            raise _clash(key, origin, other)
        target = (self.out / key).resolve()
        if not target.is_relative_to(self.out) or target == self.out:
            msg = f"{origin} would write outside the output folder: {output!r}"
            raise ContentError(msg)
        self._claims.add(key, origin)
        return target

    def _check_open(self) -> None:
        if self._finished:
            msg = "this build is finished; make a new Builder"
            raise DeedumError(msg)

    def render(
        self,
        template: str,
        path: str,
        *,
        page: Page | None = None,
        **context: Any,
    ) -> Path:
        """Render ``template`` to the site-relative URL ``path``; return the file."""
        self._check_open()
        output = output_for(path)
        if output == "CNAME":
            msg = "render would overwrite the reserved CNAME file"
            raise ContentError(msg)
        if page is None:
            page = Page(
                url=path,
                output=output,
                title=context.get("title", self.site.title),
                description=context.get("description", self.site.description),
                body=Markup(""),
                source="",
                template=template,
                lang=self.site.lang,
            )
        elif posixpath.normpath(page.output) != output:
            msg = f"page {page.url!r} has output {page.output!r}, not {output!r}"
            raise ContentError(msg)
        target = self._claim(output, f"page {page.url!r} ({template})")
        html = render_page(self.env, page, template=template, **context)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(html, encoding="utf-8")
        self._rendered += 1
        if output.endswith(".html"):
            self._pages.append(page)
        return target

    def copy_static(self, src: Path | str | None = None) -> int:
        """Copy regular files from the static folder, skipping symlinks and .git."""
        self._check_open()
        base = Path(self.site.root / self.site.static if src is None else src)
        if not base.is_dir():
            return 0
        resolved = base.resolve()
        if (
            resolved == self.out
            or self.out in resolved.parents
            or resolved in self.out.parents
        ):
            msg = (
                f"static source {str(resolved)!r} and output folder "
                f"{str(self.out)!r} are the same, or one is inside the other"
            )
            raise ContentError(msg)
        count = 0
        stack = [base]
        while stack:
            for entry in sorted(stack.pop().iterdir()):
                if entry.is_symlink() or entry.name == ".git":
                    continue
                if entry.is_dir():
                    stack.append(entry)
                elif entry.is_file():
                    rel = entry.relative_to(base).as_posix()
                    target = self._claim(rel, f"static file {str(entry)!r}")
                    target.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(entry, target)
                    count += 1
        self._static += count
        return count

    def _planned_extras(self) -> list[tuple[str, str]]:
        """Every (output path, label) ``finish`` will write, in write order."""
        site = self.site
        planned = [(name, f"extra:{label}") for name, label in _EXTRAS.items()]
        planned += [(n, "extra:favicon") for n in favicons_mod.output_names(site)]
        for name in dict.fromkeys(site.feeds):
            planned.append((feeds_mod.feed_path(name), f"extra:feed:{name}"))
        if site.llms:
            names = [
                llms_mod.SHORT,
                llms_mod.FULL,
                *llms_mod.sibling_paths(self._pages),
            ]
            planned += [(n, "extra:llms") for n in names]
        return planned

    def finish(self) -> BuildReport:
        """Write the 404 page, sitemap, robots, ``.nojekyll``, icons, feeds, llms.

        Collisions and the favicon source are checked before anything is
        claimed or written, so a failure leaves the build untouched.
        """
        self._check_open()
        planned = self._planned_extras()
        trial = self._claims.copy()
        for name, label in planned:
            key = posixpath.normpath(name)
            if (other := trial.conflict(key)) is not None:
                error = _clash(key, label, other)
                if label == "extra:favicon":
                    error.hint = _FAVICON_HINT
                raise error
            trial.add(key, label)
        master = favicons_mod.load_master(self.site)
        for name, label in planned:
            self._claim(name, label)
        written = [
            render_404(self.env, self.site, self.out),
            write_sitemap(self.site, self._pages, self.out),
            write_robots(self.site, self.out),
            write_nojekyll(self.out),
            *write_favicons(self.site, self.out, master),
            *write_feeds(self.site, self._pages, self.out, self._now),
            *write_llms(self.site, self._pages, self.out),
        ]
        self._finished = True
        return BuildReport(
            pages=self._rendered,
            static=self._static,
            extras=[p.relative_to(self.out).as_posix() for p in written],
        )
