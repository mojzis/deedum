"""Files every site needs besides its pages: sitemap, robots, 404, icons, feeds."""

from __future__ import annotations

from deedum.extras.favicons import write_favicons
from deedum.extras.feeds import write_feeds
from deedum.extras.llms import write_llms
from deedum.extras.nojekyll import write_nojekyll
from deedum.extras.notfound import render_404
from deedum.extras.robots import write_robots
from deedum.extras.sitemap import write_sitemap

__all__ = [
    "render_404",
    "write_favicons",
    "write_feeds",
    "write_llms",
    "write_nojekyll",
    "write_robots",
    "write_sitemap",
]
