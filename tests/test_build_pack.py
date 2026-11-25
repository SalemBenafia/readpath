"""Tests for build_pack.py ranking, edge filtering and collection (fake data, no network)."""

from collections import Counter
from typing import Any

import pytest

import build_pack as bp


def paper(pid: str, refs: list[str] = (), cited_by: int = 0, **extra: Any) -> dict:
    """Make a minimal simplified paper."""
    return {"id": pid, "title": f"T{pid}", "year": 2000, "cited_by": cited_by,
            "arxiv": None, "doi": None, "authors": [], "references": list(refs), **extra}


def test_count_citers_counts_distinct_citers() -> None:
    """Each citing paper counts once; excluded ids and self-citations are skipped."""
    citing = [paper("a", ["x", "y", "x", "a"]), paper("b", ["x", "s"]), paper("c", ["y", "z"])]
    counts = bp.count_citers(citing, exclude={"s"})
    assert counts == Counter({"x": 2, "y": 2, "z": 1})


def test_top_candidates_orders_by_count_then_id() -> None:
    """Higher counts first, ties by id, at most n."""
    counts = Counter({"b": 2, "a": 2, "c": 5, "d": 1})
    assert bp.top_candidates(counts, 3) == ["c", "a", "b"]
    assert bp.top_candidates(counts, 0) == []
    assert bp.top_candidates(counts, 10) == ["c", "a", "b", "d"]


def test_select_best_breaks_ties_by_cited_by_then_id() -> None:
    """Order is (citer count, cited_by, id) and the budget is respected."""
    counts = Counter({"a": 1, "b": 3, "c": 3, "d": 3})
    papers = [paper("a", cited_by=999), paper("b", cited_by=10), paper("c", cited_by=50),
              paper("d", cited_by=10)]
    assert [p["id"] for p in bp.select_best(papers, counts, 3)] == ["c", "b", "d"]
    assert bp.select_best(papers, counts, 0) == []
    assert len(bp.select_best(papers, counts, 99)) == 4


def test_filter_edges_keeps_only_inside_pack() -> None:
    """Outside refs, self-loops and duplicates are dropped."""
    papers = [paper("a", ["b", "outside", "a", "b"]), paper("b", ["c"]), paper("c", [])]
    assert bp.filter_edges(papers) == [("a", "b"), ("b", "c")]


def test_in_pack_citations() -> None:
    """Counts incoming edges per paper."""
    assert bp.in_pack_citations([("a", "c"), ("b", "c"), ("a", "b")]) == Counter({"c": 2, "b": 1})


def test_attach_arxiv_fills_or_empties() -> None:
    """Papers with metadata get it; others get an empty abstract."""
    meta = {"1": {"abstract": "abs", "primary_category": "cs.CL", "categories": ["cs.CL", "cs.LG"]}}
    out = bp.attach_arxiv([paper("a", arxiv="1"), paper("b", arxiv="2"), paper("c")], meta)
    assert out[0]["abstract"] == "abs" and out[0]["categories"] == ["cs.CL", "cs.LG"]
    assert out[1]["abstract"] == "" and out[1]["primary_category"] is None
    assert out[2]["categories"] == []


def test_summary_stats_on_toy_pack() -> None:
    """Levels, edges, abstract %, author dedupe, categories and top cited."""
    authors = [{"id": "u1", "name": "U"}, {"id": None, "name": "N"}]
    papers = [
        paper("s", level=0, abstract="x", categories=["cs.CL"], authors=authors),
        paper("a", level=1, abstract="x", categories=["cs.CL", "cs.LG"], authors=authors[:1]),
        paper("b", level=1, abstract="", categories=[]),
        paper("c", level=2, abstract="", categories=[]),
        paper("d", level=2, abstract="", categories=["stat.ML"]),
    ]
    edges = [("s", "a"), ("s", "b"), ("a", "b"), ("b", "c"), ("a", "c"), ("s", "c")]
    stats = bp.summary_stats(papers, edges)
    assert stats["levels"] == {0: 1, 1: 2, 2: 2}
    assert stats["edges"] == 6
    assert (stats["with_abstract"], stats["abstract_pct"]) == (2, 40.0)
    assert stats["authors"] == 2
    assert stats["categories"] == 3
    assert [t for _, _, t in stats["top_cited"]] == ["Tc", "Tb", "Ta"]


def test_paper_text() -> None:
    """Embedding text is "title. abstract", or the title alone without an abstract."""
    assert bp.paper_text({"title": "T", "abstract": " A "}) == "T. A"
    assert bp.paper_text({"title": "T", "abstract": ""}) == "T"


def test_collect_end_to_end(monkeypatch: pytest.MonkeyPatch) -> None:
    """Seeds → level 1 → best level 2 within budget, in-pack edges, arXiv attached."""
    raw = {
        "S": {"refs": ["A", "B"]},
        "A": {"refs": ["X", "Y", "B"], "arxiv": "1"},
        "B": {"refs": ["X", "Z"]},
        "X": {"refs": ["Y"], "cites": 5},
        "Y": {"refs": [], "cites": 100},
        "Z": {"refs": [], "cites": 1},
    }

    def to_raw(pid: str) -> dict:
        """Return a raw Semantic Scholar paper for a fake id."""
        r = raw[pid]
        return {"paperId": pid, "title": f"T{pid}", "year": 2000, "citationCount": r.get("cites", 0),
                "externalIds": {"ArXiv": r["arxiv"]} if "arxiv" in r else None,
                "authors": [], "references": [{"paperId": x} for x in r["refs"]]}

    fetched: list[list[str]] = []

    def get_papers(ids: list[str]) -> list[dict]:
        """Record the requested ids and return their raw papers."""
        fetched.append(list(ids))
        return [to_raw(i) for i in ids]

    monkeypatch.setattr(bp.s2, "match_title", lambda t: to_raw("S"))
    monkeypatch.setattr(bp.s2, "get_papers", get_papers)
    monkeypatch.setattr(bp.arxiv, "get_metadata",
                        lambda ids: {"1": {"abstract": "a", "primary_category": "cs.CL",
                                           "categories": ["cs.CL"]}})

    pack = bp.collect("toy", ["seed title"], max_papers=5)
    levels = {p["id"]: p["level"] for p in pack["papers"]}
    # X is cited by both A and B (count 2); Y and Z once; budget 5-1-2=2 → X, then Y (cited_by 100).
    assert levels == {"S": 0, "A": 1, "B": 1, "X": 2, "Y": 2}
    assert fetched[1] == ["X", "Y", "Z"]
    assert sorted(map(tuple, pack["edges"])) == [
        ("A", "B"), ("A", "X"), ("A", "Y"), ("B", "X"), ("S", "A"), ("S", "B"), ("X", "Y")]
    assert pack["seeds"] == ["S"]
    assert all("references" not in p for p in pack["papers"])
    assert next(p for p in pack["papers"] if p["id"] == "A")["abstract"] == "a"
