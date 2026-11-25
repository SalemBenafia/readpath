"""Tests for the arXiv client (no network)."""

from pathlib import Path
from urllib.parse import parse_qs, urlparse

import pytest

from readpath import arxiv

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("1706.03762v7", "1706.03762"),
        ("1706.03762", "1706.03762"),
        ("hep-th/9711200v3", "hep-th/9711200"),
        (" 2401.00001v12 ", "2401.00001"),
    ],
)
def test_strip_version(raw: str, expected: str) -> None:
    """Version suffixes are removed; ids without one are unchanged."""
    assert arxiv.strip_version(raw) == expected


def test_parse_feed() -> None:
    """The Atom feed is parsed into abstract and categories per id."""
    meta = arxiv.parse_feed((FIXTURES / "arxiv_feed.xml").read_text())
    assert set(meta) == {"1706.03762", "hep-th/9711200"}
    assert meta["1706.03762"]["primary_category"] == "cs.CL"
    assert meta["1706.03762"]["categories"] == ["cs.CL", "cs.LG"]
    assert meta["hep-th/9711200"]["categories"] == ["hep-th"]


def test_parse_feed_collapses_whitespace() -> None:
    """Abstracts have newlines and repeated spaces collapsed and are trimmed."""
    meta = arxiv.parse_feed((FIXTURES / "arxiv_feed.xml").read_text())
    abstract = meta["1706.03762"]["abstract"]
    assert abstract.startswith("The dominant sequence transduction models")
    assert abstract.endswith("the Transformer.")
    assert "\n" not in abstract and "  " not in abstract
    assert meta["hep-th/9711200"]["abstract"].startswith("We show")


def test_get_metadata_strips_dedupes_and_throttles(monkeypatch: pytest.MonkeyPatch) -> None:
    """Ids are version-stripped and deduplicated, and the throttle hook is passed."""
    urls: list[str] = []

    def fake_fetch(method: str, url: str, **kwargs: object) -> tuple[int, str]:
        """Record the call and return the saved fixture response."""
        urls.append(url)
        assert kwargs["before_request"] is arxiv._throttle
        return 200, (FIXTURES / "arxiv_feed.xml").read_text()

    monkeypatch.setattr(arxiv.http, "fetch", fake_fetch)
    meta = arxiv.get_metadata(["1706.03762v7", "1706.03762", "hep-th/9711200v3"])
    assert len(urls) == 1
    assert "id_list=1706.03762%2Chep-th%2F9711200" in urls[0]
    assert "max_results=2" in urls[0]
    assert "1706.03762" in meta


def test_throttle_waits_three_seconds(monkeypatch: pytest.MonkeyPatch) -> None:
    """A second call right after the first sleeps for the rest of the 3 s window."""
    clock = [100.0]
    slept: list[float] = []
    monkeypatch.setattr(arxiv.time, "monotonic", lambda: clock[0])
    monkeypatch.setattr(arxiv.time, "sleep", lambda s: slept.append(s))
    monkeypatch.setattr(arxiv, "_last_call", 0.0)
    arxiv._throttle()
    clock[0] += 1.0
    arxiv._throttle()
    assert slept == [pytest.approx(2.0)]


def test_get_metadata_batches_of_100(monkeypatch: pytest.MonkeyPatch) -> None:
    """205 ids are requested in 3 calls of 100, 100 and 5 ids."""
    sizes: list[int] = []

    def fake_fetch(method: str, url: str, **kwargs: object) -> tuple[int, str]:
        """Record how many ids each call asks for and return an empty feed."""
        query = parse_qs(urlparse(url).query)
        sizes.append(len(query["id_list"][0].split(",")))
        assert query["max_results"] == [str(sizes[-1])]
        return 200, '<feed xmlns="http://www.w3.org/2005/Atom"></feed>'

    monkeypatch.setattr(arxiv.http, "fetch", fake_fetch)
    assert arxiv.get_metadata([f"2401.{i:05d}v1" for i in range(205)]) == {}
    assert sizes == [100, 100, 5]
