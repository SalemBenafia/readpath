"""Streamlit app for exploring ReadPath reading paths."""

import os
import re
from pathlib import Path
from typing import Any

import streamlit as st

from readpath import path, reading, search, store

PACKS_DIR = Path(os.environ.get("READPATH_PACKS_DIR") or store.PACKS_DIR)
READING_FILE = Path(os.environ.get("READPATH_READING_FILE") or reading.READING_FILE)
S2_URL = "https://www.semanticscholar.org/paper/{}"
ARXIV_URL = "https://arxiv.org/abs/{}"
DOI_URL = "https://doi.org/{}"

Row = dict[str, Any]


# ---------- data (each call opens its own read-only connection; results are cached) ----------


@st.cache_resource(show_spinner="Loading the embedding model…")
def get_embedder() -> search.Embedder:
    """Return the shared embedding model, loaded once per server process."""
    embedder = search.Embedder()
    embedder.load()
    return embedder


@st.cache_data(show_spinner=False)
def load_pack_summary(pack_file: str, mtime: float) -> Row:
    """Return the pack's name, seeds and paper count (mtime invalidates after a rebuild)."""
    conn = store.open_store(pack_file, read_only=True)
    try:
        return store.pack_summary(conn)
    finally:
        conn.close()


@st.cache_data(show_spinner="Searching…")
def load_candidates(pack_file: str, mtime: float, text: str, model_ok: bool) -> list[Row]:
    """Return up to 5 candidate papers for the search text."""
    conn = store.open_store(pack_file, read_only=True)
    try:
        return path.find_candidates(conn, text, k=5, embedder=get_embedder())
    finally:
        conn.close()


@st.cache_data(show_spinner="Building the reading path…")
def load_reading_path(
    pack_file: str, mtime: float, target_id: str, size: int, depth: int, already_read: tuple[str, ...]
) -> Row:
    """Return the reading path for a target paper."""
    conn = store.open_store(pack_file, read_only=True)
    try:
        return path.reading_path(conn, target_id, size=size, depth=depth, already_read=already_read)
    finally:
        conn.close()


# ---------- reading progress (outside the pack) ----------


def reading_list() -> list[Row]:
    """Return the "already read" list, loading it from disk on first use in this session."""
    if "reading" not in st.session_state:
        st.session_state.reading = reading.load(READING_FILE)
    return st.session_state.reading


def mark_read(paper: Row) -> None:
    """Add a paper to the reading list and save it."""
    st.session_state.reading = reading.add(reading_list(), paper)
    reading.save(st.session_state.reading, READING_FILE)


def mark_unread(paper_id: str) -> None:
    """Remove a paper from the reading list and save it."""
    st.session_state.reading = reading.remove(reading_list(), paper_id)
    reading.save(st.session_state.reading, READING_FILE)


def clear_read() -> None:
    """Empty the reading list and save it."""
    st.session_state.reading = []
    reading.save([], READING_FILE)


# ---------- rendering helpers ----------


def md(text: str) -> str:
    """Escape characters that Markdown would interpret inside a title."""
    return re.sub(r"([\\`*_\[\]<>#|])", r"\\\1", text or "")


def label(p: Row) -> str:
    """Short "Title (year)" label for a paper."""
    return f"{p.get('title') or 'Untitled'} ({p.get('year') or 'n.d.'})"


def links(p: Row) -> None:
    """Show link buttons to Semantic Scholar, arXiv and the DOI when available."""
    targets = [("Semantic Scholar", S2_URL.format(p["id"]))]
    if p.get("arxiv"):
        targets.append(("arXiv", ARXIV_URL.format(p["arxiv"])))
    if p.get("doi"):
        targets.append(("DOI", DOI_URL.format(p["doi"])))
    for col, (name, url) in zip(st.columns(4), targets):
        col.link_button(name, url, key=f"link-{name}-{p['id']}", width="stretch")


def chain_text(chain: list[Row]) -> str:
    """Render one citation chain as "Title (year) → … → Title (year)"."""
    return " → ".join(md(label(n)) for n in chain)


def step_card(number: int, step: Row) -> None:
    """Show one paper of the reading path as a numbered card."""
    with st.container(border=True):
        st.markdown(f"#### {number}. [{md(step['title'])}]({S2_URL.format(step['id'])})")
        st.caption(
            f"{step.get('year') or 'n.d.'} · cited by {step.get('cited_by') or 0:,} · "
            f"{step['routes']} citation route{'s' if step['routes'] != 1 else ''} from your paper"
        )
        st.write(step["why"])
        links(step)
        st.button("Mark as read", key=f"read-{step['id']}", on_click=mark_read, args=(step,))
        with st.expander("Citation chain(s)"):
            for chain in step["chains"]:
                st.markdown("- " + chain_text(chain))


def target_card(number: int, target: Row) -> None:
    """Show the target paper as the last card."""
    with st.container(border=True):
        st.markdown(f"#### {number}. [{md(target['title'])}]({S2_URL.format(target['id'])}) — your paper")
        st.caption(f"{target.get('year') or 'n.d.'} · cited by {target.get('cited_by') or 0:,}")
        links(target)


def show_path(result: Row) -> None:
    """Show the numbered reading path, then authors and topics."""
    steps = result["steps"]
    if not steps:
        st.info("No earlier papers in this pack lead here (or you have read them all).")
    else:
        st.subheader(f"Read these {len(steps)} papers first, in this order")
    for i, step in enumerate(steps, start=1):
        step_card(i, step)
    target_card(len(steps) + 1, result["target"])
    authors_col, topics_col = st.columns(2)
    with authors_col:
        st.subheader("Authors to follow")
        for a in result["authors"] or []:
            st.markdown(f"- {md(a['author'])} · {a['papers']} paper{'s' if a['papers'] != 1 else ''} in this path")
    with topics_col:
        st.subheader("Topics in this path")
        for t in result["topics"] or []:
            st.markdown(f"- `{t['topic']}` · score {t['score']:g} ({t['papers']} papers)")


# ---------- page ----------


def sidebar() -> tuple[Path, int, int]:
    """Show pack choice, path settings and the reading list; return (pack file, size, depth)."""
    st.sidebar.title("ReadPath")
    packs = store.list_packs(PACKS_DIR)
    if not packs:
        st.sidebar.error("No packs found in data/packs/. Build one with build_pack.py.")
        st.stop()
    name = st.sidebar.selectbox("Pack", packs)
    pack_file = store.pack_path(name, PACKS_DIR)
    info = load_pack_summary(str(pack_file), pack_file.stat().st_mtime)
    seeds = "; ".join(info["seed_titles"]) or "-"
    st.sidebar.caption(f"{info['papers']} papers · seeds: {seeds}")
    size = st.sidebar.slider("papers in path", 3, 10, 6)
    depth = st.sidebar.radio("depth", [2, 3], index=1, horizontal=True,
                             help="How many citation hops to follow from your paper.")
    st.sidebar.subheader("Already read")
    items = reading_list()
    if not items:
        st.sidebar.caption("Nothing yet. Use “Mark as read” on a paper.")
    for item in items:
        text_col, button_col = st.sidebar.columns([5, 1])
        text_col.caption(label(item))
        button_col.button("✕", key=f"unread-{item['id']}", on_click=mark_unread, args=(item["id"],),
                          help="Remove from already read")
    if items:
        st.sidebar.button("Clear all", on_click=clear_read)
    return pack_file, size, depth


def footer() -> None:
    """Credit the data sources (required by the Semantic Scholar API licence)."""
    st.divider()
    st.caption(
        "Data: [Semantic Scholar](https://www.semanticscholar.org/) (Semantic Scholar Academic Graph API) "
        "and [arXiv](https://arxiv.org/) (metadata CC0; thank you to arXiv for use of its open access "
        "interoperability). Built with Relate."
    )


def main() -> None:
    """Render the ReadPath page."""
    st.set_page_config(page_title="ReadPath", layout="wide")
    pack_file, size, depth = sidebar()
    mtime = pack_file.stat().st_mtime
    st.title("ReadPath")
    st.caption("Find the earlier papers to read first, in order, and why each one matters.")
    model_ok = get_embedder().available
    if not model_ok:
        st.info("Embedding model not available – using full-text search only.", icon="ℹ️")
    text = st.text_input("Which paper do you want to understand?",
                         placeholder="e.g. Attention Is All You Need")
    if text.strip():
        found = load_candidates(str(pack_file), mtime, text.strip(), model_ok)
        if not found:
            st.warning("No matching paper in this pack.")
        else:
            by_id = {c["id"]: c for c in found}
            target_id = st.radio(
                "Pick the paper:", list(by_id), index=None, key="target",
                format_func=lambda pid: f"{label(by_id[pid])} · cited by {by_id[pid].get('cited_by') or 0:,}",
            )
            if target_id:
                already = reading.ids(reading_list())
                show_path(load_reading_path(str(pack_file), mtime, target_id, size, depth, already))
    footer()


main()
