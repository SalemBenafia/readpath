"""Tests for readpath.order: topological reading order with a year tie-break."""

from readpath.order import order_papers


def p(pid: str, year: int | None) -> dict:
    """Make a minimal paper."""
    return {"id": pid, "year": year}


def ids(papers: list[dict]) -> list[str]:
    """Return ids in order."""
    return [x["id"] for x in papers]


def test_simple_chain_reads_cited_first() -> None:
    """a CITES b CITES c, so c, then b, then a, even when years disagree."""
    papers = [p("a", 2000), p("b", 2010), p("c", 2020)]
    assert ids(order_papers(papers, [("a", "b"), ("b", "c")])) == ["c", "b", "a"]


def test_tie_broken_by_year() -> None:
    """Without citations between them, older papers come first."""
    papers = [p("new", 2018), p("old", 1997), p("mid", 2014)]
    assert ids(order_papers(papers, [])) == ["old", "mid", "new"]


def test_tie_break_inside_topological_order() -> None:
    """x and y both cite z; z comes first, then x and y by year."""
    papers = [p("x", 2016), p("y", 2012), p("z", 2015)]
    assert ids(order_papers(papers, [("x", "z"), ("y", "z")])) == ["z", "y", "x"]


def test_cycle_falls_back_to_year() -> None:
    """a and b cite each other: no topological order exists, so sort by year."""
    papers = [p("a", 2015), p("b", 2010), p("c", 2012)]
    assert ids(order_papers(papers, [("a", "b"), ("b", "a")])) == ["b", "c", "a"]


def test_target_is_always_last() -> None:
    """The target goes last even if it is the oldest paper or is cited by others."""
    papers = [p("t", 1990), p("a", 2000), p("b", 2010)]
    assert ids(order_papers(papers, [("a", "t")], target_id="t")) == ["a", "b", "t"]
    assert ids(order_papers(papers, [("a", "b"), ("b", "a")], target_id="t")) == ["a", "b", "t"]


def test_unknown_year_and_outside_edges() -> None:
    """Papers without a year sort last; edges to unknown ids and self-loops are ignored."""
    papers = [p("a", None), p("b", 2001)]
    assert ids(order_papers(papers, [("a", "zzz"), ("b", "b")])) == ["b", "a"]
    assert order_papers([], []) == []
