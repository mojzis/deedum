"""Load a Site from deedum.toml or [tool.deedum], with env and flag overrides."""

from __future__ import annotations

import difflib
import os
import re
import tomllib
from collections.abc import Mapping
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from deedum.errors import ConfigError
from deedum.site import (
    Site,
    normalise_base_path,
    normalise_base_url,
    normalise_twitter,
)

DEEDUM_TOML = "deedum.toml"
PYPROJECT = "pyproject.toml"

_STR_KEYS = (
    "title", "base_url", "description", "base_path", "lang", "author", "image",
    "favicon", "twitter", "analytics", "head_extra", "content", "templates",
    "static", "data", "out", "app", "theme_color",
)  # fmt: skip
_BOOL_KEYS = ("relative_links", "llms", "allow_tracked_out")
_LIST_KEYS = ("feeds", "robots_extra_sitemaps")
_KNOWN = (*_STR_KEYS, *_BOOL_KEYS, *_LIST_KEYS)

_TOML_NAMES = {
    str: "string",
    bool: "boolean",
    int: "integer",
    float: "float",
    list: "array",
    dict: "table",
}
_APP = re.compile(r"^[A-Za-z_]\w*(\.[A-Za-z_]\w*)*:[A-Za-z_]\w*$")


def _toml_name(value: object) -> str:
    return _TOML_NAMES.get(type(value), type(value).__name__)


def _read_toml(path: Path) -> dict[str, Any]:
    try:
        return tomllib.loads(path.read_text(encoding="utf-8"))
    except OSError as err:
        msg = f"{path}: cannot read file ({err.strerror or err})"
        raise ConfigError(msg) from err
    except UnicodeDecodeError as err:
        msg = f"{path}: file is not valid UTF-8 ({err})"
        raise ConfigError(msg) from err
    except tomllib.TOMLDecodeError as err:
        msg = f"{path}: malformed TOML: {err}"
        raise ConfigError(msg) from err


def _pyproject_table(data: dict[str, Any], path: Path) -> dict[str, Any] | None:
    """Return ``[tool.deedum]`` or None when absent; raise when not a table."""
    tool = data.get("tool")
    if not isinstance(tool, dict) or "deedum" not in tool:
        return None
    table = tool["deedum"]
    if not isinstance(table, dict):
        msg = f"{path}: [tool.deedum] must be a table, got {_toml_name(table)}"
        raise ConfigError(msg)
    return table


def has_pyproject_table(path: Path) -> bool:
    """Whether ``path`` exists and carries a usable ``[tool.deedum]`` table."""
    if not path.is_file():
        return False
    try:
        return _pyproject_table(_read_toml(path), path) is not None
    except ConfigError:
        return False


_REQ_NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]*")


def pyproject_facts(path: Path) -> tuple[bool, bool]:
    """``(has [tool.deedum], lists deedum in [project].dependencies)`` for ``path``.

    A missing file gives ``(False, False)``; a malformed one raises ConfigError.
    """
    if not path.is_file():
        return False, False
    data = _read_toml(path)
    project = data.get("project")
    deps = project.get("dependencies") if isinstance(project, dict) else None
    names = (
        _REQ_NAME.match(dep.strip())
        for dep in (deps if isinstance(deps, list) else [])
        if isinstance(dep, str)
    )
    listed = any(
        m and re.sub(r"[-_.]+", "-", m.group()).lower() == "deedum" for m in names
    )
    return _pyproject_table(data, path) is not None, listed


def _locate(root: Path, config: Path | None) -> tuple[Path, dict[str, Any]]:
    """Resolve the config file and return its path and raw key table."""
    if config is not None:
        data = _read_toml(config)
        if config.name != PYPROJECT:
            return config, data
        table = _pyproject_table(data, config)
        if table is None:
            msg = f"{config}: no [tool.deedum] table"
            raise ConfigError(msg)
        return config, table
    toml_path, pyproject = root / DEEDUM_TOML, root / PYPROJECT
    if toml_path.is_file():
        if has_pyproject_table(pyproject):
            msg = f"both {toml_path} and [tool.deedum] in {pyproject} exist"
            raise ConfigError(msg, hint=f"keep one: delete {toml_path} or the table")
        return toml_path, _read_toml(toml_path)
    table = (
        _pyproject_table(_read_toml(pyproject), pyproject)
        if pyproject.is_file()
        else None
    )
    if table is None:
        msg = (
            f"no deedum config in {root}: looked for {DEEDUM_TOML} "
            f"and [tool.deedum] in {PYPROJECT}"
        )
        raise ConfigError(msg, hint=f"create {toml_path}")
    return pyproject, table


def _check_table(table: dict[str, Any], path: Path) -> dict[str, Any]:
    """Reject unknown keys and wrong types; return the validated values."""
    values: dict[str, Any] = {}
    for key, value in table.items():
        if key not in _KNOWN:
            close = difflib.get_close_matches(key, _KNOWN, n=1)
            hint = f"did you mean '{close[0]}'?" if close else None
            msg = f"{path}: unknown key {key!r}"
            raise ConfigError(msg, hint=hint)
        where = f"{path}: key {key!r}"
        if key in _STR_KEYS:
            _expect(isinstance(value, str), where, "a string", value)
        elif key in _BOOL_KEYS:
            _expect(isinstance(value, bool), where, "a boolean (bool)", value)
        else:
            _expect(isinstance(value, list), where, "an array of strings", value)
            for i, item in enumerate(value):
                _expect(isinstance(item, str), f"{where} item {i}", "a string", item)
            value = tuple(value)  # noqa: PLW2901 -- tuples keep Site hashable
        values[key] = value
    return values


def _expect(ok: bool, where: str, expected: str, value: object) -> None:
    if not ok:
        msg = f"{where}: expected {expected}, got {_toml_name(value)}"
        raise ConfigError(msg)


def _override(
    key: str,
    flag: str | None,
    environ: Mapping[str, str],
    file_value: str | None,
    path: Path,
) -> tuple[str | None, str]:
    """Pick flag > env > file for ``key``; return the value and its source name."""
    env_name = f"DEEDUM_{key.upper()}"
    if flag is not None:
        return flag, f"--{key.replace('_', '-')}"
    if environ.get(env_name):
        return environ[env_name], env_name
    return file_value, f"{path}: key {key!r}"


def load_site(
    root: Path,
    *,
    config: Path | None = None,
    base_url: str | None = None,
    base_path: str | None = None,
    environ: Mapping[str, str] | None = None,
) -> Site:
    """Load and validate the Site configured in ``root`` (or at ``config``)."""
    env = os.environ if environ is None else environ
    path, table = _locate(root, config)
    values = _check_table(table, path)

    url_value, url_source = _override(
        "base_url", base_url, env, values.get("base_url"), path
    )
    if not url_value:
        msg = f"{path}: missing required key 'base_url'"
        raise ConfigError(msg, hint="set it, or pass --base-url / DEEDUM_BASE_URL")
    values["base_url"] = normalise_base_url(url_value, url_source)

    path_value, _ = _override(
        "base_path", base_path, env, values.get("base_path"), path
    )
    if path_value is not None:
        values["base_path"] = normalise_base_path(path_value)

    if not values.get("title", "").strip():
        msg = f"{path}: key 'title' is required and must not be empty"
        raise ConfigError(msg)
    if "twitter" in values:
        values["twitter"] = normalise_twitter(
            values["twitter"], f"{path}: key 'twitter'"
        )
    _check_sitemaps(values.get("robots_extra_sitemaps", ()), path)
    if values.get("app") and not _APP.match(values["app"]):
        msg = f"{path}: key 'app' must look like 'module:Class', got {values['app']!r}"
        raise ConfigError(msg)
    return Site(**values, root=path.parent)


def _check_sitemaps(urls: tuple[str, ...], path: Path) -> None:
    for i, url in enumerate(urls):
        parts = urlsplit(url)
        if parts.scheme not in ("http", "https") or not parts.netloc:
            msg = (
                f"{path}: key 'robots_extra_sitemaps' item {i} "
                f"must be an absolute http(s) URL, got {url!r}"
            )
            raise ConfigError(msg)
