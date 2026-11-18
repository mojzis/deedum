"""The Site: validated configuration plus the URL model (decision 0003)."""

from __future__ import annotations

import posixpath
import re
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit

from deedum.errors import ConfigError

_SCHEME = re.compile(r"^[A-Za-z][A-Za-z0-9+.-]*:")
_TWITTER = re.compile(r"^@?\w+$")


def normalise_base_url(value: str, source: str) -> str:
    """Return ``scheme://host[:port]`` without a trailing slash, or raise.

    ``source`` names where the value came from and prefixes the error message.
    """
    try:
        parts = urlsplit(value)
        port = parts.port  # noqa: F841 -- accessing it validates the port
    except ValueError as err:
        msg = f"{source}: invalid base_url {value!r} ({err})"
        raise ConfigError(msg) from err
    if parts.scheme not in ("http", "https") or not parts.hostname:
        msg = f"{source}: base_url {value!r} must be http(s)://host[:port]"
        raise ConfigError(msg, hint="example: https://mojzis.github.io")
    if parts.path.strip("/") or parts.query or parts.fragment:
        msg = f"{source}: base_url {value!r} must not have a path, query or fragment"
        raise ConfigError(
            msg, hint="put the path in base_path, e.g. base_path = '/aesop/'"
        )
    return f"{parts.scheme}://{parts.netloc}"


def normalise_base_path(value: str) -> str:
    """One leading and one trailing slash, runs of slashes collapsed."""
    inner = "/".join(seg for seg in value.split("/") if seg)
    return f"/{inner}/" if inner else "/"


def normalise_twitter(value: str, source: str) -> str:
    """Return the handle with a leading ``@`` (empty stays empty)."""
    value = value.strip()
    if not value:
        return ""
    if not _TWITTER.match(value):
        msg = f"{source}: twitter handle {value!r} must be letters, digits or _"
        raise ConfigError(msg)
    return value if value.startswith("@") else f"@{value}"


def _split_suffix(path: str) -> tuple[str, str]:
    """Split ``path`` into the path proper and its ``?query#fragment`` tail."""
    cut = min(
        (i for i in (path.find("?"), path.find("#")) if i >= 0), default=len(path)
    )
    return path[:cut], path[cut:]


@dataclass(frozen=True)
class Site:
    """Site configuration. Folder names are relative to ``root``."""

    title: str
    base_url: str
    description: str = ""
    base_path: str = "/"
    lang: str = "en"
    author: str = ""
    image: str = ""
    favicon: str = ""
    twitter: str = ""
    analytics: str = ""
    head_extra: str = ""
    relative_links: bool = False
    feeds: tuple[str, ...] = ()
    llms: bool = False
    robots_extra_sitemaps: tuple[str, ...] = ()
    content: str = "content"
    templates: str = "templates"
    static: str = "static"
    data: str = "data"
    out: str = "_site"
    app: str = ""
    theme_color: str = "#ffffff"
    root: Path = Path()

    def __post_init__(self) -> None:
        """Normalise and validate the fields whose format matters."""
        set_ = object.__setattr__
        set_(self, "base_url", normalise_base_url(self.base_url, "Site(base_url)"))
        set_(self, "base_path", normalise_base_path(self.base_path))
        set_(self, "twitter", normalise_twitter(self.twitter, "Site(twitter)"))
        set_(self, "feeds", tuple(self.feeds))
        set_(self, "robots_extra_sitemaps", tuple(self.robots_extra_sitemaps))

    def _root_relative(self, path: str) -> str:
        body, suffix = _split_suffix(path)
        return f"{self.base_path}{body.lstrip('/')}{suffix}"

    def url(self, path: str, *, current: str | None = None) -> str:
        """Link to ``path``: root-relative, or page-relative from ``current``.

        ``current`` is the rendered page's site-relative URL (``""`` for home).
        """
        if _is_external(path):
            return path
        if not self.relative_links or current is None:
            return self._root_relative(path)
        body, suffix = _split_suffix(path)
        body = body.lstrip("/")
        here = current.rpartition("/")[0]
        # Anchor both at "/" so relpath never consults the working directory.
        rel = posixpath.relpath(f"/{body}", f"/{here}")
        if body == "" or body.endswith("/"):
            rel = "./" if rel == "." else f"{rel}/"
        return rel + suffix

    def absolute(self, path: str) -> str:
        """Full URL for ``path``, always absolute."""
        if _is_external(path):
            return path
        return self.base_url + self._root_relative(path)


def _is_external(path: str) -> bool:
    return bool(_SCHEME.match(path)) or path.startswith(("//", "#"))
