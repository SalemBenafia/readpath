"""Tests for readpath.store: row builders and writing a fake pack into a real .rl file."""

import random
import shutil
from pathlib import Path

import pytest

import build_pack
from readpath import store


def fake_pack() -> dict:
    """Return a 5-paper pack with authors, categories and in-pack edges."""
    a1, a2, a3 = ({"id": f"u{i}", "name": f"Author {i}"} for i in range(1, 4))
    papers = [
        {"id": "p1", "title": "Seed", "year": 2017, "cited_by": 100, "arxiv": "1706.03762",
         "doi": None, "authors": [a1, a2], "level": 0, "abstract": "Attention only.",
         "primary_category": "cs.CL", "categories": ["cs.CL", "cs.LG"]},
        {"id": "p2", "title": "RNN", "year": 2014, "cited_by": 50, "arxiv": "1409.0473",
         "doi": "10.1/x", "authors": [a2, {"id": None, "name": "No Id"}], "level": 1,
         "abstract": "Align and translate.", "primary_category": "cs.CL", "categories": ["cs.CL"]},
        {"id": "p3", "title": "LSTM", "year": 1997, "cited_by": 90, "arxiv": None, "doi": None,
         "authors": [a3], "level": 1, "abstract": "", "primary_category": None, "categories": []},
        {"id": "p4", "title": "CNN", "year": 2012, "cited_by": 80, "arxiv": None, "doi": None,
         "authors": [], "level": 2, "abstract": "", "primary_category": None, "categories": []},
        {"id": "p5", "title": "Adam", "year": 2014, "cited_by": 70, "arxiv": "1412.6980",
         "doi": None, "authors": [a1], "level": 2, "abstract": "An optimizer.",
         "primary_category": "cs.LG", "categories": ["cs.LG", "math.OC"]},
    ]
    edges = [["p1", "p2"], ["p1", "p3"], ["p1", "p5"], ["p2", "p3"], ["p2", "p4"]]
    return {"name": "toy", "seeds": ["p1"], "built_at": "2026-11-25T00:00:00+00:00",
            "papers": papers, "edges": edges}


def fake_embeddings(pack: dict) -> dict[str, list[float]]:
    """Return a random 384-number vector per paper."""
    rng = random.Random(0)
    return {p["id"]: [rng.uniform(-1, 1) for _ in range(384)] for p in pack["papers"]}


EXPECTED_NODES = {"Author": 3, "Pack": 1, "Paper": 5, "Topic": 3}
# BY: p1->u1, p1->u2, p2->u2 (id-less author skipped), p3->u3, p5->u1
EXPECTED_RELS = {"ABOUT": 5, "BY": 5, "CITES": 5}


def test_row_builders() -> None:
    """Rows carry the right fields, skip id-less authors and flag the primary topic."""
    pack = fake_pack()
    assert len(store.author_rows(pack["papers"])) == 5
    topics = store.topic_rows(pack["papers"])
    assert {"paper": "p1", "topic": "cs.CL", "primary": True} in topics
    assert {"paper": "p1", "topic": "cs.LG", "primary": False} in topics
    assert store.cites_rows([["a", "b"]]) == [{"src": "a", "dst": "b"}]
    rows = store.paper_rows(pack["papers"], fake_embeddings(pack))
    assert rows[0]["citedBy"] == 100 and len(rows[0]["emb"]) == 384


def test_paper_rows_rejects_bad_embeddings() -> None:
    """A missing or wrong-length embedding raises ValueError."""
    pack = fake_pack()
    with pytest.raises(ValueError):
        store.paper_rows(pack["papers"], {})
    with pytest.raises(ValueError):
        store.paper_rows(pack["papers"][:1], {"p1": [0.0] * 10})


def test_batches() -> None:
    """Rows are split into slices of at most the batch size."""
    assert [len(b) for b in store.batches([{}] * 450)] == [200, 200, 50]


def test_write_pack_counts(tmp_path: Path) -> None:
    """A fake pack written to a .rl file reads back with the expected counts."""
    pack = fake_pack()
    path = tmp_path / "toy.rl"
    conn = store.open_store(path)
    store.create_schema(conn)
    store.create_schema(conn)  # idempotent
    store.write_pack(conn, pack, fake_embeddings(pack))
    conn.close()

    conn = store.open_store(path, read_only=True)
    try:
        assert store.store_counts(conn) == (EXPECTED_NODES, EXPECTED_RELS)
        primary = conn.execute(
            "MATCH (p:Paper)-[r:ABOUT {primary: true}]->(t:Topic) RETURN p.id AS p, t.id AS t ORDER BY p"
        ).data()
        assert primary == [{"p": "p1", "t": "cs.CL"}, {"p": "p2", "t": "cs.CL"}, {"p": "p5", "t": "cs.LG"}]
        dims = conn.execute(
            "MATCH (p:Paper) RETURN min(vector_dimension_count(p.embedding)) AS d"
        ).single()["d"]
        assert dims == 384
        pack_node = conn.execute("MATCH (k:Pack) RETURN k.name AS name, k.seeds AS seeds").single()
        assert (pack_node["name"], pack_node["seeds"]) == ("toy", ["p1"])
    finally:
        conn.close()


@pytest.mark.skipif(shutil.which("relate") is None, reason="relate CLI not installed")
def test_write_store_clones_and_removes_tmp(tmp_path: Path) -> None:
    """write_store produces <name>.rl via relate clone and removes the tmp store."""
    pack = fake_pack()
    final = build_pack.write_store(pack, fake_embeddings(pack), tmp_path)
    assert final == tmp_path / "toy.rl" and final.exists()
    assert not (tmp_path / "toy.tmp.rl").exists()
    conn = store.open_store(final, read_only=True)
    try:
        assert store.store_counts(conn) == (EXPECTED_NODES, EXPECTED_RELS)
    finally:
        conn.close()
    # A rebuild replaces the old pack instead of failing.
    build_pack.write_store(pack, fake_embeddings(pack), tmp_path)
    assert final.exists()
