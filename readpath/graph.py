"""Graph view data: nodes and edges for the reading-path picture (pure Python, no Streamlit)."""

from collections.abc import Iterable
from typing import Any

MAX_NODES = 40
MAX_AUTHORS = 8
SHORT = 28

TARGET_COLOR = "#1b2a4a"     # dark navy
STEP_COLOR = "#14919b"       # teal
VIA_COLOR = "#9fd8db"        # light teal: chain papers outside the path
AUTHOR_COLOR = "#f28c28"     # orange
HIGHLIGHT = "#ff2e63"        # bright: the chosen paper's citation chains
EDGE_GREY = "#c9cdd2"
BY_COLOR = "#f6c491"

Row = dict[str, Any]


def short(title: str, n: int = SHORT) -> str:
    """Shorten a title to n characters plus "…"."""
    title = (title or "").strip()
    return title if len(title) <= n else title[: n - 1].rstrip() + "…"


def hover(p: Row) -> str:
    """Hover text: full title and year."""
    return f"{p.get('title') or 'Untitled'} ({p.get('year') or 'n.d.'})"


def focus_chains(result: Row, focus_id: str | None) -> list[list[Row]]:
    """Return the citation chains of the chosen step (empty if none is chosen)."""
    step = next((s for s in result["steps"] if s["id"] == focus_id), None)
    return step["chains"] if step else []


def chain_pairs(chains: Iterable[list[Row]]) -> set[tuple[str, str]]:
    """Return the (citing, cited) pairs along the chains."""
    return {(c[i]["id"], c[i + 1]["id"]) for c in chains for i in range(len(c) - 1)}


def paper_nodes(result: Row, focus_id: str | None) -> list[Row]:
    """Return the papers to draw: path steps, the target, and chain papers outside the path."""
    papers = {s["id"]: {**s, "kind": "step", "step": i} for i, s in enumerate(result["steps"], start=1)}
    papers[result["target"]["id"]] = {**result["target"], "kind": "target"}
    for chain in focus_chains(result, focus_id):
        for node in chain:
            papers.setdefault(node["id"], {**node, "kind": "via"})
    return list(papers.values())


def year_levels(papers: Iterable[Row], target_id: str) -> dict[str, int]:
    """Give each paper a column by year (oldest = 1), with the target alone in the last column."""
    papers = list(papers)
    years = sorted({p.get("year") or 0 for p in papers if p["id"] != target_id})
    column = {y: i + 1 for i, y in enumerate(years)}
    levels = {p["id"]: column[p.get("year") or 0] for p in papers if p["id"] != target_id}
    levels[target_id] = len(years) + 1
    return levels


def build_graph(
    result: Row, focus_id: str | None, cites: Iterable[tuple[str, str]], authors: list[Row]
) -> dict[str, list[Row]]:
    """Return {"nodes", "edges"} as dicts ready for streamlit-agraph Node(**n) / Edge(**e)."""
    papers = paper_nodes(result, focus_id)
    target_id = result["target"]["id"]
    levels = year_levels(papers, target_id)
    shown = {p["id"] for p in papers}
    authors = authors[: max(0, MAX_NODES - len(papers))]
    highlighted = chain_pairs(focus_chains(result, focus_id))

    nodes = [_paper_node(p, levels[p["id"]], p["id"] == focus_id) for p in papers]
    nodes += [_author_node(a) for a in authors]
    edges = [_cites_edge(src, dst, (src, dst) in highlighted)
             for src, dst in sorted(set(cites)) if src in shown and dst in shown and src != dst]
    edges += [_by_edge(pid, a["id"]) for a in authors for pid in a["papers"] if pid in shown]
    return {"nodes": nodes, "edges": edges}


def _paper_node(p: Row, level: int, focused: bool) -> Row:
    """Node for a paper: target large navy, steps medium teal, chain papers small light teal."""
    if p["kind"] == "target":
        style = {"label": "Your paper: " + short(p["title"]), "size": 34, "color": TARGET_COLOR}
    elif p["kind"] == "step":
        style = {"label": f"{p['step']}. {short(p['title'])}", "size": 22, "color": STEP_COLOR}
    else:
        style = {"label": short(p["title"]), "size": 13, "color": VIA_COLOR}
    border = {"borderWidth": 4, "color": {"background": style["color"], "border": HIGHLIGHT}} if focused else {}
    return {"id": p["id"], "title": hover(p), "shape": "dot", "level": level,
            "font": {"size": 15, "strokeWidth": 3, "strokeColor": "#ffffff"}, **style, **border}


def _author_node(a: Row) -> Row:
    """Small orange node for an author (level 0: the left-most column)."""
    papers = len(a["papers"])
    return {"id": f"author:{a['id']}", "label": a["name"], "title": f"{a['name']}: {papers} paper"
            f"{'s' if papers != 1 else ''} in this path", "shape": "dot", "size": 10,
            "color": AUTHOR_COLOR, "level": 0, "font": {"size": 13, "color": "#8a4b0f"}}


def _cites_edge(src: str, dst: str, highlighted: bool) -> Row:
    """CITES edge: thick and bright on the chosen chain, otherwise thin and grey."""
    if highlighted:
        return {"source": src, "target": dst, "color": HIGHLIGHT, "width": 5, "title": "cites"}
    return {"source": src, "target": dst, "color": EDGE_GREY, "width": 1, "title": "cites"}


def _by_edge(paper_id: str, author_id: str) -> Row:
    """BY edge from a paper to one of its authors: thin, dashed, no arrow."""
    return {"source": paper_id, "target": f"author:{author_id}", "color": BY_COLOR, "width": 1,
            "dashes": True, "arrows": {"to": {"enabled": False}}, "title": "written by"}
