"""Build data/packs/<name>.rl from seed papers."""

import argparse
import json
import shutil
import subprocess
import sys
from collections import Counter
from collections.abc import Iterable
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests

from readpath import arxiv, http, s2, store

Paper = dict[str, Any]
Edge = tuple[str, str]
TOP_CITED = 10
PACKS_DIR = Path(__file__).resolve().parent / "data" / "packs"
MODEL_NAME = "sentence-transformers/all-MiniLM-L6-v2"
EMBED_BATCH_SIZE = 64


# ---------- pure functions ----------


def count_citers(citing: Iterable[Paper], exclude: set[str]) -> Counter[str]:
    """Count how many distinct citing papers reference each id not in exclude."""
    counts: Counter[str] = Counter()
    for paper in citing:
        refs = set(paper.get("references", [])) - exclude - {paper["id"]}
        counts.update(refs)
    return counts


def top_candidates(counts: Counter[str], n: int) -> list[str]:
    """Return the n ids with the highest counts (ties broken by id)."""
    ranked = sorted(counts, key=lambda pid: (-counts[pid], pid))
    return ranked[: max(0, n)]


def select_best(papers: Iterable[Paper], counts: Counter[str], budget: int) -> list[Paper]:
    """Keep the best budget papers by (citer count, cited_by, id)."""
    ranked = sorted(papers, key=lambda p: (-counts[p["id"]], -(p.get("cited_by") or 0), p["id"]))
    return ranked[: max(0, budget)]


def filter_edges(papers: Iterable[Paper]) -> list[Edge]:
    """Return sorted, unique CITES edges whose two ends are both in the pack."""
    papers = list(papers)
    ids = {p["id"] for p in papers}
    edges = {
        (p["id"], ref)
        for p in papers
        for ref in p.get("references", [])
        if ref in ids and ref != p["id"]
    }
    return sorted(edges)


def in_pack_citations(edges: Iterable[Edge]) -> Counter[str]:
    """Count how many pack papers cite each paper."""
    return Counter(dst for _, dst in edges)


def attach_arxiv(papers: Iterable[Paper], meta: dict[str, dict[str, Any]]) -> list[Paper]:
    """Return copies of papers with abstract, primary_category and categories from arXiv."""
    result = []
    for p in papers:
        m = meta.get(p["arxiv"]) if p.get("arxiv") else None
        result.append(
            {
                **p,
                "abstract": (m or {}).get("abstract", ""),
                "primary_category": (m or {}).get("primary_category"),
                "categories": list((m or {}).get("categories", [])),
            }
        )
    return result


def summary_stats(papers: list[Paper], edges: list[Edge]) -> dict[str, Any]:
    """Compute the pack summary: levels, edges, abstracts, authors, categories, top cited."""
    total = len(papers)
    with_abstract = sum(1 for p in papers if p.get("abstract"))
    authors = {a.get("id") or a.get("name") for p in papers for a in p.get("authors", [])}
    categories = {c for p in papers for c in p.get("categories", [])}
    cited = in_pack_citations(edges)
    by_id = {p["id"]: p for p in papers}
    top = sorted(cited.items(), key=lambda kv: (-kv[1], kv[0]))[:TOP_CITED]
    return {
        "papers": total,
        "levels": dict(sorted(Counter(p["level"] for p in papers).items())),
        "edges": len(edges),
        "with_abstract": with_abstract,
        "abstract_pct": round(100 * with_abstract / total, 1) if total else 0.0,
        "authors": len(authors - {None}),
        "categories": len(categories),
        "top_cited": [(n, by_id[pid].get("year"), by_id[pid]["title"]) for pid, n in top],
    }


def paper_text(p: Paper) -> str:
    """Return the text to embed: "title. abstract", or just the title without an abstract."""
    title = (p.get("title") or "").strip()
    abstract = (p.get("abstract") or "").strip()
    return f"{title}. {abstract}" if abstract else title


def to_pack(name: str, seed_ids: list[str], papers: list[Paper], edges: list[Edge]) -> dict[str, Any]:
    """Assemble the pack JSON document (references are replaced by edges)."""
    return {
        "name": name,
        "seeds": seed_ids,
        "built_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "papers": [{k: v for k, v in p.items() if k != "references"} for p in papers],
        "edges": [list(e) for e in edges],
    }


# ---------- I/O ----------


def print_summary(stats: dict[str, Any]) -> None:
    """Print the pack summary."""
    names = {0: "seeds", 1: "level 1", 2: "level 2"}
    levels = ", ".join(f"{names.get(k, k)}: {v}" for k, v in stats["levels"].items())
    print(f"\nPapers:        {stats['papers']}  ({levels})")
    print(f"CITES edges:   {stats['edges']}")
    print(f"arXiv abstract: {stats['with_abstract']} ({stats['abstract_pct']}%)")
    print(f"Authors:       {stats['authors']}")
    print(f"Categories:    {stats['categories']}")
    print(f"\nTop {TOP_CITED} most cited inside the pack:")
    for count, year, title in stats["top_cited"]:
        print(f"  {count:4}  {year or '----'}  {title}")


def find_seeds(titles: list[str]) -> list[Paper]:
    """Match each seed title on Semantic Scholar and print the chosen paper."""
    seeds: dict[str, Paper] = {}
    for title in titles:
        raw = s2.match_title(title)
        if raw is None:
            print(f"WARNING: no Semantic Scholar match for seed {title!r}", file=sys.stderr)
            continue
        p = s2.simplify(raw)
        print(f"seed  {p['id']}  {p['year'] or '----'}  {p['arxiv'] or '-':12}  {p['title']}")
        seeds.setdefault(p["id"], {**p, "level": 0})
    return list(seeds.values())


def collect(name: str, seed_titles: list[str], max_papers: int) -> dict[str, Any] | None:
    """Collect seeds, level-1 and level-2 references plus arXiv metadata into a pack."""
    seeds = find_seeds(seed_titles)
    if not seeds:
        return None
    seed_ids = {p["id"] for p in seeds}

    level1_ids = sorted({r for p in seeds for r in p["references"]} - seed_ids)
    level1 = [{**s2.simplify(r), "level": 1} for r in s2.get_papers(level1_ids)]
    level1 = [p for p in level1 if p["id"] not in seed_ids]
    print(f"level 1: {len(level1)} papers fetched")

    known = seed_ids | {p["id"] for p in level1}
    counts = count_citers(level1, exclude=known)
    budget = max(0, max_papers - len(seeds) - len(level1))
    candidates = top_candidates(counts, int(max_papers * 1.5)) if budget else []
    fetched = [s2.simplify(r) for r in s2.get_papers(candidates)] if candidates else []
    fetched = [p for p in fetched if p["id"] not in known]
    level2 = [{**p, "level": 2} for p in select_best(fetched, counts, budget)]
    print(f"level 2: {len(counts)} candidates, {len(fetched)} fetched, {len(level2)} kept")

    papers = seeds + level1 + level2
    edges = filter_edges(papers)
    arxiv_ids = [p["arxiv"] for p in papers if p.get("arxiv")]
    print(f"arXiv: fetching metadata for {len(arxiv_ids)} papers (about 3 s per 100)")
    papers = attach_arxiv(papers, arxiv.get_metadata(arxiv_ids))
    return to_pack(name, [p["id"] for p in seeds], papers, edges)


def save_pack(pack: dict[str, Any]) -> Path:
    """Write the pack JSON to data/raw/<name>.pack.json and return its path."""
    path = http.RAW_DIR / f"{pack['name']}.pack.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(pack, ensure_ascii=False, indent=1), encoding="utf-8")
    return path


def embed_papers(papers: list[Paper]) -> dict[str, list[float]]:
    """Embed every paper's text with all-MiniLM-L6-v2 on the CPU."""
    from sentence_transformers import SentenceTransformer

    model = SentenceTransformer(MODEL_NAME, device="cpu")
    vectors = model.encode(
        [paper_text(p) for p in papers], batch_size=EMBED_BATCH_SIZE, show_progress_bar=True
    )
    return {p["id"]: [float(x) for x in v] for p, v in zip(papers, vectors, strict=True)}


def _remove(path: Path) -> None:
    """Delete a store at path, whether it is a single file or a directory."""
    if path.is_dir():
        shutil.rmtree(path)
    elif path.exists():
        path.unlink()


def write_store(pack: dict[str, Any], embeddings: dict[str, list[float]], packs_dir: Path) -> Path:
    """Write the pack to <name>.tmp.rl, clone it compactly to <name>.rl and return that path."""
    relate_bin = shutil.which("relate")
    if relate_bin is None:
        raise RuntimeError("the `relate` CLI is not on PATH; it is needed for `relate clone`")
    packs_dir.mkdir(parents=True, exist_ok=True)
    tmp = packs_dir / f"{pack['name']}.tmp.rl"
    final = packs_dir / f"{pack['name']}.rl"
    _remove(tmp)
    conn = store.open_store(tmp)
    try:
        store.create_schema(conn)
        store.write_pack(conn, pack, embeddings)
    finally:
        conn.close()
    _remove(final)
    subprocess.run([relate_bin, "clone", str(tmp), str(final)], check=True)
    _remove(tmp)
    return final


def print_store_counts(path: Path) -> None:
    """Open a store read-only and print node and relationship counts."""
    conn = store.open_store(path, read_only=True)
    try:
        nodes, rels = store.store_counts(conn)
    finally:
        conn.close()
    print(f"\nWrote {path}")
    print("Nodes:         " + ", ".join(f"{k} {v}" for k, v in nodes.items()))
    print("Relationships: " + ", ".join(f"{k} {v}" for k, v in rels.items()))


def build_parser() -> argparse.ArgumentParser:
    """Build the argument parser."""
    parser = argparse.ArgumentParser(description="Build a ReadPath topic pack from seed papers.")
    parser.add_argument("--name", required=True, help="pack name, e.g. transformers")
    parser.add_argument("--seed", required=True, action="append", help="seed paper title (repeatable)")
    parser.add_argument("--max-papers", type=int, default=800, help="maximum papers in the pack")
    parser.add_argument("--dry-run", action="store_true", help="stop after the summary")
    return parser


def main(argv: list[str] | None = None) -> int:
    """Collect a pack, save it as JSON and print a summary."""
    args = build_parser().parse_args(argv)
    try:
        pack = collect(args.name, args.seed, args.max_papers)
    except requests.RequestException as exc:
        status = getattr(getattr(exc, "response", None), "status_code", None)
        print(f"API request failed after retries ({status or type(exc).__name__}).", file=sys.stderr)
        print("Run the same command again: finished calls are cached in data/raw/.", file=sys.stderr)
        return 1
    if pack is None:
        print("No seed paper matched; nothing to build.", file=sys.stderr)
        return 1
    path = save_pack(pack)
    print(f"\nSaved {path}")
    print_summary(summary_stats(pack["papers"], [tuple(e) for e in pack["edges"]]))
    if args.dry_run:
        return 0
    print(f"\nEmbedding {len(pack['papers'])} papers with {MODEL_NAME} (CPU)")
    embeddings = embed_papers(pack["papers"])
    print_store_counts(write_store(pack, embeddings, PACKS_DIR))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
