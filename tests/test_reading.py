"""Tests for readpath.reading: the "already read" list stored outside the packs."""

from pathlib import Path

from readpath import reading


def test_missing_or_corrupt_file_loads_empty(tmp_path: Path) -> None:
    """A missing, broken or wrongly shaped file gives an empty list."""
    assert reading.load(tmp_path / "nope.json") == []
    (tmp_path / "bad.json").write_text("{not json")
    assert reading.load(tmp_path / "bad.json") == []
    (tmp_path / "dict.json").write_text('{"id": "x"}')
    assert reading.load(tmp_path / "dict.json") == []


def test_save_and_load_round_trip(tmp_path: Path) -> None:
    """Saved items load back, keeping only id, title and year; folders are created."""
    target = tmp_path / "sub" / "my_reading.json"
    reading.save([{"id": "a", "title": "A", "year": 2001}], target)
    raw = '[{"id": "a", "title": "A", "year": 2001, "extra": 1}, {"title": "no id"}]'
    assert reading.load(target) == [{"id": "a", "title": "A", "year": 2001}]
    target.write_text(raw)
    assert reading.load(target) == [{"id": "a", "title": "A", "year": 2001}]


def test_add_dedupes_and_remove() -> None:
    """add() ignores duplicates and trims fields; remove() drops by id; ids() is sorted."""
    items = reading.add([], {"id": "b", "title": "B", "year": 2002, "routes": 9})
    items = reading.add(items, {"id": "a", "title": "A", "year": None})
    assert reading.add(items, {"id": "b", "title": "B again"}) == items
    assert items[0] == {"id": "b", "title": "B", "year": 2002}
    assert reading.ids(items) == ("a", "b")
    assert reading.remove(items, "b") == [{"id": "a", "title": "A", "year": None}]
