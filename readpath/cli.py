"""Command-line interface for `python -m readpath`."""

import argparse
import sys

import requests

from readpath import s2


def _describe(exc: requests.RequestException) -> str:
    """Return a short description of a failed request (status code or error type)."""
    response = getattr(exc, "response", None)
    if response is not None:
        return f"HTTP {response.status_code}"
    return type(exc).__name__


def build_parser() -> argparse.ArgumentParser:
    """Build the top-level argument parser."""
    parser = argparse.ArgumentParser(
        prog="readpath",
        description="Build a reading path for a research paper.",
    )
    commands = parser.add_subparsers(dest="command")
    search = commands.add_parser("search", help="search Semantic Scholar for a paper title")
    search.add_argument("title", help="paper title or search words")
    return parser


def cmd_search(title: str) -> int:
    """Print paperId, year, cited_by, arXiv id and title of the top 5 matches."""
    try:
        papers = [s2.simplify(p) for p in s2.search(title, limit=5)]
    except requests.RequestException as exc:
        print(f"Semantic Scholar request failed after retries: {_describe(exc)}", file=sys.stderr)
        print("The shared free rate limit is busy; try again in a minute.", file=sys.stderr)
        return 1
    if not papers:
        print("No matches.")
        return 0
    print(f"{'paperId':40}  {'year':4}  {'cited_by':>9}  {'arxiv':12}  title")
    for p in papers:
        year = str(p["year"] or "-")
        print(f"{p['id']:40}  {year:4}  {p['cited_by']:>9}  {p['arxiv'] or '-':12}  {p['title']}")
    return 0


def main(argv: list[str] | None = None) -> int:
    """Parse arguments and run the chosen command; print help if none is given."""
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command == "search":
        return cmd_search(args.title)
    parser.print_help()
    return 0
