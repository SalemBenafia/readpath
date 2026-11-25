"""Tests for the shared cache and retry helper (no network)."""

from pathlib import Path

import pytest
import requests

from readpath import http


class FakeResponse:
    """A minimal stand-in for requests.Response."""

    def __init__(self, status: int, text: str = "", headers: dict | None = None) -> None:
        """Store status, body and headers."""
        self.status_code = status
        self.text = text
        self.headers = headers or {}

    def raise_for_status(self) -> None:
        """Raise HTTPError for 4xx and 5xx statuses."""
        if self.status_code >= 400:
            raise requests.HTTPError(f"HTTP {self.status_code}", response=self)


@pytest.fixture
def env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> dict:
    """Redirect the cache to tmp_path and record sleeps and requests."""
    state: dict = {"responses": [], "calls": 0, "sleeps": []}

    def fake_request(*args: object, **kwargs: object) -> FakeResponse:
        """Count the call and return the next queued response."""
        state["calls"] += 1
        return state["responses"].pop(0)

    monkeypatch.setattr(http, "RAW_DIR", tmp_path)
    monkeypatch.setattr(http.requests, "request", fake_request)
    monkeypatch.setattr(http.time, "sleep", lambda s: state["sleeps"].append(s))
    return state


def test_cache_key_ignores_headers_and_depends_on_body() -> None:
    """The key covers method, URL and body only."""
    assert http.cache_key("GET", "u") == http.cache_key("get", "u", None)
    assert http.cache_key("POST", "u", b"a") != http.cache_key("POST", "u", b"b")


def test_retries_on_429_then_caches(env: dict) -> None:
    """A 429 is retried after 2 s, and the result is then served from cache."""
    env["responses"] = [FakeResponse(429), FakeResponse(200, "ok")]
    assert http.fetch("GET", "https://x/y", headers={"x-api-key": "secret"}) == (200, "ok")
    assert env["sleeps"] == [2.0]
    assert http.fetch("GET", "https://x/y") == (200, "ok")
    assert env["calls"] == 2
    cached = next(http.RAW_DIR.glob("*.json")).read_text()
    assert "secret" not in cached


def test_backoff_doubles_and_gives_up_after_six_tries(env: dict) -> None:
    """Six 5xx responses wait 2, 4, 8, 16, 32 s and then raise."""
    env["responses"] = [FakeResponse(503) for _ in range(6)]
    with pytest.raises(requests.HTTPError):
        http.fetch("GET", "https://x/y")
    assert env["sleeps"] == [2.0, 4.0, 8.0, 16.0, 32.0]
    assert env["calls"] == 6
    assert not list(http.RAW_DIR.glob("*.json"))


def test_retry_after_header_is_honoured(env: dict) -> None:
    """A longer Retry-After header overrides the backoff."""
    env["responses"] = [FakeResponse(429, headers={"Retry-After": "10"}), FakeResponse(200, "ok")]
    http.fetch("GET", "https://x/y")
    assert env["sleeps"] == [10.0]


def test_404_only_returned_when_allowed(env: dict) -> None:
    """404 is cached and returned with allow_404, otherwise it raises."""
    env["responses"] = [FakeResponse(404, "nf"), FakeResponse(404, "nf")]
    with pytest.raises(requests.HTTPError):
        http.fetch("GET", "https://x/a")
    assert http.fetch("GET", "https://x/b", allow_404=True) == (404, "nf")
    assert env["sleeps"] == []


def test_before_request_runs_before_every_try(env: dict) -> None:
    """The before_request hook runs once per network attempt."""
    hooks: list[int] = []
    env["responses"] = [FakeResponse(500), FakeResponse(200, "ok")]
    http.fetch("GET", "https://x/y", before_request=lambda: hooks.append(1))
    assert len(hooks) == 2
