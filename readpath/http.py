"""Shared HTTP helper: disk cache in data/raw/ plus retries with exponential backoff."""

import hashlib
import json
import sys
import time
from collections.abc import Callable
from pathlib import Path

import requests

RAW_DIR = Path(__file__).resolve().parent.parent / "data" / "raw"
MAX_TRIES = 6
FIRST_WAIT = 2.0
TIMEOUT = 30
RETRY_STATUSES = {429} | set(range(500, 600))


def cache_key(method: str, url: str, body: bytes | None = None) -> str:
    """Return the sha1 cache key for a request (headers are never included)."""
    digest = hashlib.sha1()
    digest.update(f"{method.upper()}\n{url}\n".encode())
    digest.update(body or b"")
    return digest.hexdigest()


def _cache_path(key: str) -> Path:
    """Return the cache file path for a key."""
    return RAW_DIR / f"{key}.json"


def _read_cache(key: str) -> tuple[int, str] | None:
    """Return a cached (status, body) pair, or None if not cached."""
    path = _cache_path(key)
    if not path.exists():
        return None
    data = json.loads(path.read_text(encoding="utf-8"))
    return data["status"], data["body"]


def _write_cache(key: str, status: int, body: str) -> None:
    """Store a (status, body) pair in the cache."""
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    payload = json.dumps({"status": status, "body": body}, ensure_ascii=False)
    _cache_path(key).write_text(payload, encoding="utf-8")


def _wait_seconds(attempt: int, response: requests.Response | None) -> float:
    """Return the backoff for an attempt, honouring a longer Retry-After header."""
    wait = FIRST_WAIT * 2**attempt
    if response is not None:
        try:
            wait = max(wait, float(response.headers.get("Retry-After", 0)))
        except ValueError:
            pass
    return wait


def fetch(
    method: str,
    url: str,
    *,
    headers: dict[str, str] | None = None,
    body: bytes | None = None,
    allow_404: bool = False,
    before_request: Callable[[], None] | None = None,
) -> tuple[int, str]:
    """Return (status, text) for a request, from cache or the network with retries."""
    key = cache_key(method, url, body)
    cached = _read_cache(key)
    if cached is not None:
        return cached
    for attempt in range(MAX_TRIES):
        if before_request is not None:
            before_request()
        response: requests.Response | None = None
        try:
            response = requests.request(method, url, headers=headers, data=body, timeout=TIMEOUT)
        except (requests.ConnectionError, requests.Timeout) as exc:
            if attempt == MAX_TRIES - 1:
                raise
            reason = type(exc).__name__
        else:
            if response.status_code == 200 or (allow_404 and response.status_code == 404):
                _write_cache(key, response.status_code, response.text)
                return response.status_code, response.text
            if response.status_code not in RETRY_STATUSES or attempt == MAX_TRIES - 1:
                response.raise_for_status()
                raise requests.HTTPError(f"Unexpected status {response.status_code}", response=response)
            reason = f"HTTP {response.status_code}"
        wait = _wait_seconds(attempt, response)
        print(f"{method} {reason}, retrying in {wait:.0f}s", file=sys.stderr)
        time.sleep(wait)
    raise RuntimeError("unreachable")
