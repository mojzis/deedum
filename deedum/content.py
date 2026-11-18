"""Read a target site's content and data folders (R7, R8, R9). Writes nothing."""

from __future__ import annotations

import json
import re
import tomllib
from collections.abc import Callable, Iterable, Mapping
from datetime import UTC, date, datetime, time
from pathlib import Path
from typing import Any

import yaml
from markdown_it import MarkdownIt
from markdown_it.token import Token
from markupsafe import Markup

from deedum.errors import ContentError
from deedum.site import Page, Site

_MD = MarkdownIt("commonmark").enable("table")
_DESCRIPTION_MAX = 160
_STR_KEYS = ("title", "description", "slug", "template", "image", "lang")
_BOOL_KEYS = ("draft", "noindex")
_RESERVED = ("url", "output", "body", "source", "collection", "meta", "source_path")
_DATA_SUFFIXES = (".yaml", ".yml", ".toml", ".json")
_SPACES = re.compile(r"\s+")


def _rel(site: Site, path: Path) -> str:
    return path.relative_to(site.root).as_posix()


# ---- frontmatter -----------------------------------------------------------


def _split_frontmatter(text: str, rel: str) -> tuple[str, str | None]:
    """Return ``(body, yaml_text)``; ``yaml_text`` is None without frontmatter."""
    lines = text.splitlines(keepends=True)
    if not lines or lines[0].rstrip() != "---":
        return text, None
    for i in range(1, len(lines)):
        if lines[i].rstrip() == "---":
            return "".join(lines[i + 1 :]), "".join(lines[1:i])
    msg = f"{rel}: frontmatter opened with '---' is never closed"
    raise ContentError(msg, hint="add a closing '---' line after the frontmatter")


def _parse_frontmatter(yaml_text: str, rel: str) -> dict[str, Any]:
    try:
        data = yaml.safe_load(yaml_text)
    except yaml.YAMLError as err:
        msg = f"{rel}: invalid frontmatter YAML: {err}"
        raise ContentError(msg) from err
    if data is None:
        return {}
    if not isinstance(data, dict):
        msg = f"{rel}: frontmatter must be a mapping, got {type(data).__name__}"
        raise ContentError(msg)
    for key in data:
        if not isinstance(key, str):
            msg = f"{rel}: frontmatter key {key!r} must be a string"
            raise ContentError(msg)
    return data


def _check_types(meta: Mapping[str, Any], rel: str) -> None:
    for key in _RESERVED:
        if key in meta:
            msg = f"{rel}: frontmatter key {key!r} is reserved: deedum derives it"
            raise ContentError(msg)
    for key in _STR_KEYS:
        if key in meta and not isinstance(meta[key], str):
            msg = f"{rel}: frontmatter key {key!r} must be a string"
            raise ContentError(msg)
    for key in _BOOL_KEYS:
        if key in meta and not isinstance(meta[key], bool):
            msg = f"{rel}: frontmatter key {key!r} must be true or false"
            raise ContentError(msg, hint=f"write `{key}: true`, without quotes")
    alt = meta.get("alternates", {})
    if not isinstance(alt, Mapping) or not all(
        isinstance(k, str) and isinstance(v, str) for k, v in alt.items()
    ):
        msg = f"{rel}: frontmatter key 'alternates' must map language to path (strings)"
        raise ContentError(msg)


def _as_date(value: Any, key: str, rel: str) -> date | datetime | None:
    """A YAML date/datetime or ISO string; naive datetimes become UTC."""
    if value is None:
        return None
    if isinstance(value, str):
        try:
            value = date.fromisoformat(value)
        except ValueError:
            try:
                value = datetime.fromisoformat(value)
            except ValueError:
                msg = (
                    f"{rel}: frontmatter key {key!r}: {value!r} is not an ISO 8601 date"
                )
                raise ContentError(msg, hint="example: 2024-03-01") from None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=UTC)
    if isinstance(value, date):
        return value
    msg = f"{rel}: frontmatter key {key!r} must be a date or ISO 8601 string"
    raise ContentError(msg)


def _read_text(path: Path, rel: str) -> str:
    try:
        return path.read_text(encoding="utf-8-sig")
    except UnicodeDecodeError as err:
        msg = f"{rel}: not valid UTF-8 ({err.reason} at byte {err.start})"
        raise ContentError(msg) from err
    except OSError as err:
        msg = f"{rel}: cannot read file ({err.strerror})"
        raise ContentError(msg) from err


# ---- markdown --------------------------------------------------------------


def _plain_text(inline: Token) -> str:
    """Text and inline-code content of an inline token; images are dropped."""
    parts: list[str] = []
    for child in inline.children or []:
        if child.type in ("text", "code_inline"):
            parts.append(child.content)
        elif child.type in ("softbreak", "hardbreak"):
            parts.append(" ")
    return _SPACES.sub(" ", "".join(parts)).strip()


def _take_h1(tokens: list[Token]) -> tuple[str | None, list[Token]]:
    """Return the first h1's text and the tokens without it."""
    for i, tok in enumerate(tokens[:-2]):
        if tok.type == "heading_open" and tok.tag == "h1":
            return _plain_text(tokens[i + 1]), tokens[:i] + tokens[i + 3 :]
    return None, tokens


def _truncate(text: str) -> str:
    if len(text) <= _DESCRIPTION_MAX:
        return text
    head = text[: _DESCRIPTION_MAX - 1]
    if not text[_DESCRIPTION_MAX - 1].isspace():
        cut = max((m.start() for m in _SPACES.finditer(head)), default=0)
        head = head[:cut] if cut else head
    return f"{head.rstrip()}…"


def _first_paragraph(tokens: list[Token]) -> str:
    for i, tok in enumerate(tokens[:-1]):
        if tok.type == "paragraph_open" and tok.level == 0:
            return _truncate(_plain_text(tokens[i + 1]))
    return ""


# ---- pages -----------------------------------------------------------------


def _find_markdown(folder: Path) -> list[Path]:
    found: list[Path] = []
    for entry in sorted(folder.iterdir()):
        if entry.name.startswith(("_", ".")):
            continue
        if entry.is_dir():
            found.extend(_find_markdown(entry))
        elif entry.suffix == ".md" and entry.is_file():
            found.append(entry)
    return found


def _url_for(rel_parts: tuple[str, ...], slug: str | None, rel: str) -> str:
    *dirs, name = rel_parts
    stem = name.removesuffix(".md")
    if stem == "index":
        if slug is not None:
            msg = f"{rel}: 'slug' is not allowed on an index.md"
            raise ContentError(msg)
        return "/".join(dirs) + "/" if dirs else ""
    if slug is not None:
        if not slug or "/" in slug or slug in (".", ".."):
            msg = (
                f"{rel}: frontmatter key 'slug' {slug!r} must be a single path segment"
            )
            raise ContentError(msg)
        stem = slug
    return "/".join([*dirs, stem]) + "/"


def _fallback_title(site: Site, rel_parts: tuple[str, ...]) -> str:
    *dirs, name = rel_parts
    stem = name.removesuffix(".md")
    if stem != "index":
        return stem
    return dirs[-1] if dirs else site.title


def _template_for(site: Site, collection: str, meta: Mapping[str, Any]) -> str:
    if "template" in meta:
        return meta["template"]
    if collection and (site.root / site.templates / f"{collection}.html").exists():
        return f"{collection}.html"
    return "page.html"


def _load_page(site: Site, path: Path, rel: str) -> Page | None:
    content_root = site.root / site.content
    rel_parts = path.relative_to(content_root).parts
    body_text, yaml_text = _split_frontmatter(_read_text(path, rel), rel)
    meta = {} if yaml_text is None else _parse_frontmatter(yaml_text, rel)
    _check_types(meta, rel)
    if meta.get("draft"):
        return None
    url = _url_for(rel_parts, meta.get("slug"), rel)
    tokens = _MD.parse(body_text)
    description = meta.get("description") or _first_paragraph(tokens)
    h1, rendered = (None, tokens) if "title" in meta else _take_h1(tokens)
    title = meta.get("title") or h1 or _fallback_title(site, rel_parts)
    html = _MD.renderer.render(rendered, _MD.options, {})
    collection = rel_parts[0] if len(rel_parts) > 1 else ""
    return Page(
        url=url,
        output=f"{url}index.html",
        title=title,
        description=description,
        body=Markup(html),  # noqa: S704 -- owner-authored markdown, marked safe once here
        source=body_text,
        template=_template_for(site, collection, meta),
        date=_as_date(meta.get("date"), "date", rel),
        updated=_as_date(meta.get("updated"), "updated", rel),
        collection=collection,
        image=meta.get("image", ""),
        noindex=meta.get("noindex", False),
        lang=meta.get("lang", site.lang),
        alternates=dict(meta.get("alternates", {})),
        meta=meta,
        source_path=path,
    )


def load_pages(site: Site) -> list[Page]:
    """Every ``content/**/*.md`` as a Page, sorted by url. No folder gives ``[]``."""
    content_root = site.root / site.content
    if not content_root.is_dir():
        return []
    pages: dict[str, Page] = {}
    for path in _find_markdown(content_root):
        rel = _rel(site, path)
        page = _load_page(site, path, rel)
        if page is None:
            continue
        if page.url in pages and pages[page.url].source_path is not None:
            first = _rel(site, pages[page.url].source_path)  # ty: ignore[invalid-argument-type]
            msg = f"{rel} and {first} both produce url '/{page.url}'"
            raise ContentError(msg, hint="rename one file or give it a `slug`")
        pages[page.url] = page
    return [pages[url] for url in sorted(pages)]


# ---- collections and data --------------------------------------------------


def _sort_key(page: Page) -> tuple[int, float, str, str]:
    when = page.date
    if when is None:
        return (1, 0.0, page.title, page.url)
    if not isinstance(when, datetime):
        when = datetime.combine(when, time(), tzinfo=UTC)
    return (0, -when.timestamp(), page.title, page.url)


def build_collections(pages: Iterable[Page]) -> dict[str, list[Page]]:
    """Group pages by collection, minus each collection's own index page."""
    groups: dict[str, list[Page]] = {}
    for page in pages:
        if page.collection and page.url != f"{page.collection}/":
            groups.setdefault(page.collection, []).append(page)
    return {name: sorted(items, key=_sort_key) for name, items in groups.items()}


def _load_yaml(text: str) -> Any:
    return yaml.safe_load(text)


_PARSERS: dict[str, tuple[Callable[[str], Any], tuple[type[Exception], ...]]] = {
    ".yaml": (_load_yaml, (yaml.YAMLError,)),
    ".yml": (_load_yaml, (yaml.YAMLError,)),
    ".toml": (tomllib.loads, (tomllib.TOMLDecodeError,)),
    ".json": (json.loads, (json.JSONDecodeError,)),
}


def load_data(site: Site) -> dict[str, Any]:
    """Parse the top-level files of the data folder, keyed by file stem."""
    folder = site.root / site.data
    if not folder.is_dir():
        return {}
    data: dict[str, Any] = {}
    seen: dict[str, str] = {}
    for path in sorted(folder.iterdir()):
        if path.suffix not in _DATA_SUFFIXES or not path.is_file():
            continue
        rel = _rel(site, path)
        if path.stem in seen:
            msg = f"{rel} and {seen[path.stem]} both define data '{path.stem}'"
            raise ContentError(msg, hint="keep one file per name")
        seen[path.stem] = rel
        parse, errors = _PARSERS[path.suffix]
        try:
            data[path.stem] = parse(_read_text(path, rel))
        except errors as err:
            msg = f"{rel}: cannot parse {path.suffix} data: {err}"
            raise ContentError(msg) from err
    return data
