"""Command-line interface for `python -m readpath`."""

import argparse
import re
import sys
from typing import Any

import requests

from readpath import path, s2, search, store

PAPER_ID = re.compile(r"^[0-9a-f]{40}$")


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
    search_cmd = commands.add_parser("search", help="search Semantic Scholar for a paper title")
    search_cmd.add_argument("title", help="paper title or search words")
    find = commands.add_parser("find", help="hybrid (vector + full-text) search inside a pack")
    find.add_argument("question", help="what you are looking for, in plain words")
    find.add_argument("--pack", required=True, help="pack name, e.g. transformers")
    find.add_argument("-k", type=int, default=5, help="number of results (default 5)")
    path_cmd = commands.add_parser("path", help="print a reading path for a paper in a pack")
    path_cmd.add_argument("paper", help="paper title (found by hybrid search) or Semantic Scholar paperId")
    path_cmd.add_argument("--pack", required=True, help="pack name, e.g. transformers")
    path_cmd.add_argument("--depth", type=int, choices=(2, 3), default=3, help="citation hops (default 3)")
    path_cmd.add_argument("--size", type=int, default=6, help="papers to read first (default 6)")
    path_cmd.add_argument("--read", default="", help="comma-separated paperIds you have already read")
    return parser


def _open_pack(pack: str) -> Any:
    """Open a pack read-only, or print the available packs and return None."""
    path = store.pack_path(pack)
    if not path.exists():
        available = ", ".join(store.list_packs()) or "none"
        print(f"No pack named {pack!r} (available: {available}).", file=sys.stderr)
        return None
    return store.open_store(path, read_only=True)


def resolve_target(conn: Any, text: str) -> tuple[dict | None, str]:
    """Find the target paper by paperId, then exact title, then the top hybrid search hit."""
    text = text.strip()
    if PAPER_ID.match(text):
        return path.paper(conn, text), "paperId"
    exact = path.paper_by_title(conn, text)
    if exact is not None:
        return exact, "title"
    hits = search.hybrid_search(conn, text, k=1)
    return (path.paper(conn, hits[0]["id"]) if hits else None), "search"


def cmd_path(text: str, pack: str, depth: int, size: int, read: str) -> int:
    """Print a numbered reading list with the why sentence under each paper."""
    conn = _open_pack(pack)
    if conn is None:
        return 1
    try:
        target, how = resolve_target(conn, text)
        if target is None:
            print(f"No paper in pack {pack!r} matches {text!r}.", file=sys.stderr)
            return 1
        already_read = [x.strip() for x in read.split(",") if x.strip()]
        result = path.reading_path(conn, target["id"], size=size, depth=depth, already_read=already_read)
    finally:
        conn.close()
    print(f"Target: {target['title']} ({target['year'] or 'n.d.'})  [{target['id']}]")
    if how == "search":
        print("        (no exact title match; this is the top hybrid-search hit."
              " Pass a paperId to choose another paper)")
    steps = result["steps"]
    if not steps:
        print("\nNo earlier papers in this pack lead to it.")
        return 0
    print(f"\nRead these {len(steps)} papers first, in this order:\n")
    for i, s in enumerate(steps, start=1):
        print(f"{i:>2}. {s['title']} ({s['year'] or 'n.d.'})")
        print(f"    {s['why']}")
    print(f"{len(steps) + 1:>2}. {target['title']} ({target['year'] or 'n.d.'})  <- your paper")
    if result["authors"]:
        print("\nAuthors to follow: " + ", ".join(f"{a['author']} ({a['papers']})" for a in result["authors"]))
    if result["topics"]:
        print("Topics: " + ", ".join(t["topic"] for t in result["topics"]))
    return 0


def cmd_find(question: str, pack: str, k: int) -> int:
    """Print hybrid search results with their vector and full-text ranks."""
    conn = _open_pack(pack)
    if conn is None:
        return 1
    embedder = search.default_embedder()
    try:
        hits = search.hybrid_search(conn, question, k=k, embedder=embedder)
    finally:
        conn.close()
    if not embedder.available:
        print("(vector search unavailable: full-text results only)")
    if not hits:
        print("No matches.")
        return 0
    print(f"{'#':>2}  {'rrf':>6}  {'vec':>3}  {'text':>4}  {'year':4}  title")
    for i, h in enumerate(hits, start=1):
        vec = h["vector_rank"] or "-"
        txt = h["text_rank"] or "-"
        print(f"{i:>2}  {h['score']:.4f}  {vec:>3}  {txt:>4}  {h['year'] or '----':4}  {h['title']}")
    return 0


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
    if args.command == "find":
        return cmd_find(args.question, args.pack, args.k)
    if args.command == "path":
        return cmd_path(args.paper, args.pack, args.depth, args.size, args.read)
    parser.print_help()
    return 0
