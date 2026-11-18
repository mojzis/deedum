"""Jinja environment, page rendering and the built-in head (decision 0005)."""

from __future__ import annotations

import datetime as dt
from pathlib import Path
from typing import Any

import jinja2
from jinja2.runtime import Context
from markupsafe import Markup
from PIL import Image

from deedum.errors import RenderError
from deedum.site import Page, Site, _is_external, _split_suffix

_BUILTIN_DIR = Path(__file__).parent / "templates"
_HEAD = "deedum/head.html"


def _builtins() -> jinja2.FileSystemLoader:
    return jinja2.FileSystemLoader(_BUILTIN_DIR)


def _read_size(path: Path) -> tuple[int, int]:
    """Header-only image dimensions. Raises on anything Pillow can't read."""
    with Image.open(path) as img:
        return img.size


def _image_sizer(site: Site) -> Any:
    """``image_size(path)`` for templates: ``(w, h)`` or ``None``, cached."""
    static = (site.root / site.static).resolve()
    cache: dict[str, tuple[int, int] | None] = {}

    def image_size(path: str) -> tuple[int, int] | None:
        if path not in cache:
            cache[path] = _measure(static, path)
        return cache[path]

    return image_size


def _measure(static: Path, path: str) -> tuple[int, int] | None:
    if not path or _is_external(path):
        return None
    path = _split_suffix(path)[0]
    file = (static / path.lstrip("/")).resolve()
    if not file.is_relative_to(static) or not file.is_file():
        return None
    try:
        return _read_size(file)
    except (OSError, ValueError, Image.DecompressionBombError):
        return None


def _build_env(
    site: Site,
    loader: jinja2.BaseLoader,
    collections: dict[str, Any] | None,
    data: dict[str, Any] | None,
    now: dt.datetime | None,
) -> jinja2.Environment:
    env = jinja2.Environment(
        loader=loader,
        autoescape=True,
        undefined=jinja2.StrictUndefined,
        trim_blocks=True,
        lstrip_blocks=True,
    )

    @jinja2.pass_context
    def url(ctx: Context, path: str) -> str:
        page = ctx.get("page")
        # The 404 page is served at any depth: links must not be page-relative.
        if page is None or page.output == "404.html":
            return site.url(path)
        return site.url(path, current=page.url)

    globals_: dict[str, Any] = {
        "site": site,
        "url": url,
        "absolute": site.absolute,
        "collections": {} if collections is None else collections,
        "data": {} if data is None else data,
        "now": now if now is not None else dt.datetime.now(dt.UTC),
        "image_size": _image_sizer(site),
        # Trusted config, the one raw-HTML wrap besides the markdown body.
        "head_extra": Markup(site.head_extra),  # noqa: S704 -- trusted site config
    }
    env.globals.update(globals_)
    return env


def make_env(
    site: Site,
    *,
    collections: dict[str, Any] | None = None,
    data: dict[str, Any] | None = None,
    now: dt.datetime | None = None,
) -> jinja2.Environment:
    """Environment: target templates, then built-ins, then ``builtin/`` prefix."""
    loader = jinja2.ChoiceLoader(
        [
            jinja2.FileSystemLoader(site.root / site.templates),
            _builtins(),
            jinja2.PrefixLoader({"builtin": _builtins()}),
        ]
    )
    return _build_env(site, loader, collections, data, now)


def _location(env: jinja2.Environment, err: BaseException) -> str:
    """Template name and line where Jinja failed, or empty."""
    if isinstance(err, jinja2.TemplateSyntaxError):
        return f"{err.name}, line {err.lineno}" if err.name else f"line {err.lineno}"
    names = {t.filename: t.name for t in (env.cache or {}).values() if t is not None}
    where = ""
    tb = err.__traceback__
    while tb is not None:
        # Jinja rewrites template frames: marked by __jinja_exception__, file = path.
        if "__jinja_exception__" in tb.tb_frame.f_globals:
            file = tb.tb_frame.f_code.co_filename
            where = f"{names.get(file, file)}, line {tb.tb_lineno}"
        tb = tb.tb_next
    return where


def _render_msg(
    env: jinja2.Environment, err: Exception, name: str, page: Page, *, kind: bool
) -> str:
    where = _location(env, err)
    detail = f" ({where})" if where else ""
    what = f"{type(err).__name__}: {err}" if kind else str(err)
    return f"cannot render {name!r} for page {page.url!r}: {what}{detail}"


def render_page(
    env: jinja2.Environment,
    page: Page,
    *,
    template: str | None = None,
    **context: Any,
) -> str:
    """Render ``template`` (default: the page's own) with ``page`` in context."""
    name = template or page.template
    try:
        return env.get_template(name).render(page=page, **context)
    except jinja2.TemplateError as err:
        raise RenderError(_render_msg(env, err, name, page, kind=False)) from err
    except Exception as err:
        raise RenderError(_render_msg(env, err, name, page, kind=True)) from err


def head_tags(site: Site, page: Page) -> Markup:
    """The documented ``<head>`` tags, ignoring any target-site overrides."""
    env = _build_env(site, _builtins(), None, None, None)
    html = render_page(env, page, template=_HEAD)
    return Markup(html)  # noqa: S704 -- output of an autoescaped template
