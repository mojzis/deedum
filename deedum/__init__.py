"""Static HTML for small sites, with the boring parts done for you."""

from __future__ import annotations

from deedum.builder import Builder, BuildReport
from deedum.config import load_site
from deedum.content import build_collections, load_data, load_pages
from deedum.errors import ConfigError, ContentError, DeedumError, RenderError
from deedum.render import head_tags, make_env, render_page
from deedum.site import Page, Site

__all__ = [
    "BuildReport",
    "Builder",
    "ConfigError",
    "ContentError",
    "DeedumError",
    "Page",
    "RenderError",
    "Site",
    "build_collections",
    "head_tags",
    "load_data",
    "load_pages",
    "load_site",
    "make_env",
    "render_page",
]
