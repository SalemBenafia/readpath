"""Shared test fixtures: a tiny 5-paper pack with random vectors, written to a temp .rl store."""

import random
from pathlib import Path

import pytest

from readpath import store

AUTHORS = [{"id": f"u{i}", "name": f"Author {i}"} for i in range(1, 4)]


def make_pack() -> dict:
    """Return a 5-paper pack with authors, categories and in-pack edges."""
    a1, a2, a3 = AUTHORS
    papers = [
        {"id": "p1", "title": "Attention Is All You Need", "year": 2017, "cited_by": 100,
         "arxiv": "1706.03762", "doi": None, "authors": [a1, a2], "level": 0,
         "abstract": "The Transformer uses self-attention for machine translation.",
         "primary_category": "cs.CL", "categories": ["cs.CL", "cs.LG"]},
        {"id": "p2", "title": "Neural Machine Translation by Jointly Learning to Align and Translate",
         "year": 2014, "cited_by": 50, "arxiv": "1409.0473", "doi": "10.1/x",
         "authors": [a2, {"id": None, "name": "No Id"}], "level": 1,
         "abstract": "An attention mechanism that learns to align source and target words.",
         "primary_category": "cs.CL", "categories": ["cs.CL"]},
        {"id": "p3", "title": "Long Short-Term Memory", "year": 1997, "cited_by": 90,
         "arxiv": None, "doi": None, "authors": [a3], "level": 1, "abstract": "",
         "primary_category": None, "categories": []},
        {"id": "p4", "title": "ImageNet Classification with Deep Convolutional Neural Networks",
         "year": 2012, "cited_by": 80, "arxiv": None, "doi": None, "authors": [], "level": 2,
         "abstract": "", "primary_category": None, "categories": []},
        {"id": "p5", "title": "Adam: A Method for Stochastic Optimization", "year": 2014,
         "cited_by": 70, "arxiv": "1412.6980", "doi": None, "authors": [a1], "level": 2,
         "abstract": "An optimizer based on adaptive estimates of lower-order moments.",
         "primary_category": "cs.LG", "categories": ["cs.LG", "math.OC"]},
    ]
    edges = [["p1", "p2"], ["p1", "p3"], ["p1", "p5"], ["p2", "p3"], ["p2", "p4"]]
    return {"name": "toy", "seeds": ["p1"], "built_at": "2026-11-25T00:00:00+00:00",
            "papers": papers, "edges": edges}


def make_embeddings(pack: dict) -> dict[str, list[float]]:
    """Return a seeded random 384-number vector per paper."""
    rng = random.Random(0)
    return {p["id"]: [rng.uniform(-1, 1) for _ in range(384)] for p in pack["papers"]}


@pytest.fixture
def toy_pack() -> dict:
    """A fresh copy of the 5-paper fake pack."""
    return make_pack()


@pytest.fixture
def toy_embeddings() -> dict[str, list[float]]:
    """Random 384-number vectors for the fake pack."""
    return make_embeddings(make_pack())


@pytest.fixture(scope="session")
def toy_store_path(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """The fake pack written once to a temp .rl store."""
    path = tmp_path_factory.mktemp("packs") / "toy.rl"
    pack = make_pack()
    conn = store.open_store(path)
    try:
        store.create_schema(conn)
        store.write_pack(conn, pack, make_embeddings(pack))
    finally:
        conn.close()
    return path


@pytest.fixture
def toy_conn(toy_store_path: Path):
    """A read-only connection to the fake pack store, closed after the test."""
    conn = store.open_store(toy_store_path, read_only=True)
    yield conn
    conn.close()
