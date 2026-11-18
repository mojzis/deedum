"""robots.txt: allow everything, point at the sitemap(s)."""

from __future__ import annotations

from pathlib import Path

from deedum.site import Site

NAME = "robots.txt"


def write_robots(site: Site, out: Path) -> Path:
    """Write ``robots.txt`` into ``out`` (LF endings, trailing newline)."""
    sitemaps = [site.absolute("sitemap.xml"), *site.robots_extra_sitemaps]
    lines = ["User-agent: *", "Allow: /", "", *(f"Sitemap: {s}" for s in sitemaps)]
    path = out / NAME
    path.write_bytes(("\n".join(lines) + "\n").encode("utf-8"))
    return path
