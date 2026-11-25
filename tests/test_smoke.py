"""Smoke tests: every readpath module imports and the CLI runs."""

import importlib

import pytest

MODULES = [
    "readpath",
    "readpath.__main__",
    "readpath.http",
    "readpath.s2",
    "readpath.arxiv",
    "readpath.store",
    "readpath.queries",
    "readpath.search",
    "readpath.path",
    "readpath.order",
    "readpath.cli",
]


@pytest.mark.parametrize("name", MODULES)
def test_module_imports(name: str) -> None:
    """Each readpath module can be imported."""
    assert importlib.import_module(name) is not None


def test_cli_main_without_command_returns_zero() -> None:
    """Running the CLI with no command prints help and exits 0."""
    from readpath.cli import main

    assert main([]) == 0


def test_cli_search_reports_api_failure(monkeypatch: pytest.MonkeyPatch, capsys) -> None:
    """A search that fails after retries prints a short error and exits 1, no traceback."""
    import requests

    from readpath import cli

    def failing_search(query: str, limit: int = 5) -> list:
        raise requests.HTTPError("429", response=type("R", (), {"status_code": 429})())

    monkeypatch.setattr(cli.s2, "search", failing_search)
    assert cli.main(["search", "anything"]) == 1
    assert "HTTP 429" in capsys.readouterr().err
