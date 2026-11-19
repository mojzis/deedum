from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def _plain_terminal(monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep rich/typer output free of terminal styling in every test."""
    monkeypatch.setenv("_TYPER_FORCE_DISABLE_TERMINAL", "1")
    monkeypatch.delenv("DEEDUM_BASE_URL", raising=False)
    monkeypatch.delenv("DEEDUM_BASE_PATH", raising=False)
