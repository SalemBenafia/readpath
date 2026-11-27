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


def test_graph_view_and_focus(app: AppTest) -> None:
    """The graph renders under the path, and the focus selectbox changes the why line."""
    app.text_input[0].input("Paper T").run()
    app.radio(key="target").set_value("T").run()
    focus = app.selectbox(key="focus")
    assert focus.value == "E"  # step 1 by default
    assert any("Citation graph" in h.value for h in app.subheader)
    focus.set_value("F").run()
    assert not app.exception
    assert "**Why Paper F:** Your paper cites it directly. Reached by 3 citation routes." in markdown(app)


def test_link_opens_reading_path(app: AppTest) -> None:
    """A fresh visit to ?paper=<id> fills the search box with the title and opens that path."""
    visit = AppTest.from_file(APP, default_timeout=30)
    visit.query_params["paper"] = "T"
    visit.run()
    assert visit.text_input(key="search").value == "Paper T"
    assert visit.radio(key="target").value == "T"
    assert card_titles(visit)[0].startswith("#### 1. [Paper E]")


def test_start_here_suggestions_open_a_path(app: AppTest) -> None:
    """With an empty search box, one click on a suggested paper shows its reading path."""
    buttons = [b for b in app.button if b.key and b.key.startswith("start-")]
    assert [b.label for b in buttons][0] == "Paper T (2020)"  # the seed comes first
    buttons[0].click().run()
    assert not app.exception
    assert app.text_input(key="search").value == "Paper T"
    assert app.radio(key="target").value == "T"
    assert card_titles(app)[0].startswith("#### 1. [Paper E]")
    assert app.query_params["paper"] == "T"


def test_candidates_say_whether_they_have_a_path(app: AppTest) -> None:
    """Search results show how many pack papers each one cites, or that it has no path."""
    app.text_input[0].input("Paper").run()
    labels = app.radio(key="target").options
    assert labels[0] == "Paper A (2015) · cited by 10 · cites 2 papers in this pack"  # A cites F and D
    assert any(o.endswith("cites 1 paper in this pack") for o in labels)  # B cites only F
    assert any("no reading path in this pack" in o for o in labels)  # E cites nothing
    has_path = ["no reading path" not in o for o in labels]
    assert has_path == sorted(has_path, reverse=True)  # papers with a path are listed first


def test_unknown_search_is_friendly(app: AppTest) -> None:
    """Text that matches nothing explains what to try, with an example title from the pack."""
    app.text_input[0].input("zzzz qqqq").run()
    message = next(i.value for i in app.info if "No paper in this pack matches" in i.value)
    assert "“zzzz qqqq”" in message and "*Paper T*" in message and "6 papers" in message
    assert not app.main.radio  # no paper to pick (the sidebar's depth radio does not count)


def test_paper_without_citations_in_pack(app: AppTest) -> None:
    """E cites nothing inside the pack: say so kindly, show the paper, and no graph."""
    app.text_input[0].input("Paper E").run()
    app.radio(key="target").set_value("E").run()
    assert not app.exception
    message = next(i.value for i in app.info if "no reading path for it here" in i.value)
    assert "two citation steps back" in message and "*Paper T*" in message  # names the seed
    assert card_titles(app) == ["#### 1. [Paper E](https://www.semanticscholar.org/paper/E) — your paper"]
    assert not any("Citation graph" in h.value for h in app.subheader)
    assert any(b.key and b.key.startswith("empty-") for b in app.button)  # suggestions to move on


def test_everything_already_read(app: AppTest) -> None:
    """When every earlier paper is marked as read, celebrate instead of saying "no citations"."""
    app.text_input[0].input("Paper T").run()
    app.radio(key="target").set_value("T").run()
    for pid in ("E", "F", "D", "A", "B"):
        app.button(key=f"read-{pid}").click().run()
    assert any("already read every earlier paper" in s.value for s in app.success)
    assert not any("does not cite" in i.value for i in app.info)


def test_empty_reading_list_message(app: AppTest) -> None:
    """An empty "Already read" list explains what Mark as read does."""
    assert any("Nothing here yet" in c.value and "Mark as read" in c.value for c in app.sidebar.caption)


def test_how_it_works_and_footer(app: AppTest) -> None:
    """The explainer lists the graph model, and the footer credits sources with the pack date."""
    assert app.expander[0].label == "How ReadPath works"
    explainer = "\n".join(m.value for m in app.expander[0].markdown)
    for part in ("[:CITES]", "[:BY]", "[:ABOUT {primary}]", "Hybrid search", "Citation paths", "Reading order"):
        assert part in explainer
    footer = app.main.caption[-1].value
    assert "Citation data: [Semantic Scholar]" in footer and "Abstracts: [arXiv](https://arxiv.org/) (CC0)" in footer
    assert "Graph: Relate by Neo4j." in footer and "Pack “paths” built 2026-11-25." in footer
