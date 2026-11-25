"""Semantic Scholar Graph API client with a response cache in data/raw/."""

import json
import os
from collections.abc import Iterable
from typing import Any
from urllib.parse import urlencode

from dotenv import load_dotenv

from readpath import http

BASE = "https://api.semanticscholar.org/graph/v1"
FIELDS = "paperId,externalIds,title,year,citationCount,authors,references.paperId"
BATCH_SIZE = 500
MAX_AUTHORS = 10

_env_loaded = False


def _headers() -> dict[str, str]:
    """Return request headers, with x-api-key only when S2_API_KEY is set."""
    global _env_loaded
    if not _env_loaded:
        load_dotenv()
        _env_loaded = True
    key = os.environ.get("S2_API_KEY", "").strip()
    return {"x-api-key": key} if key else {}


def _get(path: str, params: dict[str, Any], allow_404: bool = False) -> tuple[int, Any]:
    """GET a Graph API path and return (status, parsed JSON)."""
    url = f"{BASE}{path}?{urlencode(params)}"
    status, text = http.fetch("GET", url, headers=_headers(), allow_404=allow_404)
    return status, json.loads(text) if status == 200 else None


def match_title(title: str) -> dict[str, Any] | None:
    """Return the raw best title match, or None when Semantic Scholar finds none."""
    status, data = _get("/paper/search/match", {"query": title, "fields": FIELDS}, allow_404=True)
    if status == 404 or not data or not data.get("data"):
        return None
    return data["data"][0]


def search(query: str, limit: int = 5) -> list[dict[str, Any]]:
    """Return raw relevance-search results for a query."""
    _, data = _get("/paper/search", {"query": query, "limit": limit, "fields": FIELDS})
    return data.get("data") or []


def _chunks(items: list[str], size: int) -> Iterable[list[str]]:
    """Yield consecutive slices of at most size items."""
    for start in range(0, len(items), size):
        yield items[start : start + size]


def get_papers(ids: list[str]) -> list[dict[str, Any]]:
    """Return raw papers for ids via the batch endpoint, skipping unknown ids."""
    url = f"{BASE}/paper/batch?{urlencode({'fields': FIELDS})}"
    headers = {**_headers(), "Content-Type": "application/json"}
    papers: list[dict[str, Any]] = []
    for chunk in _chunks(list(ids), BATCH_SIZE):
        body = json.dumps({"ids": chunk}).encode()
        _, text = http.fetch("POST", url, headers=headers, body=body)
        papers.extend(p for p in json.loads(text) if p is not None)
    return papers


def simplify(p: dict[str, Any]) -> dict[str, Any]:
    """Reduce a raw Semantic Scholar paper to the fields ReadPath stores."""
    external = p.get("externalIds") or {}
    return {
        "id": p["paperId"],
        "title": p.get("title") or "",
        "year": p.get("year"),
        "cited_by": p.get("citationCount") or 0,
        "arxiv": external.get("ArXiv"),
        "doi": external.get("DOI"),
        "authors": [
            {"id": a.get("authorId"), "name": a.get("name")}
            for a in (p.get("authors") or [])[:MAX_AUTHORS]
        ],
        "references": [
            r["paperId"] for r in (p.get("references") or []) if r and r.get("paperId")
        ],
    }
