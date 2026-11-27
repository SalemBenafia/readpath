"""Foundations, citation chains, authors and topics for a target paper."""

import re
from collections.abc import Iterable
from typing import Any

from readpath import order, queries, search

MAX_TITLE = 40
PAPER_ID = re.compile(r"^[0-9a-f]{40}$")  # Semantic Scholar paperId

Row = dict[str, Any]


def _pick(table: dict[int, str], depth: int) -> str:
    """Return the statement for a supported depth (2 or 3)."""
    if depth not in table:
        raise ValueError(f"depth must be one of {sorted(table)}, got {depth}")
    return table[depth]


def foundations(
    conn: Any, target_id: str, depth: int = 3, limit: int = 6, already_read: Iterable[str] = ()
) -> list[Row]:
    """Return earlier papers reachable from the target, ranked by number of citation routes."""
    statement = _pick(queries.FOUNDATIONS, depth)
    params = {
        "target": target_id,
        "already_read": list(already_read),
        "limit": limit,
        "loops": _loop_walks(conn, target_id, depth),
    }
    return [dict(r) for r in conn.execute(statement, params)]


def _loop_walks(conn: Any, target_id: str, depth: int) -> list[str]:
    """Return one foundation id per walk from the target that visits a paper twice."""
    statement = queries.LOOP_WALKS[depth]
    if statement is None:
        return []
    return [r["id"] for r in conn.execute(statement, {"target": target_id})]


def why_chains(conn: Any, target_id: str, foundation_id: str, depth: int = 3) -> list[list[Row]]:
    """Return up to 3 citation chains from the target to a foundation, shortest first."""
    statement = _pick(queries.WHY_CHAINS, depth)
    rows = conn.execute(statement, {"target": target_id, "foundation": foundation_id})
    return [[dict(n) for n in r["chain"]] for r in rows]


def authors_to_follow(conn: Any, ids: Iterable[str]) -> list[Row]:
    """Return the authors who wrote the most of the given papers."""
    ids = list(ids)
    return [dict(r) for r in conn.execute(queries.AUTHORS_TO_FOLLOW, {"ids": ids})] if ids else []


def author_links(conn: Any, ids: Iterable[str], limit: int = 8) -> list[Row]:
    """Return the top authors of the given papers as {id, name, papers: [paper ids]}."""
    ids = list(ids)
    if not ids:
        return []
    rows = conn.execute(queries.AUTHORS_OF_PAPERS, {"ids": ids, "limit": limit})
    return [{"id": r["id"], "name": r["name"], "papers": sorted(r["papers"])} for r in rows]


def topics_in_path(conn: Any, ids: Iterable[str]) -> list[Row]:
    """Return the arXiv categories of the given papers, with summed scores."""
    ids = list(ids)
    return [dict(r) for r in conn.execute(queries.TOPICS_IN_PATH, {"ids": ids})] if ids else []


def _short(title: str) -> str:
    """Shorten a title to MAX_TITLE characters plus "..."."""
    title = (title or "").strip()
    return title if len(title) <= MAX_TITLE else title[:MAX_TITLE].rstrip() + "..."


def why_text(chain: list[Row], routes: int) -> str:
    """Explain in one sentence, from data only, how the target reaches a foundation."""
    if len(chain) < 2:
        return "Not linked by citations in this pack."
    if len(chain) == 2:
        sentence = "Your paper cites it directly."
    else:
        middle = [f"{_short(n['title'])} ({n['year'] or 'n.d.'})" for n in chain[1:-1]]
        sentence = "Your paper -> " + " -> ".join(middle) + " -> this paper."
    if routes > 1:
        sentence += f" Reached by {routes} citation routes."
    elif len(chain) > 2:
        sentence += " Reached by 1 citation route."
    return sentence


def edges_among(conn: Any, ids: Iterable[str]) -> list[tuple[str, str]]:
    """Return (src, dst) CITES edges whose two ends are both in ids."""
    ids = list(ids)
    if not ids:
        return []
    return [(r["src"], r["dst"]) for r in conn.execute(queries.EDGES_AMONG, {"ids": ids})]


def paper(conn: Any, paper_id: str) -> Row | None:
    """Return basic fields of one paper, or None if it is not in the pack."""
    rows = list(conn.execute(queries.PAPER_BY_ID, {"id": paper_id}))
    return dict(rows[0]) if rows else None


def paper_by_title(conn: Any, title: str) -> Row | None:
    """Return the paper whose title equals title (case-insensitive), or None."""
    wanted = " ".join(title.split()).lower()
    if not wanted:
        return None
    rows = list(conn.execute(queries.PAPER_BY_TITLE, {"title": wanted}))
    return dict(rows[0]) if rows else None


def find_paper(conn: Any, text: str, embedder: Any = None) -> tuple[Row | None, str]:
    """Find a target by paperId, then exact title, then top hybrid-search hit; return (paper, how)."""
    text = text.strip()
    if not text:
        return None, "none"
    if PAPER_ID.match(text):
        return paper(conn, text), "paperId"
    exact = paper_by_title(conn, text)
    if exact is not None:
        return exact, "title"
    hits = search.hybrid_search(conn, text, k=1, embedder=embedder)
    return (paper(conn, hits[0]["id"]) if hits else None), "search"


def suggested_papers(conn: Any, limit: int = 6, min_cites: int = 15) -> list[Row]:
    """Return "start here" papers: the pack's seeds, then famous papers with a rich reading path."""
    rows = conn.execute(queries.SUGGESTED_PAPERS, {"limit": limit, "min_cites": min_cites})
    return [dict(r) for r in rows]


def cites_in_pack(conn: Any, ids: Iterable[str]) -> dict[str, int]:
    """Return how many pack papers each paper cites (0 means no reading path in this pack)."""
    ids = list(ids)
    if not ids:
        return {}
    return {r["id"]: r["cites"] for r in conn.execute(queries.CITES_IN_PACK, {"ids": ids})}


def find_candidates(conn: Any, text: str, k: int = 5, embedder: Any = None) -> list[Row]:
    """Return up to k candidates: paperId or exact title first, then search hits that have a path first."""
    text = text.strip()
    if not text:
        return []
    first = paper(conn, text) if PAPER_ID.match(text) else paper_by_title(conn, text)
    found: list[Row] = []
    if first is not None:
        found.append({**_candidate(first), "match": "paperId" if PAPER_ID.match(text) else "title"})
    hits = [h for h in search.hybrid_search(conn, text, k=k, embedder=embedder)
            if all(h["id"] != f["id"] for f in found)]
    found += [{**_candidate(h), "match": "search"} for h in hits]
    cites = cites_in_pack(conn, [f["id"] for f in found])
    found = [{**f, "cites": cites.get(f["id"], 0)} for f in found]
    exact, rest = found[: 1 if first else 0], found[1 if first else 0 :]
    rest.sort(key=lambda f: f["cites"] == 0)  # stable: papers with a reading path first
    return (exact + rest)[:k]


def _candidate(row: Row) -> Row:
    """Keep the fields a candidate list shows: id, title, year, cited_by."""
    return {key: row.get(key) for key in ("id", "title", "year", "cited_by")}


def reading_path(
    conn: Any, target_id: str, size: int = 6, depth: int = 3, already_read: Iterable[str] = ()
) -> dict[str, Any]:
    """Build the reading path for a target: steps in reading order with their why, authors and topics."""
    target = paper(conn, target_id)
    if target is None:
        raise ValueError(f"paper {target_id} is not in this pack")
    steps = []
    for f in foundations(conn, target_id, depth=depth, limit=size, already_read=already_read):
        chains = why_chains(conn, target_id, f["id"], depth=depth)
        why = why_text(chains[0] if chains else [], f["routes"])
        steps.append({**f, "chains": chains, "why": why})
    ids = [s["id"] for s in steps]
    steps = order.order_papers(steps, edges_among(conn, ids))
    return {
        "target": target,
        "steps": steps,
        "authors": authors_to_follow(conn, ids),
        "topics": topics_in_path(conn, ids),
    }
