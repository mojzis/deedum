"""Files every site needs besides its pages: sitemap, robots, .nojekyll, 404."""

from __future__ import annotations

from deedum.extras.nojekyll import write_nojekyll
from deedum.extras.notfound import render_404
from deedum.extras.robots import write_robots
from deedum.extras.sitemap import write_sitemap

__all__ = ["render_404", "write_nojekyll", "write_robots", "write_sitemap"]
