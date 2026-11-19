"""The 404 page, rendered through the shared environment."""

from __future__ import annotations

from pathlib import Path

import jinja2
from markupsafe import Markup

from deedum.render import render_page
from deedum.site import Page, Site

NAME = "404.html"


def render_404(env: jinja2.Environment, site: Site, out: Path) -> Path:
    """Render ``404.html`` (target template first, built-in otherwise) into ``out``.

    Links on it are root-relative whatever ``relative_links`` says: the host
    serves it at any depth (see ``url()`` in ``deedum.render``).
    """
    page = Page(
        url=NAME,
        output=NAME,
        title="Page not found",
        description="",
        body=Markup(""),
        source="",
        template=NAME,
        noindex=True,
        lang=site.lang,
    )
    path = out / NAME
    path.write_text(render_page(env, page), encoding="utf-8")
    return path
