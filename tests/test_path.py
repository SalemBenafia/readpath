"""Tests for readpath.path on a pack whose answers are obvious (see conftest.make_path_pack)."""

from pathlib import Path
from typing import Any

import pytest

from readpath import path


def ids(rows: list[dict]) -> list[str]:
    """Return the ids of rows, in order."""
    return [r["id"] for r in rows]


# ---------- foundations ----------


def test_foundations_depth3_ranks_by_routes_then_cited_by(path_conn: Any) -> None:
    """F has 3 routes; the rest have 1 and follow cited_by (D 30, B 20, A 10, E 5)."""
    rows = path.foundations(path_conn, "T", depth=3, limit=10)
    assert ids(rows) == ["F", "D", "B", "A", "E"]
    assert [r["routes"] for r in rows] == [3, 1, 1, 1, 1]
    assert set(rows[0]) == {"id", "title", "year", "cited_by", "arxiv", "doi", "routes"}


def test_foundations_depth2_does_not_reach_three_hops(path_conn: Any) -> None:
    """E is 3 hops from T, so depth 2 leaves it out."""
    assert ids(path.foundations(path_conn, "T", depth=2, limit=10)) == ["F", "D", "B", "A"]


def test_foundations_limit_and_already_read(path_conn: Any) -> None:
    """limit caps the list and already-read papers are skipped."""
    assert ids(path.foundations(path_conn, "T", limit=2)) == ["F", "D"]
    assert ids(path.foundations(path_conn, "T", limit=2, already_read=["F"])) == ["D", "B"]


def test_foundations_of_leaf_is_empty(path_conn: Any) -> None:
    """A paper that cites nothing in the pack has no foundations."""
    assert path.foundations(path_conn, "E") == []


def test_unsupported_depth_raises(path_conn: Any) -> None:
    """Only depths with a constant (2, 3) are allowed."""
    with pytest.raises(ValueError):
        path.foundations(path_conn, "T", depth=4)
    with pytest.raises(ValueError):
        path.why_chains(path_conn, "T", "F", depth=1)


# ---------- why chains ----------


def test_why_chains_shortest_first(path_conn: Any) -> None:
    """The direct citation comes first, then the two 3-node chains via A and B."""
    chains = path.why_chains(path_conn, "T", "F")
    assert [ids(c) for c in chains][0] == ["T", "F"]
    assert sorted(ids(c) for c in chains[1:]) == [["T", "A", "F"], ["T", "B", "F"]]
    assert chains[0][1] == {"id": "F", "title": "Paper F", "year": 2010}


def test_why_chains_respects_depth(path_conn: Any) -> None:
    """E needs 3 hops: found at depth 3, not at depth 2."""
    assert [ids(c) for c in path.why_chains(path_conn, "T", "E", depth=3)] == [["T", "A", "D", "E"]]
    assert path.why_chains(path_conn, "T", "E", depth=2) == []


# ---------- citation loops (see conftest.make_loop_pack) ----------


@pytest.mark.parametrize("depth", [2, 3])
def test_foundations_ignore_routes_that_repeat_a_paper(loop_conn: Any, depth: int) -> None:
    """Loops (A <-> B, T <-> C) add no routes: every foundation has exactly 1."""
    rows = path.foundations(loop_conn, "T", depth=depth, limit=10)
    assert ids(rows) == ["A", "B", "C"]
    assert [r["routes"] for r in rows] == [1, 1, 1]


@pytest.mark.parametrize("depth", [2, 3])
def test_why_chains_never_repeat_a_paper(loop_conn: Any, depth: int) -> None:
    """Only the simple chain is shown, never T -> A -> B -> A or T -> C -> T -> A."""
    assert [ids(c) for c in path.why_chains(loop_conn, "T", "A", depth=depth)] == [["T", "A"]]


# ---------- why text (pure) ----------


def node(pid: str, title: str, year: int | None) -> dict:
    """Make a chain node."""
    return {"id": pid, "title": title, "year": year}


def test_why_text_direct() -> None:
    """A 2-node chain is a direct citation; routes > 1 are mentioned."""
    chain = [node("T", "Target", 2020), node("F", "Found", 2010)]
    assert path.why_text(chain, 1) == "Your paper cites it directly."
    assert path.why_text(chain, 3) == "Your paper cites it directly. Reached by 3 citation routes."


def test_why_text_multi_hop_with_truncation() -> None:
    """Middle papers are named with year, and long titles are shortened."""
    long_title = "Neural Machine Translation by Jointly Learning to Align and Translate"
    chain = [node("T", "Target", 2017), node("M", long_title, 2014), node("F", "Found", 1997)]
    assert path.why_text(chain, 12) == (
        "Your paper -> Neural Machine Translation by Jointly Le... (2014) -> this paper."
        " Reached by 12 citation routes."
    )
    chain = [node("T", "T", 2020), node("A", "Short", None), node("B", "Other", 2001), node("F", "F", 1990)]
    assert path.why_text(chain, 1) == (
        "Your paper -> Short (n.d.) -> Other (2001) -> this paper. Reached by 1 citation route."
    )


def test_why_text_without_chain() -> None:
    """No chain means no citation link."""
    assert path.why_text([], 0) == "Not linked by citations in this pack."


# ---------- authors and topics ----------


def test_authors_to_follow(path_conn: Any) -> None:
    """Ada wrote both F and D, so she comes first."""
    authors = path.authors_to_follow(path_conn, ["F", "D", "A"])
    assert authors[0] == {"author": "Ada", "papers": 2}
    assert authors[1] == {"author": "Alan", "papers": 1}
    assert path.authors_to_follow(path_conn, []) == []


def test_topics_in_path_sums_primary_and_secondary(path_conn: Any) -> None:
    """cs.CL is primary for F and D (1.0 + 1.0); cs.LG is secondary for D (0.5)."""
    topics = path.topics_in_path(path_conn, ["F", "D", "E"])
    assert topics == [
        {"topic": "cs.CL", "score": 2.0, "papers": 2},
        {"topic": "cs.LG", "score": 0.5, "papers": 1},
    ]
    assert path.topics_in_path(path_conn, []) == []


# ---------- reading path ----------


def test_reading_path_structure(path_conn: Any) -> None:
    """The full result has target, steps with chains and why, authors and topics."""
    result = path.reading_path(path_conn, "T", size=3)
    assert result["target"]["id"] == "T"
    assert ids(result["steps"]) == ["F", "D", "B"]
    first = result["steps"][0]
    assert set(first) == {"id", "title", "year", "cited_by", "arxiv", "doi", "routes", "chains", "why"}
    assert first["why"] == "Your paper cites it directly. Reached by 3 citation routes."
    assert result["steps"][1]["why"] == "Your paper -> Paper A (2015) -> this paper. Reached by 1 citation route."
    assert result["authors"][0] == {"author": "Ada", "papers": 2}
    assert result["topics"][0]["topic"] == "cs.CL"


def test_paper_by_title_is_case_and_space_insensitive(path_conn: Any) -> None:
    """An exact title matches regardless of case and extra spaces; anything else does not."""
    assert path.paper_by_title(path_conn, "  paper   F ")["id"] == "F"
    assert path.paper_by_title(path_conn, "Paper") is None
    assert path.paper_by_title(path_conn, "   ") is None


def test_find_paper_prefers_exact_title(path_conn: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    """An exact title wins without running hybrid search at all."""

    def no_search(*args: object, **kwargs: object) -> list:
        """Fail the test if hybrid search is called."""
        raise AssertionError("hybrid search should not run for an exact title")

    monkeypatch.setattr(path.search, "hybrid_search", no_search)
    target, how = path.find_paper(path_conn, "PAPER d")
    assert (target["id"], how) == ("D", "title")


def test_find_paper_by_id_and_search_fallback(path_conn: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    """A paperId-shaped text is looked up directly; other text falls back to the top search hit."""
    assert path.find_paper(path_conn, "f" * 40) == (None, "paperId")  # valid shape, not in pack
    monkeypatch.setattr(path.search, "hybrid_search", lambda conn, text, k, embedder: [{"id": "B"}])
    target, how = path.find_paper(path_conn, "something about B")
    assert (target["id"], how) == ("B", "search")
    assert path.find_paper(path_conn, "   ") == (None, "none")


def test_find_candidates_exact_title_first(path_conn: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    """The exact-title paper leads, search hits follow without duplicates, k is respected."""
    hits = [{"id": i, "title": f"Paper {i}", "year": 2000, "cited_by": 1} for i in ("A", "D", "B")]
    monkeypatch.setattr(path.search, "hybrid_search", lambda conn, text, k, embedder: hits)
    found = path.find_candidates(path_conn, "paper d", k=3)
    assert [(c["id"], c["match"]) for c in found] == [("D", "title"), ("A", "search"), ("B", "search")]
    assert set(found[0]) == {"id", "title", "year", "cited_by", "match"}
    assert found[0]["cited_by"] == 30
    assert path.find_candidates(path_conn, "  ") == []


def test_steps_carry_link_ids(path_conn: Any) -> None:
    """Steps include arxiv and doi so the app can link them."""
    step = path.reading_path(path_conn, "T", size=1)["steps"][0]
    assert {"arxiv", "doi"} <= set(step)


def test_edges_among(path_conn: Any) -> None:
    """Only citations with both ends in the id set are returned."""
    assert sorted(path.edges_among(path_conn, ["A", "D", "F", "T"])) == [
        ("A", "D"), ("A", "F"), ("T", "A"), ("T", "F")]
    assert path.edges_among(path_conn, []) == []


def test_reading_path_steps_in_reading_order(path_conn: Any) -> None:
    """E before D (D cites E); F before A and B (they cite it); D before A (A cites D)."""
    result = path.reading_path(path_conn, "T", size=5)
    assert ids(result["steps"]) == ["E", "F", "D", "A", "B"]


def test_cli_path_prints_reading_list(
    path_store_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """The path command prints numbered steps, each with its why, and the target last."""
    import re

    from readpath import cli, store

    monkeypatch.setattr(store, "pack_path", lambda name: path_store_path)
    monkeypatch.setattr(path, "PAPER_ID", re.compile(r"^[A-Z]$"))  # fixture ids are single letters
    assert cli.main(["path", "T", "--pack", "paths", "--size", "2", "--read", "F"]) == 0
    out = capsys.readouterr().out
    # F is already read; the top 2 left are D (cited_by 30) and B (20), no edge between them -> by year.
    numbered = [line for line in out.splitlines() if re.match(r"\s*\d+\. ", line)]
    assert numbered == [
        " 1. Paper D (2012)",
        " 2. Paper B (2016)",
        " 3. Paper T (2020)  <- your paper",
    ]
    assert "    Your paper -> Paper A (2015) -> this paper. Reached by 1 citation route." in out
    assert "    Your paper cites it directly." in out


def test_reading_path_unknown_target(path_conn: Any) -> None:
    """A paper that is not in the pack raises ValueError."""
    with pytest.raises(ValueError):
        path.reading_path(path_conn, "missing")
