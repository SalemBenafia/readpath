"""Reading order: topological sort with a year tie-break."""

from collections.abc import Iterable
from typing import Any

import networkx as nx

UNKNOWN_YEAR = 10**6  # papers without a year sort after dated ones

Paper = dict[str, Any]


def _year_key(paper: Paper) -> tuple[int, str]:
    """Sort key: year (older first, unknown last), then id for a stable order."""
    year = paper.get("year")
    return (year if year is not None else UNKNOWN_YEAR, paper["id"])


def order_papers(
    papers: list[Paper], edges: Iterable[tuple[str, str]], target_id: str | None = None
) -> list[Paper]:
    """Order papers so every cited paper comes before the papers citing it; target last.

    edges are (a, b) pairs meaning "a CITES b", so b must be read before a. Ties are
    broken by year (older first). If the citations form a cycle, fall back to year order.
    """
    by_id = {p["id"]: p for p in papers}
    rest = [p for p in papers if p["id"] != target_id]
    graph = nx.DiGraph()
    graph.add_nodes_from(p["id"] for p in rest)
    graph.add_edges_from(
        (b, a) for a, b in edges if a in graph and b in graph and a != b
    )
    try:
        ordered_ids = list(
            nx.lexicographical_topological_sort(graph, key=lambda pid: _year_key(by_id[pid]))
        )
        ordered = [by_id[pid] for pid in ordered_ids]
    except nx.NetworkXUnfeasible:  # citation cycle
        ordered = sorted(rest, key=_year_key)
    if target_id is not None and target_id in by_id:
        ordered.append(by_id[target_id])
    return ordered
