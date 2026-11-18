"""Static HTML for small sites, with the boring parts done for you."""

from __future__ import annotations

from deedum.config import load_site
from deedum.errors import ConfigError, DeedumError
from deedum.site import Site

__all__ = ["ConfigError", "DeedumError", "Site", "load_site"]
