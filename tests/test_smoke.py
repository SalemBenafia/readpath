"""Smoke tests: every readpath module imports and the CLI runs."""

import importlib

import pytest

MODULES = [
    "readpath",
    "readpath.__main__",
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
