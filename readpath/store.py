"""Open Relate stores, create the schema and write topic packs."""

from collections.abc import Iterable, Iterator
from pathlib import Path
from typing import Any

import relate

from readpath import queries

DIMENSIONS = 384
BATCH_SIZE = 200
PACKS_DIR = Path(__file__).resolve().parent.parent / "data" / "packs"

Row = dict[str, Any]


def pack_path(name: str, packs_dir: Path = PACKS_DIR) -> Path:
    """Return the path of the committed pack <name>.rl."""
    return packs_dir / f"{name}.rl"


def list_packs(packs_dir: Path = PACKS_DIR) -> list[str]:
    """Return the names of available packs (temporary builds excluded)."""
    return sorted(p.stem for p in packs_dir.glob("*.rl") if not p.name.endswith(".tmp.rl"))


def open_store(path: str | Path, read_only: bool = False) -> Any:
    """Open a Relate store (a read-only open never creates a missing store)."""
    return relate.connect(str(path), read_only=read_only)


def create_schema(conn: Any) -> None:
    """Create constraints and indexes; safe to run more than once."""
    for statement in queries.SCHEMA_STATEMENTS:
        conn.execute(statement)


def batches(rows: list[Row], size: int = BATCH_SIZE) -> Iterator[list[Row]]:
    """Yield consecutive slices of at most size rows."""
    for start in range(0, len(rows), size):
        yield rows[start : start + size]


def paper_rows(papers: Iterable[Row], embeddings: dict[str, list[float]]) -> list[Row]:
    """Build MERGE_PAPERS rows; every paper needs a 384-number embedding."""
    rows = []
    for p in papers:
        emb = embeddings.get(p["id"])
        if emb is None or len(emb) != DIMENSIONS:
            raise ValueError(f"paper {p['id']} needs a {DIMENSIONS}-dimension embedding")
        rows.append(
            {
                "id": p["id"],
                "title": p.get("title") or "",
                "year": p.get("year"),
                "abstract": p.get("abstract") or "",
                "citedBy": p.get("cited_by") or 0,
                "arxiv": p.get("arxiv"),
                "doi": p.get("doi"),
                "emb": [float(x) for x in emb],
            }
        )
    return rows


def author_rows(papers: Iterable[Row]) -> list[Row]:
    """Build MERGE_AUTHORS rows, skipping authors without a Semantic Scholar id."""
    return [
        {"paper": p["id"], "id": a["id"], "name": a.get("name") or ""}
        for p in papers
        for a in p.get("authors", [])
        if a.get("id")
    ]


def topic_rows(papers: Iterable[Row]) -> list[Row]:
    """Build MERGE_TOPICS rows, one per arXiv category, flagging the primary one."""
    return [
        {"paper": p["id"], "topic": cat, "primary": cat == p.get("primary_category")}
        for p in papers
        for cat in dict.fromkeys(p.get("categories", []))
    ]


def cites_rows(edges: Iterable[Iterable[str]]) -> list[Row]:
    """Build MERGE_CITES rows from [src, dst] pairs."""
    return [{"src": src, "dst": dst} for src, dst in edges]


def _run_batched(conn: Any, statement: str, rows: list[Row]) -> None:
    """Run an UNWIND statement over rows in batches."""
    for chunk in batches(rows):
        conn.execute(statement, {"rows": chunk})


def write_pack(conn: Any, pack: dict[str, Any], embeddings: dict[str, list[float]]) -> None:
    """Write papers, authors, topics, citations and the Pack node in one transaction."""
    papers = pack["papers"]
    rows = paper_rows(papers, embeddings)
    conn.autocommit = False
    try:
        _run_batched(conn, queries.MERGE_PAPERS, rows)
        _run_batched(conn, queries.MERGE_AUTHORS, author_rows(papers))
        _run_batched(conn, queries.MERGE_TOPICS, topic_rows(papers))
        _run_batched(conn, queries.MERGE_CITES, cites_rows(pack["edges"]))
        conn.execute(
            queries.MERGE_PACK,
            {"name": pack["name"], "seeds": list(pack["seeds"]), "builtAt": pack["built_at"]},
        )
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.autocommit = True


def pack_summary(conn: Any) -> dict[str, Any]:
    """Return the Pack node's name, build time, seeds and seed titles, plus the paper count."""
    rows = conn.execute(queries.PACK_SUMMARY).data()
    info = rows[0] if rows else {"name": None, "built_at": None, "seeds": [], "seed_titles": []}
    papers = conn.execute(queries.COUNT_PAPERS).single()["papers"]
    return {**info, "seeds": list(info["seeds"] or []), "seed_titles": list(info["seed_titles"] or []),
            "papers": papers}


def store_counts(conn: Any) -> tuple[dict[str, int], dict[str, int]]:
    """Return (nodes per label, relationships per type)."""
    nodes = {r["label"]: r["n"] for r in conn.execute(queries.COUNT_NODES_BY_LABEL)}
    rels = {r["type"]: r["n"] for r in conn.execute(queries.COUNT_RELS_BY_TYPE)}
    return nodes, rels
