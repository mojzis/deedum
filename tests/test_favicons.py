from __future__ import annotations

import dataclasses
import io
import json
import sys
from pathlib import Path

import pytest
import resvg_py
from PIL import Image

import deedum.extras.favicons as fav
from deedum import ConfigError, Site
from deedum.extras.favicons import write_favicons

SQUARE = (
    '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64">'
    '<rect width="64" height="64" fill="#cc3333"/>'
    '<circle cx="32" cy="32" r="12" fill="#fff"/></svg>'
)
WIDE = (
    '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 200 100">'
    '<rect width="200" height="100" fill="#cc3333"/></svg>'
)
TALL = (
    '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 300">'
    '<rect width="100" height="300" fill="#cc3333"/></svg>'
)
RED = (204, 51, 51, 255)


def make_site(tmp_path: Path, favicon: str = "icon.svg", **kw) -> Site:
    root = tmp_path / "site"
    root.mkdir(exist_ok=True)
    return Site(title="T", base_url="https://ex.org", favicon=favicon, root=root, **kw)


def svg_site(tmp_path: Path, text: str = SQUARE) -> Site:
    site = make_site(tmp_path)
    (site.root / "icon.svg").write_text(text, encoding="utf-8")
    return site


def png_site(tmp_path: Path, size=(512, 512), fmt="PNG", name="icon.png") -> Site:
    site = make_site(tmp_path, favicon=name)
    Image.new("RGB", size, RED[:3]).save(site.root / name, format=fmt)
    return site


def out_dir(tmp_path: Path) -> Path:
    out = tmp_path / "out"
    out.mkdir()
    return out


def px(path: Path):
    return Image.open(path).convert("RGBA")


def test_svg_source_writes_full_set(tmp_path):
    site, out = svg_site(tmp_path), out_dir(tmp_path)
    written = write_favicons(site, out)
    assert [p.name for p in written] == [
        "favicon.ico",
        "favicon.svg",
        "apple-touch-icon.png",
        "icon-192.png",
        "icon-512.png",
        "site.webmanifest",
    ]
    assert Image.open(out / "favicon.ico").info["sizes"] == {
        (16, 16),
        (32, 32),
        (48, 48),
    }
    sizes = [px(out / n).size for n in ("apple-touch-icon.png", "icon-192.png")]
    assert sizes == [(180, 180), (192, 192)]
    assert (out / "favicon.svg").read_bytes() == (site.root / "icon.svg").read_bytes()


def test_svg_master_pixels(tmp_path):
    site, out = svg_site(tmp_path), out_dir(tmp_path)
    write_favicons(site, out)
    big = px(out / "icon-512.png")
    assert big.size == (512, 512)
    assert [big.getpixel((2, 2)), big.getpixel((256, 256))] == [RED, (255,) * 4]


def test_png_source_has_no_svg(tmp_path):
    site, out = png_site(tmp_path, size=(800, 800)), out_dir(tmp_path)
    names = [p.name for p in write_favicons(site, out)]
    assert "favicon.svg" not in names
    assert not (out / "favicon.svg").exists()
    assert px(out / "icon-512.png").getpixel((10, 10)) == RED
    assert px(out / "apple-touch-icon.png").size == (180, 180)


def test_uppercase_svg_suffix_is_svg(tmp_path):
    site = make_site(tmp_path, favicon="Icon.SVG")
    (site.root / "Icon.SVG").write_text(SQUARE, encoding="utf-8")
    assert fav.output_names(site)[1] == "favicon.svg"
    assert write_favicons(site, out_dir(tmp_path))[1].name == "favicon.svg"


def test_absolute_source_path(tmp_path):
    src = tmp_path / "elsewhere.svg"
    src.write_text(SQUARE, encoding="utf-8")
    site = make_site(tmp_path, favicon=str(src))
    master = fav.load_master(site)
    assert master is not None
    assert master.size == (512, 512)


@pytest.mark.parametrize(("text", "wide"), [(WIDE, True), (TALL, False)])
def test_non_square_svg_is_centred_on_transparent_square(tmp_path, text, wide):
    site, out = svg_site(tmp_path, text), out_dir(tmp_path)
    write_favicons(site, out)
    big = px(out / "icon-512.png")
    assert big.size == (512, 512)
    assert big.getpixel((256, 256))[3] == 255
    transparent = (256, 2) if wide else (2, 256)
    opaque = (2, 256) if wide else (256, 2)
    assert big.getpixel(transparent)[3] == 0
    assert big.getpixel(opaque)[3] == 255


def test_manifest(tmp_path):
    site = dataclasses.replace(svg_site(tmp_path), theme_color="#abc", title="My é")
    out = out_dir(tmp_path)
    write_favicons(site, out)
    text = (out / "site.webmanifest").read_text(encoding="utf-8")
    assert json.loads(text) == {
        "name": "My é",
        "short_name": "My é",
        "icons": [
            {"src": "icon-192.png", "sizes": "192x192", "type": "image/png"},
            {"src": "icon-512.png", "sizes": "512x512", "type": "image/png"},
        ],
        "theme_color": "#abc",
        "background_color": "#abc",
    }
    assert text.endswith("}\n")
    assert '  "icons"' in text


def test_no_favicon_writes_nothing(tmp_path):
    site, out = make_site(tmp_path, favicon=""), out_dir(tmp_path)
    assert fav.load_master(site) is None
    assert write_favicons(site, out) == []
    assert fav.output_names(site) == []
    assert list(out.iterdir()) == []


def test_deterministic(tmp_path):
    site = svg_site(tmp_path)
    a, b = tmp_path / "a", tmp_path / "b"
    a.mkdir()
    b.mkdir()
    write_favicons(site, a)
    write_favicons(site, b)
    for name in fav.output_names(site):
        assert (a / name).read_bytes() == (b / name).read_bytes()


def fail_msgs(site: Site) -> str:
    with pytest.raises(ConfigError) as ei:
        fav.load_master(site)
    msg = str(ei.value)
    assert "favicon" in msg
    assert str(site.root / site.favicon) in msg
    return msg


def test_missing_file(tmp_path):
    assert "no such file" in fail_msgs(make_site(tmp_path, favicon="nope.png"))


def test_directory(tmp_path):
    site = make_site(tmp_path, favicon="dir")
    (site.root / "dir").mkdir()
    assert "regular file" in fail_msgs(site)


def test_too_small(tmp_path):
    assert "256x256" in fail_msgs(png_site(tmp_path, size=(256, 256)))


def test_not_square(tmp_path):
    assert "600x512" in fail_msgs(png_site(tmp_path, size=(600, 512)))


def test_jpeg_renamed_png(tmp_path):
    assert "JPEG" in fail_msgs(png_site(tmp_path, fmt="JPEG"))


def test_not_an_image(tmp_path):
    site = make_site(tmp_path, favicon="x.png")
    (site.root / "x.png").write_text("hello", encoding="utf-8")
    assert "not an image" in fail_msgs(site)


def test_truncated_png(tmp_path):
    site = png_site(tmp_path)
    path = site.root / "icon.png"
    path.write_bytes(path.read_bytes()[:-30])
    assert "cannot be read" in fail_msgs(site)


def test_decompression_bomb(tmp_path, monkeypatch):
    site = png_site(tmp_path)
    monkeypatch.setattr(Image, "MAX_IMAGE_PIXELS", 100)
    assert "cannot be read" in fail_msgs(site)


@pytest.mark.parametrize("text", ["<svg", ""])
def test_malformed_svg(tmp_path, text):
    assert "not readable SVG" in fail_msgs(svg_site(tmp_path, text))


def test_extreme_aspect_ratio_is_refused_without_rendering(tmp_path, monkeypatch):
    def boom(**_):
        msg = "must not render"
        raise AssertionError(msg)

    monkeypatch.setattr(resvg_py, "svg_to_bytes", boom)
    text = (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1 100000">'
        '<rect width="1" height="100000"/></svg>'
    )
    msg = fail_msgs(svg_site(tmp_path, text))
    assert "aspect ratio 100000.0:1" in msg


def test_svg_without_size_is_refused(tmp_path):
    text = '<svg xmlns="http://www.w3.org/2000/svg"><rect width="9" height="9"/></svg>'
    assert "needs a viewBox or width/height" in fail_msgs(svg_site(tmp_path, text))


def test_svg_size_from_width_and_height(tmp_path):
    text = (
        '<svg xmlns="http://www.w3.org/2000/svg" width="200px" height="100">'
        '<rect width="200" height="100" fill="red"/></svg>'
    )
    site, out = svg_site(tmp_path, text), out_dir(tmp_path)
    write_favicons(site, out)
    big = px(out / "icon-512.png")
    assert big.getpixel((256, 2))[3] == 0
    assert big.getpixel((256, 256))[3] == 255


def test_resvg_missing(tmp_path, monkeypatch):
    monkeypatch.setitem(sys.modules, "resvg_py", None)
    assert "resvg-py" in fail_msgs(svg_site(tmp_path))


def test_resvg_returns_garbage(tmp_path, monkeypatch):
    monkeypatch.setattr(resvg_py, "svg_to_bytes", lambda **_: b"not a png")
    assert "resvg cannot render" in fail_msgs(svg_site(tmp_path))


def test_failure_hint(tmp_path):
    with pytest.raises(ConfigError) as ei:
        fav.load_master(make_site(tmp_path, favicon="nope.png"))
    assert "512" in (ei.value.hint or "")


def test_png_source_not_modified(tmp_path):
    site = png_site(tmp_path)
    before = (site.root / "icon.png").read_bytes()
    write_favicons(site, out_dir(tmp_path))
    assert (site.root / "icon.png").read_bytes() == before
    assert Image.open(io.BytesIO(before)).size == (512, 512)
