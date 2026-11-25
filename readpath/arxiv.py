"""arXiv API client for abstracts and categories, cached in data/raw/."""

import re
import time
import xml.etree.ElementTree as ET
from typing import Any
from urllib.parse import urlencode

from readpath import http

API = "https://export.arxiv.org/api/query"
BATCH_SIZE = 100
MIN_INTERVAL = 3.0
NS = {"atom": "http://www.w3.org/2005/Atom", "arxiv": "http://arxiv.org/schemas/atom"}

_last_call = 0.0


def strip_version(arxiv_id: str) -> str:
    """Remove a trailing version suffix such as "v7" from an arXiv id."""
    return re.sub(r"v\d+$", "", arxiv_id.strip())


def _throttle() -> None:
    """Sleep so that real arXiv requests are at least MIN_INTERVAL seconds apart."""
    global _last_call
    wait = _last_call + MIN_INTERVAL - time.monotonic()
    if wait > 0:
        time.sleep(wait)
    _last_call = time.monotonic()


def _collapse(text: str | None) -> str:
    """Collapse all runs of whitespace into single spaces."""
    return " ".join((text or "").split())


def parse_feed(xml_text: str) -> dict[str, dict[str, Any]]:
    """Parse an arXiv Atom feed into {arxiv_id: {abstract, primary_category, categories}}."""
    root = ET.fromstring(xml_text)
    result: dict[str, dict[str, Any]] = {}
    for entry in root.findall("atom:entry", NS):
        raw_id = entry.findtext("atom:id", default="", namespaces=NS)
        if "/abs/" not in raw_id:
            continue
        primary = entry.find("arxiv:primary_category", NS)
        result[strip_version(raw_id.split("/abs/", 1)[1])] = {
            "abstract": _collapse(entry.findtext("atom:summary", namespaces=NS)),
            "primary_category": primary.get("term") if primary is not None else None,
            "categories": [c.get("term") for c in entry.findall("atom:category", NS)],
        }
    return result


def get_metadata(arxiv_ids: list[str]) -> dict[str, dict[str, Any]]:
    """Return abstract and categories for each arXiv id (versions are ignored)."""
    ids = list(dict.fromkeys(strip_version(i) for i in arxiv_ids if i))
    metadata: dict[str, dict[str, Any]] = {}
    for start in range(0, len(ids), BATCH_SIZE):
        chunk = ids[start : start + BATCH_SIZE]
        url = f"{API}?{urlencode({'id_list': ','.join(chunk), 'max_results': len(chunk)})}"
        _, text = http.fetch("GET", url, before_request=_throttle)
        metadata.update(parse_feed(text))
    return metadata
