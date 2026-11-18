"""Static HTML for small sites, with the boring parts done for you."""

from __future__ import annotations

from deedum.config import load_site
from deedum.content import build_collections, load_data, load_pages
from deedum.errors import ConfigError, ContentError, DeedumError
from deedum.site import Page, Site

__all__ = [
    "ConfigError",
    "ContentError",
    "DeedumError",
    "Page",
    "Site",
    "build_collections",
    "load_data",
    "load_pages",
    "load_site",
]
