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
from deedum.check import CheckReport, check_folder
from deedum.config import DEEDUM_TOML, PYPROJECT, has_pyproject_table, load_site
from deedum.errors import ConfigError, DeedumError
from deedum.foreign import write_extras
from deedum.scaffold import init_site, new_entry
from deedum.serve import serve as run_server
from deedum.site import Site, normalise_base_path

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


def _report(report: CheckReport, *, strict: bool) -> None:
    """Print the findings and the summary; exit 1 on errors (and warnings, strict)."""
    for finding in report.findings:
        _say(str(finding))
    _say(report.summary)
    if report.errors or (strict and report.warnings):
        raise typer.Exit(1)


def _configured(config: Path | None) -> bool:
    cwd = Path.cwd()
    return (
        config is not None
        or (cwd / DEEDUM_TOML).is_file()
        or has_pyproject_table(cwd / PYPROJECT)
    )


def _listing(label: str, names: list[str]) -> str:
    return f"{label} {len(names)}: {', '.join(names)}" if names else f"{label} 0"


@app.command()
def build(  # noqa: PLR0913, PLR0917 -- every CLI option is an argument
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
    check_after: Annotated[
        bool,
        typer.Option("--check", help="Lint the output afterwards; errors exit 1."),
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
        if check_after:
            where = site.root / site.out if target is None else target
            _report(check_folder(where, site.base_path), strict=False)


@app.command()
def check(
    folder: Annotated[
        Path | None,
        typer.Argument(help="A folder of built HTML; default is the configured out."),
    ] = None,
    config: Config = None,
    base_url: BaseUrl = None,
    base_path: BasePath = None,
    strict: Annotated[
        bool, typer.Option("--strict", help="Warnings exit 1 too.")
    ] = False,
) -> None:
    """Lint built HTML: broken links, leftover template syntax, head metadata."""
    with _failures():
        if folder is not None and not _configured(config):
            if base_path == "":
                msg = "--base-path must not be empty"
                raise ConfigError(msg)
            found = normalise_base_path(base_path or "/")
            report = check_folder(folder, found)
        else:
            site = _site(config, base_url, base_path)
            report = check_folder(folder or site.root / site.out, site.base_path)
        _report(report, strict=strict)


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
        if report.skipped and not report.written:
            _complain(
                "hint: existing files were kept; pass --overwrite to refresh them"
            )


@app.command()
def init(
    folder: Annotated[
        Path, typer.Argument(help="The site folder; default is this one.")
    ] = Path(),
) -> None:
    """Scaffold a site: config, home page, template override, Pages workflow."""
    with _failures():
        report = init_site(folder)
        _say(_listing("written", report.written))
        _say(_listing("skipped", report.skipped))
        for hint in report.hints:
            _say(hint)


@app.command()
def new(
    collection: Annotated[str, typer.Argument(help="The collection folder name.")],
    title: Annotated[str, typer.Argument(help="The entry title.")],
    slug: Annotated[
        str | None, typer.Option("--slug", help="File name; default is from the title.")
    ] = None,
    config: Config = None,
) -> None:
    """Create content/<collection>/<slug>.md with title and today's date."""
    with _failures():
        site = _site(config, None, None)
        path = new_entry(site, collection, title, slug=slug)
        _say(f"written {os.path.relpath(path)}")


@app.command()
def serve(
    port: Annotated[
        int,
        typer.Option(
            "--port", min=0, max=65535, help="Port on 127.0.0.1; 0 picks one."
        ),
    ] = 8000,
    config: Config = None,
) -> None:
    """Build, serve on localhost and rebuild on every change. Ctrl-C stops it."""
    with _failures():
        run_server(
            lambda base_url: _site(config, base_url, None),
            port=port,
            say=_say,
            complain=_complain,
        )


@app.command(name="guide")
def guide_command(
    topic: Annotated[
        guide.Topic | None,
        typer.Argument(help="setup, use or tune; default is picked from this folder."),
    ] = None,
) -> None:
    """Print instructions for an agent about to use deedum. Writes nothing."""
    _say(guide.render(topic, Path.cwd()))
