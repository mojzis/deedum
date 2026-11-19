"""The convention build: ``App`` hooks, loading the app class, ``build()`` (R11)."""

from __future__ import annotations

import datetime as dt
import importlib.util
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

from markupsafe import Markup

from deedum.builder import Builder, BuildReport, output_for
from deedum.content import build_collections, load_data, load_pages
from deedum.errors import ConfigError, DeedumError
from deedum.site import Page, Site

_BUILTIN_GLOBALS = frozenset(
    {
        "site", "page", "url", "absolute", "collections", "data", "now",
        "image_size", "head_extra",
    }
)  # fmt: skip
_RENDER_ARGS = frozenset({"page", "template", "path"})
_PAGE_FIELDS = (
    "date", "updated", "collection", "image", "noindex", "lang", "alternates",
)  # fmt: skip


class App:
    """Hooks of the convention build. Subclass it and name it in ``app``.

    The defaults reproduce the plain build: pages from ``content/``, no extra
    template context, no filters, no globals.
    """

    def __init__(self, site: Site) -> None:
        """Keep the site and load the data folder."""
        self.site = site
        self.data = load_data(site)

    def load_pages(self) -> list[Page]:
        """Every page of the site. Default: the markdown files of ``content/``."""
        return load_pages(self.site)

    def context(self, page: Page) -> dict[str, Any]:
        """Extra template variables for ``page``. Must not contain ``page``."""
        return {}

    def filters(self) -> dict[str, Callable[..., Any]]:
        """Extra Jinja filters by name."""
        return {}

    def globals(self) -> dict[str, Any]:
        """Extra Jinja globals by name. Built-in global names are refused."""
        return {}

    def after_build(self, out: Path) -> None:
        """Called once the output is complete; ``out`` is the output folder."""

    def page(  # noqa: PLR0913 -- mirrors the Page fields an override fills in
        self,
        path: str,
        *,
        title: str,
        template: str = "page.html",
        description: str = "",
        body: str = "",
        source: str = "",
        **meta: Any,
    ) -> Page:
        """A Page for the site-relative URL ``path``, to return from ``load_pages``.

        ``body`` is HTML. Keys naming a Page field (``date``, ``noindex``, ...)
        set that field; the rest become frontmatter-style ``meta``.
        """
        fields = {k: meta.pop(k) for k in _PAGE_FIELDS if k in meta}
        fields.setdefault("lang", self.site.lang)
        return Page(
            url=path,
            output=output_for(path),
            title=title,
            description=description,
            body=Markup(body),  # noqa: S704 -- the override's own HTML, like markdown
            source=source,
            template=template,
            meta=meta,
            **fields,
        )


def _fail(site: Site, why: str) -> ConfigError:
    return ConfigError(
        f"app {site.app!r}: {why}",
        hint="set app = 'module:Class' to a deedum.App subclass in a file "
        "under the site root",
    )


def _module_file(site: Site, module: str) -> Path:
    base = site.root.joinpath(*module.split("."))
    for candidate in (base.with_suffix(".py"), base / "__init__.py"):
        if candidate.is_file():
            return candidate
    raise _fail(site, f"no module file for {module!r} under {site.root}")


def _execute(site: Site, module: str, file: Path) -> Any:
    """Run ``file`` as a fresh module that never stays in ``sys.modules``."""
    name = f"_deedum_app_{module.replace('.', '_')}"
    package = [str(file.parent)] if file.name == "__init__.py" else None
    spec = importlib.util.spec_from_file_location(
        name, file, submodule_search_locations=package
    )
    if spec is None or spec.loader is None:
        raise _fail(site, f"cannot load {str(file)!r}")
    mod = importlib.util.module_from_spec(spec)
    saved_path = list(sys.path)
    sys.path.insert(0, str(site.root))
    sys.modules[name] = mod
    try:
        spec.loader.exec_module(mod)
    except (Exception, SystemExit) as err:
        raise _fail(site, f"importing {str(file)!r} failed: {_describe(err)}") from err
    finally:
        sys.modules.pop(name, None)
        sys.path[:] = saved_path
    return mod


def _describe(err: BaseException) -> str:
    return f"{type(err).__name__}: {err}"


def load_app(site: Site) -> App:
    """The configured ``App`` instance, or a plain ``App`` when ``app`` is unset."""
    if not site.app:
        return App(site)
    module, _, cls_name = site.app.partition(":")
    mod = _execute(site, module, _module_file(site, module))
    cls = getattr(mod, cls_name, None)
    if cls is None:
        raise _fail(site, f"module {module!r} has no class {cls_name!r}")
    if not (isinstance(cls, type) and issubclass(cls, App)):
        raise _fail(site, f"{cls_name!r} is not a subclass of deedum.App")
    try:
        return cls(site)
    except DeedumError:
        raise
    except Exception as err:
        raise _fail(
            site, f"constructing {cls_name!r} failed: {_describe(err)}"
        ) from err


def _label(app: App) -> str:
    return app.site.app or "default"


def _bad(app: App, hook: str, why: str) -> DeedumError:
    return DeedumError(f"app hook {hook!r} ({_label(app)}) returned a bad value: {why}")


def _call(app: App, hook: str, *args: Any) -> Any:
    """Run a hook. An overridden hook's failures are named; a default's are not."""
    method = getattr(app, hook)
    if getattr(type(app), hook) is getattr(App, hook):
        return method(*args)
    try:
        return method(*args)
    except DeedumError as err:
        msg = f"app hook {hook!r} ({_label(app)}) failed: {err}"
        raise type(err)(msg, hint=err.hint) from err
    except Exception as err:
        msg = f"app hook {hook!r} ({_label(app)}) failed: {_describe(err)}"
        raise DeedumError(msg) from err


def _pages(app: App) -> list[Page]:
    pages = _call(app, "load_pages")
    if not isinstance(pages, list) or not all(isinstance(p, Page) for p in pages):
        raise _bad(app, "load_pages", "expected a list of Page")
    return pages


def _mapping(app: App, hook: str, value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise _bad(app, hook, f"expected a dict, got {type(value).__name__}")
    for key in value:
        if not isinstance(key, str):
            raise _bad(app, hook, f"keys must be strings, got {key!r}")
    return value


def _context(app: App, page: Page) -> dict[str, Any]:
    ctx = _mapping(app, "context", _call(app, "context", page))
    if clash := sorted(_RENDER_ARGS & ctx.keys()):
        raise _bad(app, "context", f"must not contain {', '.join(clash)}")
    return ctx


def _env_hooks(app: App) -> tuple[dict[str, Any], dict[str, Any]]:
    """Validated ``filters()`` and ``globals()``."""
    filters = _mapping(app, "filters", _call(app, "filters"))
    for name, fn in filters.items():
        if not callable(fn):
            raise _bad(app, "filters", f"{name!r} is not callable")
    globals_ = _mapping(app, "globals", _call(app, "globals"))
    if clash := sorted(_BUILTIN_GLOBALS & globals_.keys()):
        raise _bad(app, "globals", f"{', '.join(clash)} is a built-in global")
    return filters, globals_


def build(
    site: Site,
    out: Path | str | None = None,
    *,
    force_clear: bool = False,
    now: dt.datetime | None = None,
) -> BuildReport:
    """Build ``site`` with its ``App``: pages, static files, extras, after_build.

    Everything that can fail before the output is touched (app, pages, env hooks)
    runs before the ``Builder`` clears the folder.
    """
    app = load_app(site)
    pages = _pages(app)
    filters, globals_ = _env_hooks(app)
    builder = Builder(
        site,
        out,
        force_clear=force_clear,
        collections=build_collections(pages),
        data=app.data,
        now=now,
    )
    builder.env.filters.update(filters)
    builder.env.globals.update(globals_)
    for page in pages:
        ctx = _context(app, page)
        builder.render(page.template, page.url, page=page, **ctx)
    builder.copy_static()
    report = builder.finish()
    _call(app, "after_build", builder.out)
    return report
