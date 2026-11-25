"""Command-line interface for `python -m readpath`."""

import argparse


def build_parser() -> argparse.ArgumentParser:
    """Build the top-level argument parser (no commands yet)."""
    parser = argparse.ArgumentParser(
        prog="readpath",
        description="Build a reading path for a research paper.",
    )
    parser.add_subparsers(dest="command")
    return parser


def main(argv: list[str] | None = None) -> int:
    """Parse arguments and run the chosen command; print help if none is given."""
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command is None:
        parser.print_help()
    return 0
