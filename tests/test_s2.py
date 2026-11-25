"""Tests for the Semantic Scholar client (no network)."""

import json
from pathlib import Path

import pytest

from readpath import s2

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def batch() -> list:
    """Return the saved sample batch response."""
    return json.loads((FIXTURES / "s2_batch.json").read_text())


def test_simplify_fields(batch: list) -> None:
    """simplify() keeps exactly the ReadPath fields and drops the rest."""
    p = s2.simplify(batch[0])
    assert p["id"] == "204e3073870fae3d05bcbc2f6a8e263d9b72e776"
    assert p["title"] == "Attention is All you Need"
    assert p["year"] == 2017
    assert p["cited_by"] == 204874
    assert p["arxiv"] == "1706.03762"
    assert p["doi"] == "10.48550/arXiv.1706.03762"
    assert p["authors"][0] == {"id": "40348417", "name": "Ashish Vaswani"}
    assert set(p) == {"id", "title", "year", "cited_by", "arxiv", "doi", "authors", "references"}


def test_simplify_skips_null_references(batch: list) -> None:
    """References without a paperId are dropped."""
    assert s2.simplify(batch[0])["references"] == [
        "032274e57f7d8b456bd255fe76b909b2c1d7458e",
        "43428880d75b3a14257c3ee9bda054e61eb869c0",
    ]


def test_simplify_caps_authors_at_ten(batch: list) -> None:
    """Only the first 10 authors are kept."""
    raw = dict(batch[0])
    raw["authors"] = [{"authorId": str(i), "name": f"A{i}"} for i in range(15)]
    authors = s2.simplify(raw)["authors"]
    assert len(authors) == 10
    assert authors[-1] == {"id": "9", "name": "A9"}


def test_simplify_handles_missing_values(batch: list) -> None:
    """Null externalIds, year, citationCount and references do not crash."""
    p = s2.simplify(batch[2])
    assert p["arxiv"] is None and p["doi"] is None
    assert p["year"] is None and p["cited_by"] == 0
    assert p["authors"] == [] and p["references"] == []


def test_fields_never_request_abstract() -> None:
    """The Semantic Scholar abstract field is never requested."""
    assert "abstract" not in s2.FIELDS


def test_get_papers_chunks_and_skips_nulls(batch: list, monkeypatch: pytest.MonkeyPatch) -> None:
    """get_papers sends at most 500 ids per call and skips null results."""
    sizes: list[int] = []

    def fake_fetch(method: str, url: str, **kwargs: object) -> tuple[int, str]:
        sizes.append(len(json.loads(kwargs["body"])["ids"]))
        return 200, json.dumps(batch)

    monkeypatch.setattr(s2.http, "fetch", fake_fetch)
    monkeypatch.setattr(s2, "_headers", lambda: {})
    papers = s2.get_papers([f"id{i}" for i in range(1001)])
    assert sizes == [500, 500, 1]
    assert len(papers) == 3 * 2
