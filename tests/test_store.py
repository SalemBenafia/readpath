"""Tests for readpath.store: row builders and writing a fake pack into a real .rl file."""

import shutil
from pathlib import Path

import pytest

import build_pack
from readpath import store

EXPECTED_NODES = {"Author": 3, "Pack": 1, "Paper": 5, "Topic": 3}
# BY: p1->u1, p1->u2, p2->u2 (id-less author skipped), p3->u3, p5->u1
EXPECTED_RELS = {"ABOUT": 5, "BY": 5, "CITES": 5}


def test_row_builders(toy_pack: dict, toy_embeddings: dict) -> None:
    """Rows carry the right fields, skip id-less authors and flag the primary topic."""
    assert len(store.author_rows(toy_pack["papers"])) == 5
    topics = store.topic_rows(toy_pack["papers"])
    assert {"paper": "p1", "topic": "cs.CL", "primary": True} in topics
    assert {"paper": "p1", "topic": "cs.LG", "primary": False} in topics
    assert store.cites_rows([["a", "b"]]) == [{"src": "a", "dst": "b"}]
    rows = store.paper_rows(toy_pack["papers"], toy_embeddings)
    assert rows[0]["citedBy"] == 100 and len(rows[0]["emb"]) == 384


def test_paper_rows_rejects_bad_embeddings(toy_pack: dict) -> None:
    """A missing or wrong-length embedding raises ValueError."""
    with pytest.raises(ValueError):
        store.paper_rows(toy_pack["papers"], {})
    with pytest.raises(ValueError):
        store.paper_rows(toy_pack["papers"][:1], {"p1": [0.0] * 10})


def test_batches() -> None:
    """Rows are split into slices of at most the batch size."""
    assert [len(b) for b in store.batches([{}] * 450)] == [200, 200, 50]


def test_pack_path_and_list_packs(tmp_path: Path) -> None:
    """Pack paths are <name>.rl and temporary builds are not listed."""
    for name in ("b.rl", "a.rl", "a.tmp.rl"):
        (tmp_path / name).touch()
    assert store.pack_path("a", tmp_path) == tmp_path / "a.rl"
    assert store.list_packs(tmp_path) == ["a", "b"]


def test_write_pack_counts(tmp_path: Path, toy_pack: dict, toy_embeddings: dict) -> None:
    """A fake pack written to a .rl file reads back with the expected counts."""
    path = tmp_path / "toy.rl"
    conn = store.open_store(path)
    store.create_schema(conn)
    store.create_schema(conn)  # idempotent
    store.write_pack(conn, toy_pack, toy_embeddings)
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
def test_write_store_clones_and_removes_tmp(
    tmp_path: Path, toy_pack: dict, toy_embeddings: dict
) -> None:
    """write_store produces <name>.rl via relate clone and removes the tmp store."""
    final = build_pack.write_store(toy_pack, toy_embeddings, tmp_path)
    assert final == tmp_path / "toy.rl" and final.exists()
    assert not (tmp_path / "toy.tmp.rl").exists()
    conn = store.open_store(final, read_only=True)
    try:
        assert store.store_counts(conn) == (EXPECTED_NODES, EXPECTED_RELS)
    finally:
        conn.close()
    # A rebuild replaces the old pack instead of failing.
    build_pack.write_store(toy_pack, toy_embeddings, tmp_path)
    assert final.exists()
