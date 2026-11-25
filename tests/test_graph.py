"""Tests for readpath.graph: nodes, levels, highlighting and the node limit (pure Python)."""

from typing import Any

from readpath import graph, path


def n(pid: str, year: int) -> dict:
    """Chain node."""
    return {"id": pid, "title": f"Paper {pid}", "year": year}


def fake_result() -> dict:
    """Target T, steps F (direct + via A) and D (via X, a paper outside the path)."""
    return {
        "target": {"id": "T", "title": "Target paper with a rather long title indeed", "year": 2020,
                   "cited_by": 1, "arxiv": None, "doi": None},
        "steps": [
            {"id": "F", "title": "Paper F", "year": 2010, "routes": 2,
             "chains": [[n("T", 2020), n("F", 2010)], [n("T", 2020), n("A", 2015), n("F", 2010)]]},
            {"id": "D", "title": "Paper D", "year": 2012, "routes": 1,
             "chains": [[n("T", 2020), n("X", 2016), n("D", 2012)]]},
        ],
        "authors": [], "topics": [],
    }


def by_id(items: list[dict]) -> dict[str, dict]:
    """Index nodes by id."""
    return {i["id"]: i for i in items}


def test_nodes_kinds_sizes_and_labels() -> None:
    """Target is large navy, steps medium teal and numbered, authors small orange."""
    authors = [{"id": "a1", "name": "Ada", "papers": ["F", "D"]}]
    data = graph.build_graph(fake_result(), None, [("T", "F")], authors)
    nodes = by_id(data["nodes"])
    assert nodes["T"]["color"] == graph.TARGET_COLOR and nodes["T"]["size"] > nodes["F"]["size"]
    assert nodes["T"]["label"].startswith("Your paper: Target paper with a rather")
    assert nodes["F"]["color"] == graph.STEP_COLOR and nodes["F"]["label"] == "1. Paper F"
    assert nodes["D"]["label"] == "2. Paper D"
    assert nodes["author:a1"]["color"] == graph.AUTHOR_COLOR
    assert nodes["author:a1"]["size"] < nodes["F"]["size"]
    assert nodes["F"]["title"] == "Paper F (2010)"  # hover shows full title and year


def test_focus_adds_chain_papers_and_highlights_its_edges() -> None:
    """Choosing D adds X (outside the path) and highlights T->X->D only."""
    cites = [("T", "F"), ("T", "X"), ("X", "D"), ("T", "A"), ("A", "F")]
    data = graph.build_graph(fake_result(), "D", cites, [])
    nodes = by_id(data["nodes"])
    assert nodes["X"]["color"] == graph.VIA_COLOR
    assert "A" not in nodes  # A is only on F's chain
    edges = {(e["source"], e["target"]): e for e in data["edges"]}
    assert set(edges) == {("T", "F"), ("T", "X"), ("X", "D")}
    assert edges[("T", "X")]["color"] == graph.HIGHLIGHT and edges[("T", "X")]["width"] > 1
    assert edges[("X", "D")]["color"] == graph.HIGHLIGHT
    assert edges[("T", "F")]["color"] == graph.EDGE_GREY and edges[("T", "F")]["width"] == 1
    assert nodes["D"]["color"]["border"] == graph.HIGHLIGHT  # chosen paper is outlined


def test_levels_oldest_left_target_last_authors_first() -> None:
    """Columns follow the year; the target is alone on the right, authors on the left."""
    data = graph.build_graph(fake_result(), "F", [], [{"id": "a", "name": "A", "papers": ["F"]}])
    level = {node["id"]: node["level"] for node in data["nodes"]}
    assert level["author:a"] == 0
    assert level["F"] < level["D"] < level["A"] < level["T"]
    assert level["T"] == max(level.values())


def test_by_edges_only_to_shown_papers_and_without_arrows() -> None:
    """BY edges link shown papers to their authors, dashed and without arrows."""
    authors = [{"id": "a", "name": "A", "papers": ["F", "Z"]}]
    data = graph.build_graph(fake_result(), None, [], authors)
    by = [e for e in data["edges"] if e["target"] == "author:a"]
    assert [(e["source"], e["dashes"]) for e in by] == [("F", True)]
    assert by[0]["arrows"] == {"to": {"enabled": False}}


def test_node_limit() -> None:
    """No more than MAX_NODES nodes even with many authors."""
    authors = [{"id": f"a{i}", "name": f"A{i}", "papers": ["F"]} for i in range(100)]
    data = graph.build_graph(fake_result(), "D", [], authors)
    assert len(data["nodes"]) == graph.MAX_NODES


def test_short_titles() -> None:
    """Long titles are cut with an ellipsis; short ones are kept."""
    assert graph.short("x" * 40) == "x" * 27 + "…"
    assert graph.short("Short") == "Short"


def test_author_links_on_path_pack(path_conn: Any) -> None:
    """Ada wrote F and D, so she comes first with both papers."""
    links = path.author_links(path_conn, ["F", "D", "A"], limit=2)
    assert links[0] == {"id": "ada", "name": "Ada", "papers": ["D", "F"]}
    assert len(links) == 2
    assert path.author_links(path_conn, []) == []
