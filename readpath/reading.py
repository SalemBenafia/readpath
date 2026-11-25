"""Reading progress ("already read" papers), kept in a JSON file outside the packs."""

import json
from pathlib import Path
from typing import Any

READING_FILE = Path(__file__).resolve().parent.parent / "data" / "my_reading.json"

Item = dict[str, Any]


def load(path: Path = READING_FILE) -> list[Item]:
    """Return the saved reading list, or [] if the file is missing or unreadable."""
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    if not isinstance(data, list):
        return []
    return [_item(x) for x in data if isinstance(x, dict) and x.get("id")]


def save(items: list[Item], path: Path = READING_FILE) -> None:
    """Write the reading list as JSON, creating the folder if needed."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(items, ensure_ascii=False, indent=1), encoding="utf-8")


def _item(paper: Item) -> Item:
    """Keep only id, title and year of a paper."""
    return {"id": paper["id"], "title": paper.get("title") or "", "year": paper.get("year")}


def add(items: list[Item], paper: Item) -> list[Item]:
    """Return a new list with paper appended, unless it is already there."""
    if any(x["id"] == paper["id"] for x in items):
        return list(items)
    return [*items, _item(paper)]


def remove(items: list[Item], paper_id: str) -> list[Item]:
    """Return a new list without the paper with paper_id."""
    return [x for x in items if x["id"] != paper_id]


def ids(items: list[Item]) -> tuple[str, ...]:
    """Return the ids in the list as a sorted tuple (stable and hashable for caching)."""
    return tuple(sorted(x["id"] for x in items))
