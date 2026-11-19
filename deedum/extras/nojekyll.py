"""The empty ``.nojekyll`` file that tells GitHub Pages not to run Jekyll."""

from __future__ import annotations

from pathlib import Path

NAME = ".nojekyll"


def write_nojekyll(out: Path) -> Path:
    """Write an empty ``.nojekyll`` into ``out``."""
    path = out / NAME
    path.write_bytes(b"")
    return path
