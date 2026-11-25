"""End-to-end test of app.py with Streamlit's AppTest on the obvious-answer path pack (no model)."""

import json
from pathlib import Path

import pytest
import streamlit as st
from streamlit.testing.v1 import AppTest

from readpath import search

APP = str(Path(__file__).resolve().parent.parent / "app.py")


@pytest.fixture
def app(path_store_path: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> AppTest:
    """The app pointed at the path pack and a temp reading file, with no embedding model."""
    monkeypatch.setenv("READPATH_PACKS_DIR", str(path_store_path.parent))
    monkeypatch.setenv("READPATH_READING_FILE", str(tmp_path / "my_reading.json"))

    def no_model(self: search.Embedder) -> bool:
        """Simulate a model that cannot be loaded (e.g. offline first run)."""
        self.available = False
        return False

    monkeypatch.setattr(search.Embedder, "load", no_model)
    monkeypatch.setattr(search.Embedder, "encode", lambda self, text: None)
    st.cache_data.clear()
    st.cache_resource.clear()
    at = AppTest.from_file(APP, default_timeout=30)
    at.run()
    return at


def markdown(at: AppTest) -> str:
    """All markdown text on the page, joined."""
    return "\n".join(m.value for m in at.markdown)


def card_titles(at: AppTest) -> list[str]:
    """The numbered card headings, in order."""
    return [m.value for m in at.markdown if m.value.startswith("#### ")]


def test_start_page(app: AppTest) -> None:
    """The page loads with pack info, settings, the no-model notice and the credit footer."""
    assert not app.exception
    assert any("6 papers" in c.value and "Paper T" in c.value for c in app.sidebar.caption)
    assert app.sidebar.slider[0].value == 6
    assert app.sidebar.radio[0].value == 3
    assert any("full-text search only" in i.value for i in app.info)
    assert any("Semantic Scholar" in c.value and "arXiv" in c.value for c in app.caption)


def test_search_pick_and_reading_path(app: AppTest) -> None:
    """Searching an exact title lists it first; picking it shows cards in reading order."""
    app.text_input[0].input("Paper T").run()
    radio = app.radio(key="target")
    assert radio.options[0].startswith("Paper T (2020)")
    assert radio.value is None
    radio.set_value("T").run()
    assert not app.exception
    assert card_titles(app) == [
        "#### 1. [Paper E](https://www.semanticscholar.org/paper/E)",
        "#### 2. [Paper F](https://www.semanticscholar.org/paper/F)",
        "#### 3. [Paper D](https://www.semanticscholar.org/paper/D)",
        "#### 4. [Paper A](https://www.semanticscholar.org/paper/A)",
        "#### 5. [Paper B](https://www.semanticscholar.org/paper/B)",
        "#### 6. [Paper T](https://www.semanticscholar.org/paper/T) — your paper",
    ]
    text = markdown(app)
    assert "Your paper cites it directly. Reached by 3 citation routes." in text
    assert "Paper T (2020) → Paper A (2015) → Paper D (2012) → Paper E (2005)" in text
    assert "Ada · 2 papers in this path" in text
    assert "`cs.CL`" in text


def test_mark_as_read_updates_path_and_file(app: AppTest, tmp_path: Path) -> None:
    """Marking F as read removes it from the path and saves it outside the pack."""
    app.text_input[0].input("Paper T").run()
    app.radio(key="target").set_value("T").run()
    app.button(key="read-F").click().run()
    assert not app.exception
    assert all("Paper F" not in t for t in card_titles(app))
    saved = json.loads((tmp_path / "my_reading.json").read_text())
    assert saved == [{"id": "F", "title": "Paper F", "year": 2010}]
    assert any("Paper F (2010)" in c.value for c in app.sidebar.caption)
    app.button(key="unread-F").click().run()
    assert any("Paper F" in t for t in card_titles(app))
    assert json.loads((tmp_path / "my_reading.json").read_text()) == []


def test_depth_two_drops_three_hop_paper(app: AppTest) -> None:
    """Switching depth to 2 removes E, which is 3 citation hops away."""
    app.text_input[0].input("Paper T").run()
    app.radio(key="target").set_value("T").run()
    app.sidebar.radio[0].set_value(2).run()
    assert all("Paper E" not in t for t in card_titles(app))


def test_unknown_search(app: AppTest) -> None:
    """Text that matches nothing shows a warning instead of a radio."""
    app.text_input[0].input("zzzz qqqq").run()
    assert any("No matching paper" in w.value for w in app.warning)
