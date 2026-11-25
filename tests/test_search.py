"""Tests for readpath.search: fusion math, query cleaning and searches on the fixture pack."""

from pathlib import Path
from typing import Any

import pytest

from readpath import search


class FakeEmbedder:
    """Returns a fixed vector (or nothing, to simulate a model that failed to load)."""

    def __init__(self, vector: list[float] | None) -> None:
        """Store the vector to return."""
        self.vector = vector
        self.available = vector is not None

    def encode(self, text: str) -> list[float] | None:
        """Return the fixed vector regardless of text."""
        return self.vector


def hit(pid: str) -> dict:
    """Make a minimal search hit."""
    return {"id": pid, "title": f"T{pid}", "year": 2000, "score": 1.0}


# ---------- fusion math (pure Python) ----------


def test_rrf_scores_and_ranks() -> None:
    """score = sum of 1/(60 + rank) over the lists a paper appears in, ranks from 1."""
    fused = search.rrf_fuse([hit("a"), hit("b"), hit("c")], [hit("b"), hit("d")], k=10)
    by_id = {h["id"]: h for h in fused}
    assert by_id["b"]["score"] == pytest.approx(1 / 62 + 1 / 61)
    assert by_id["a"]["score"] == pytest.approx(1 / 61)
    assert by_id["d"]["score"] == pytest.approx(1 / 62)
    assert (by_id["b"]["vector_rank"], by_id["b"]["text_rank"]) == (2, 1)
    assert (by_id["a"]["vector_rank"], by_id["a"]["text_rank"]) == (1, None)
    assert (by_id["d"]["vector_rank"], by_id["d"]["text_rank"]) == (None, 2)
    assert [h["id"] for h in fused] == ["b", "a", "d", "c"]


def test_rrf_tie_break_and_top_k() -> None:
    """Equal scores are ordered by best single rank, then id; only k results are returned."""
    fused = search.rrf_fuse([hit("x"), hit("y")], [hit("y"), hit("x")], k=1)
    assert len(fused) == 1 and fused[0]["id"] == "x"
    assert search.rrf_fuse([], [], k=5) == []


def test_rrf_ignores_duplicate_within_a_list() -> None:
    """A paper listed twice in one ranking only counts its first (best) rank."""
    fused = search.rrf_fuse([hit("a"), hit("a")], [], k=5)
    assert fused[0]["score"] == pytest.approx(1 / 61) and fused[0]["vector_rank"] == 1


@pytest.mark.parametrize(
    ("raw", "clean"),
    [
        ('"machine translation', "machine translation"),
        ("title: (attention) AND", "title attention and"),
        ("self-attention for C++!", "self attention for c"),
        ("[1 TO 2] {x} \\ ~ * ^", "1 to 2 x"),
        ("  ?!:  ", ""),
    ],
)
def test_clean_query(raw: str, clean: str) -> None:
    """Symbols become spaces and operators become plain lowercase words."""
    assert search.clean_query(raw) == clean


# ---------- searches on the fixture pack ----------


def test_vector_search_finds_identical_vector(toy_conn: Any, toy_embeddings: dict) -> None:
    """Querying with a paper's own vector ranks that paper first with score ~1."""
    hits = search.vector_search(toy_conn, "anything", k=3, embedder=FakeEmbedder(toy_embeddings["p3"]))
    assert len(hits) == 3
    assert hits[0]["id"] == "p3" and hits[0]["title"] == "Long Short-Term Memory"
    assert hits[0]["score"] == pytest.approx(1.0, abs=1e-4)
    assert set(hits[0]) == {"id", "title", "year", "cited_by", "score"}


def test_vector_search_without_model_returns_nothing(toy_conn: Any) -> None:
    """An unavailable embedder yields no vector hits instead of an error."""
    assert search.vector_search(toy_conn, "attention", embedder=FakeEmbedder(None)) == []


def test_fulltext_search_handles_symbols(toy_conn: Any) -> None:
    """Quotes, colons, brackets and dangling operators do not break the query."""
    hits = search.fulltext_search(toy_conn, 'adam: "stochastic (optimization AND', k=5)
    assert hits[0]["id"] == "p5"
    assert search.fulltext_search(toy_conn, '"?!: \\', k=5) == []


def test_hybrid_search_combines_both(toy_conn: Any, toy_embeddings: dict) -> None:
    """A paper found by both searches gets both ranks and comes out on top."""
    hits = search.hybrid_search(
        toy_conn, "self-attention machine translation", k=3,
        embedder=FakeEmbedder(toy_embeddings["p1"]),
    )
    assert hits[0]["id"] == "p1"
    assert hits[0]["vector_rank"] == 1 and hits[0]["text_rank"] is not None
    assert len(hits) == 3


def test_hybrid_search_falls_back_to_fulltext(toy_conn: Any) -> None:
    """Without a model, hybrid search returns full-text results with no vector rank."""
    hits = search.hybrid_search(toy_conn, "machine translation", k=5, embedder=FakeEmbedder(None))
    assert hits and all(h["vector_rank"] is None and h["text_rank"] for h in hits)


def test_embedder_sets_flag_when_model_cannot_load(monkeypatch: pytest.MonkeyPatch) -> None:
    """A model that fails to load marks the embedder unavailable and encode returns None."""
    import sentence_transformers

    def boom(*args: object, **kwargs: object) -> None:
        """Simulate a model that cannot be downloaded."""
        raise OSError("no internet")

    monkeypatch.setattr(sentence_transformers, "SentenceTransformer", boom)
    embedder = search.Embedder()
    assert embedder.encode("hello") is None
    assert embedder.available is False


def test_cli_find_prints_both_ranks(
    toy_store_path: Path,
    toy_embeddings: dict,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """The find command prints fused results with their vector and full-text ranks."""
    from readpath import cli, store

    monkeypatch.setattr(store, "pack_path", lambda name: toy_store_path)
    monkeypatch.setattr(search, "default_embedder", lambda: FakeEmbedder(toy_embeddings["p1"]))
    assert cli.main(["find", "self-attention machine translation", "--pack", "toy", "-k", "2"]) == 0
    lines = capsys.readouterr().out.splitlines()
    assert lines[0].split() == ["#", "rrf", "vec", "text", "year", "title"]
    first = lines[1].split()
    assert first[0] == "1" and first[2] == "1" and first[3] != "-"
    assert lines[1].endswith("Attention Is All You Need")
    assert len(lines) == 3


def test_cli_find_without_model_says_so(
    toy_store_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """With no embedding model, find still answers from full-text and says so."""
    from readpath import cli, store

    monkeypatch.setattr(store, "pack_path", lambda name: toy_store_path)
    monkeypatch.setattr(search, "default_embedder", lambda: FakeEmbedder(None))
    assert cli.main(["find", "machine translation", "--pack", "toy"]) == 0
    out = capsys.readouterr().out
    assert "full-text results only" in out and "Neural Machine Translation" in out
