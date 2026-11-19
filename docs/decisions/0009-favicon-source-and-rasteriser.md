# 0009 Favicon source and rasteriser

Date: 2026-11-19
Status: accepted

## Context

One configured image has to become `favicon.ico`, `apple-touch-icon.png`, two
manifest icons and `site.webmanifest`. Pillow reads PNG but cannot render SVG, and
the SVG source is the one people actually have.

## Decision

- **resvg-py** rasterises SVG. It ships wheels for Linux, macOS and Windows, needs no
  system library, does no network access, and raises `ValueError` on bad input.
- `favicon` resolves against `site.root` (an absolute path is accepted) and must be a
  regular file. A `.svg` suffix, case-insensitive (the same test the head uses),
  selects SVG. Anything else must open in Pillow as a **PNG**, be square and be at
  least 512 px. A JPEG renamed `.png` fails.
- The source is rasterised once to a 512x512 RGBA master. Every PNG size and the ICO
  (16, 32, 48) are LANCZOS downsamples of it.
- A non-square SVG keeps its aspect ratio: it is rendered at 512 px on the longer side
  and centred on a transparent square. It is not stretched.
- Every failure raises `ConfigError` naming `favicon`, the resolved path and, where
  relevant, the size. `finish()` validates the source before it claims or writes
  anything.
- `favicon.svg` is a byte copy of the source, written for SVG sources only.
- A static file at any favicon output path is a collision (0006). The error hints to
  keep the source image outside the static folder.
- `theme_color` must be `#rgb` or `#rrggbb`; `Site` rejects anything else.

## Consequences

- One new runtime dependency, `resvg-py`. Text in an SVG renders with whatever fonts
  the build machine has, so convert text to paths for a stable icon.
- A favicon source inside the static folder is a build error. Keep it next to
  `deedum.toml` instead.
- An SVG with an extreme aspect ratio renders a very large image for the probe pass;
  we do not guard against that.
