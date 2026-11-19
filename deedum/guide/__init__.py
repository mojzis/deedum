"""The agent guide: one markdown page per topic, shipped inside the package."""

from __future__ import annotations

from enum import StrEnum
from importlib import resources
from pathlib import Path

from deedum.config import DEEDUM_TOML, PYPROJECT, has_pyproject_table


class Topic(StrEnum):
    """The pages ``deedum guide`` can print."""

    SETUP = "setup"
    USE = "use"
    TUNE = "tune"


def detect(folder: Path) -> tuple[Topic, str]:
    """Pick a topic from the files in ``folder`` and say what was looked at."""
    if (folder / DEEDUM_TOML).is_file():
        return Topic.USE, f"configured via {DEEDUM_TOML}"
    if has_pyproject_table(folder / PYPROJECT):
        return Topic.USE, f"configured via {PYPROJECT} [tool.deedum]"
    return Topic.SETUP, f"no {DEEDUM_TOML} or [tool.deedum] in {PYPROJECT} here"


def render(topic: Topic | None, folder: Path) -> str:
    """The page for ``topic`` (auto-detected when None), under its pick line."""
    if topic is None:
        topic, reason = detect(folder)
    else:
        reason = "topic requested"
    page = (resources.files("deedum.guide") / f"{topic.value}.md").read_text("utf-8")
    return f"# deedum guide: {reason} -> {topic.value}\n\n{page}"
