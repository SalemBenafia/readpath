"""Vector and full-text paper search combined with reciprocal rank fusion."""

import re
import sys
from typing import Any

from readpath import queries

MODEL_NAME = "sentence-transformers/all-MiniLM-L6-v2"
DIMENSIONS = 384
RRF_K = 60
CANDIDATES = 20

Hit = dict[str, Any]


class Embedder:
    """Lazily loads all-MiniLM-L6-v2 once; sets available=False if it cannot be loaded."""

    def __init__(self, model_name: str = MODEL_NAME) -> None:
        """Remember the model name; nothing is loaded until the first encode()."""
        self.model_name = model_name
        self.available = True
        self._model: Any = None

    def _load(self) -> Any:
        """Load the model on first use, or mark the embedder unavailable on failure."""
        if self._model is None and self.available:
            try:
                from sentence_transformers import SentenceTransformer

                try:  # cached copy first: no network call, works offline
                    self._model = SentenceTransformer(
                        self.model_name, device="cpu", local_files_only=True
                    )
                except Exception:  # not cached yet: download once
                    self._model = SentenceTransformer(self.model_name, device="cpu")
            except Exception as exc:  # no internet on first run, missing files, ...
                self.available = False
                print(f"Embedding model unavailable ({type(exc).__name__}); "
                      "using full-text search only.", file=sys.stderr)
        return self._model

    def load(self) -> bool:
        """Load the model now (if not loaded yet) and return whether it is available."""
        self._load()
        return self.available

    def encode(self, text: str) -> list[float] | None:
        """Return 384 floats for text, or None when the model is unavailable."""
        model = self._load()
        if model is None:
            return None
        return [float(x) for x in model.encode(text)]


_default_embedder: Embedder | None = None


def default_embedder() -> Embedder:
    """Return the shared process-wide Embedder."""
    global _default_embedder
    if _default_embedder is None:
        _default_embedder = Embedder()
    return _default_embedder


def clean_query(text: str) -> str:
    """Keep only lowercase word tokens so quotes, colons, brackets and operators cannot break full-text syntax."""
    return " ".join(re.findall(r"\w+", text.lower()))


def _hits(rows: Any) -> list[Hit]:
    """Turn result rows into {id, title, year, cited_by, score} dicts."""
    return [
        {"id": r["id"], "title": r["title"], "year": r["year"], "cited_by": r["cited_by"],
         "score": r["score"]}
        for r in rows
    ]


def vector_search(
    conn: Any, text: str, k: int = 10, embedder: Embedder | None = None
) -> list[Hit]:
    """Return the k papers whose embedding is closest to text (empty if no model)."""
    vector = (embedder or default_embedder()).encode(text)
    if vector is None or not text.strip():
        return []
    return _hits(conn.execute(queries.VECTOR_SEARCH, {"vector": vector, "k": k}))


def fulltext_search(conn: Any, text: str, k: int = 10) -> list[Hit]:
    """Return the k best full-text matches for text in titles and abstracts."""
    query = clean_query(text)
    if not query:
        return []
    return _hits(conn.execute(queries.FULLTEXT_SEARCH, {"query": query, "k": k}))


def rrf_fuse(vector_hits: list[Hit], text_hits: list[Hit], k: int = 5) -> list[Hit]:
    """Fuse two ranked lists with reciprocal rank fusion, keeping each paper's two ranks."""
    fused: dict[str, Hit] = {}
    for key, hits in (("vector_rank", vector_hits), ("text_rank", text_hits)):
        for rank, hit in enumerate(hits, start=1):
            entry = fused.setdefault(
                hit["id"],
                {"id": hit["id"], "title": hit["title"], "year": hit["year"],
                 "cited_by": hit.get("cited_by"), "score": 0.0,
                 "vector_rank": None, "text_rank": None},
            )
            if entry[key] is None:
                entry[key] = rank
                entry["score"] += 1.0 / (RRF_K + rank)
    ranked = sorted(fused.values(), key=lambda h: (-h["score"], _best_rank(h), h["id"]))
    return ranked[:k]


def _best_rank(hit: Hit) -> int:
    """Return the better of a fused hit's two ranks (for tie-breaking)."""
    return min(r for r in (hit["vector_rank"], hit["text_rank"]) if r is not None)


def hybrid_search(
    conn: Any, text: str, k: int = 5, embedder: Embedder | None = None
) -> list[Hit]:
    """Run vector and full-text search and return the top k fused results."""
    depth = max(CANDIDATES, k)
    vector_hits = vector_search(conn, text, depth, embedder)
    text_hits = fulltext_search(conn, text, depth)
    return rrf_fuse(vector_hits, text_hits, k)
