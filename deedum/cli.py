"""The ``deedum`` command: a router over the library (decision 0001)."""

from __future__ import annotations

import os
from collections.abc import Generator
from contextlib import contextmanager
from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console
from typer_agentic import DEFAULT_AGENT_ENV_VARS, agent_errors

from deedum import guide
from deedum.app import build as build_site
from deedum.config import load_site
from deedum.errors import ConfigError, DeedumError
from deedum.foreign import write_extras
from deedum.site import Site

AGENT = any(os.environ.get(v) for v in DEFAULT_AGENT_ENV_VARS)
console = Console(no_color=AGENT, highlight=not AGENT, width=200 if AGENT else None)
err = Console(stderr=True, no_color=AGENT, highlight=not AGENT)

app = typer.Typer(
    no_args_is_help=True,
    add_completion=False,
    context_settings={"help_option_names": ["-h", "--help"]},
    help="Static HTML for small sites: build from folder conventions, add extras "
    "to a folder something else built. Run `deedum guide` first.",
)
main = agent_errors(app)

Config = Annotated[
    Path | None,
    typer.Option("--config", help="Config file; its folder is the site root."),
]
BaseUrl = Annotated[
    str | None,
    typer.Option("--base-url", help="Overrides DEEDUM_BASE_URL and the config."),
]
BasePath = Annotated[
    str | None,
    typer.Option("--base-path", help="Overrides DEEDUM_BASE_PATH and the config."),
]


def _say(text: str) -> None:
    console.print(text, markup=False, highlight=False, soft_wrap=True)


def _complain(text: str) -> None:
    err.print(text, markup=False, highlight=False, soft_wrap=True)


@contextmanager
def _failures() -> Generator[None]:
    """Turn expected failures into ``error:``/``hint:`` lines and exit codes."""
    try:
        yield
    except DeedumError as failure:
        _complain(f"error: {failure}")
        if failure.hint:
            _complain(f"hint: {failure.hint}")
        code = 2 if isinstance(failure, ConfigError) else 1
        raise typer.Exit(code) from None
    except OSError as failure:
        _complain(f"error: {failure}")
        raise typer.Exit(1) from None
    except KeyboardInterrupt:
        raise typer.Exit(130) from None


def _site(config: Path | None, base_url: str | None, base_path: str | None) -> Site:
    for flag, value in (("--base-url", base_url), ("--base-path", base_path)):
        if value == "":
            msg = f"{flag} must not be empty"
            raise ConfigError(msg)
    if config is None:
        return load_site(Path.cwd(), base_url=base_url, base_path=base_path)
    config = config.absolute()
    return load_site(
        config.parent, config=config, base_url=base_url, base_path=base_path
    )


def _listing(label: str, names: list[str]) -> str:
    return f"{label} {len(names)}: {', '.join(names)}" if names else f"{label} 0"


@app.command()
def build(
    out: Annotated[
        Path | None,
        typer.Option("--out", help="Output folder; default is `out` in the config."),
    ] = None,
    base_url: BaseUrl = None,
    base_path: BasePath = None,
    config: Config = None,
    force_clear: Annotated[
        bool,
        typer.Option(
            "--force-clear", help="Clear an output folder that holds tracked files."
        ),
    ] = False,
) -> None:
    """Build the site from folder conventions, using the configured App if any."""
    with _failures():
        site = _site(config, base_url, base_path)
        target = None if out is None else out.absolute()
        report = build_site(site, target, force_clear=force_clear)
        _say(f"pages {report.pages}")
        _say(f"static {report.static}")
        _say(_listing("extras", report.extras))


@app.command()
def extras(
    folder: Annotated[Path, typer.Argument(help="A folder of built HTML.")],
    config: Config = None,
    base_url: BaseUrl = None,
    base_path: BasePath = None,
    overwrite: Annotated[
        bool, typer.Option("--overwrite", help="Replace files that already exist.")
    ] = False,
) -> None:
    """Add sitemap, robots.txt, favicons and .nojekyll to a folder."""
    with _failures():
        site = _site(config, base_url, base_path)
        report = write_extras(site, folder, overwrite=overwrite)
        _say(f"pages {report.pages}")
        _say(_listing("written", report.written))
        _say(_listing("skipped", report.skipped))
        if report.links:
            _say("")
            _say(report.links)


@app.command(name="guide")
def guide_command(
    topic: Annotated[
        guide.Topic | None,
        typer.Argument(help="setup, use or tune; default is picked from this folder."),
    ] = None,
) -> None:
    """Print instructions for an agent about to use deedum. Writes nothing."""
    _say(guide.render(topic, Path.cwd()))
