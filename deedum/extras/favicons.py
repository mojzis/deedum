"""Favicon set and web manifest from one SVG or PNG source (R15, decision 0009)."""

from __future__ import annotations

import io
import json
import re
import shutil
import xml.etree.ElementTree as ET
from pathlib import Path

from PIL import Image

from deedum.errors import ConfigError
from deedum.site import Site

MASTER = 512
ICO_SIZES = (16, 32, 48)
ICO = "favicon.ico"
SVG = "favicon.svg"
APPLE = "apple-touch-icon.png"
MANIFEST = "site.webmanifest"
_PNG_SIZES = {APPLE: 180, "icon-192.png": 192, "icon-512.png": 512}
MAX_RATIO = 16


def output_names(site: Site) -> list[str]:
    """Output paths the favicon set writes; empty when no favicon is configured."""
    if not site.favicon:
        return []
    names = [ICO, APPLE, "icon-192.png", "icon-512.png", MANIFEST]
    if _is_svg(site.favicon):
        names.insert(1, SVG)
    return names


def _is_svg(name: str | Path) -> bool:
    return str(name).lower().endswith(".svg")


def _fail(path: Path, why: str) -> ConfigError:
    return ConfigError(
        f"favicon {str(path)!r}: {why}",
        hint="use a square PNG of at least 512 px, or an SVG",
    )


def source_path(site: Site) -> Path:
    """The configured favicon, resolved against the site root."""
    return Path(site.root / site.favicon)


def _number(text: str | None) -> float | None:
    """Leading number of an SVG length such as ``200`` or ``64px``; else None."""
    match = re.match(r"\s*([0-9]*\.?[0-9]+(?:[eE][-+]?[0-9]+)?)", text or "")
    return float(match.group(1)) if match else None


def _svg_size(path: Path) -> tuple[float, float]:
    """Width and height of the SVG root from ``viewBox``, else ``width``/``height``."""
    try:
        _, root = next(ET.iterparse(path, events=("start",)))  # noqa: S314 -- trusted
    except (StopIteration, ET.ParseError, OSError) as err:
        raise _fail(path, f"is not readable SVG ({err})") from err
    box = (root.get("viewBox") or "").replace(",", " ").split()
    sizes = [_number(box[2]), _number(box[3])] if len(box) == 4 else []  # noqa: PLR2004
    if len(sizes) != 2 or not all(sizes):  # noqa: PLR2004
        sizes = [_number(root.get("width")), _number(root.get("height"))]
    if not (sizes[0] and sizes[1]):
        raise _fail(path, "needs a viewBox or width/height")
    return sizes[0], sizes[1]


def _rasterise_svg(path: Path) -> Image.Image:
    """Render at 512 px on the longer side, centred on a transparent square."""

    try:
        import resvg_py  # noqa: PLC0415 -- lazy: a missing wheel is a clear error
    except ImportError as err:
        raise _fail(path, "SVG sources need the resvg-py package") from err

    width, height = _svg_size(path)
    ratio = max(width, height) / min(width, height)
    if ratio > MAX_RATIO:
        raise _fail(path, f"aspect ratio {ratio:.1f}:1 is above {MAX_RATIO}:1")
    wide = width >= height
    try:
        png = resvg_py.svg_to_bytes(
            svg_path=str(path),
            width=MASTER if wide else None,
            height=None if wide else MASTER,
        )
        image = Image.open(io.BytesIO(bytes(png))).convert("RGBA")
    except (ValueError, OSError, Image.DecompressionBombError) as err:
        raise _fail(path, f"resvg cannot render this SVG ({err})") from err
    master = Image.new("RGBA", (MASTER, MASTER), (0, 0, 0, 0))
    master.paste(image, ((MASTER - image.width) // 2, (MASTER - image.height) // 2))
    return master


def _load_png(path: Path) -> Image.Image:
    try:
        with Image.open(path) as image:
            if image.format != "PNG":
                raise _fail(path, f"must be a PNG or SVG, found {image.format}")
            if image.width != image.height or image.width < MASTER:
                size = f"{image.width}x{image.height}"
                raise _fail(path, f"must be square and at least {MASTER} px, is {size}")
            return image.convert("RGBA").resize(
                (MASTER, MASTER), Image.Resampling.LANCZOS
            )
    except Image.UnidentifiedImageError as err:
        raise _fail(path, "must be a PNG or SVG, not an image Pillow can read") from err
    except (OSError, Image.DecompressionBombError) as err:
        raise _fail(path, f"cannot be read as an image ({err})") from err


def load_master(site: Site) -> Image.Image | None:
    """Validate the favicon source and return its 512 px master (None if unset).

    Raises ``ConfigError`` naming ``favicon`` and the path. Writes nothing.
    """
    if not site.favicon:
        return None
    path = source_path(site)
    if not path.is_file():
        raise _fail(path, "no such file (or it is not a regular file)")
    return _rasterise_svg(path) if _is_svg(path) else _load_png(path)


def _png_bytes(image: Image.Image) -> bytes:
    buf = io.BytesIO()
    image.save(buf, format="PNG", optimize=False)
    return buf.getvalue()


def write_favicons(
    site: Site, out: Path, master: Image.Image | None = None
) -> list[Path]:
    """Write the favicon set and manifest into ``out``; return the paths."""
    master = master or load_master(site)
    if master is None:
        return []
    written = []
    master.save(out / ICO, format="ICO", sizes=[(s, s) for s in ICO_SIZES])
    written.append(out / ICO)
    if _is_svg(site.favicon):
        shutil.copyfile(source_path(site), out / SVG)
        written.append(out / SVG)
    for name, size in _PNG_SIZES.items():
        small = master.resize((size, size), Image.Resampling.LANCZOS)
        (out / name).write_bytes(_png_bytes(small))
        written.append(out / name)
    manifest = {
        "name": site.title,
        "short_name": site.title,
        "icons": [
            {"src": f"icon-{n}.png", "sizes": f"{n}x{n}", "type": "image/png"}
            for n in (192, 512)
        ],
        "theme_color": site.theme_color,
        "background_color": site.theme_color,
    }
    (out / MANIFEST).write_text(
        json.dumps(manifest, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    written.append(out / MANIFEST)
    return written
