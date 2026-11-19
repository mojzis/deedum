"""User-facing failures: raise deep down, catch once at the top."""

from __future__ import annotations


class DeedumError(Exception):
    """Base class for expected failures, with an optional hint for the user."""

    def __init__(self, message: str, hint: str | None = None) -> None:
        super().__init__(message)
        self.hint = hint


class ConfigError(DeedumError):
    """The site configuration is missing, malformed or invalid."""


class ContentError(DeedumError):
    """A content file or data file is malformed or collides with another."""


class RenderError(DeedumError):
    """A template is missing, malformed or failed while rendering a page."""
