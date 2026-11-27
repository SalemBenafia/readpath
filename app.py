"""Streamlit app for exploring ReadPath reading paths."""

import os
import re
from pathlib import Path
from typing import Any

import streamlit as st
from streamlit_agraph import Config, Edge, Node, agraph

from readpath import graph, path, reading, search, store

GRAPH_WIDTH = 1150
GRAPH_HEIGHT = 620
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


@st.cache_data(show_spinner=False)
def load_suggestions(pack_file: str, mtime: float) -> list[Row]:
    """Return the "start here" papers of a pack: seeds, then famous papers with a rich path."""
    conn = store.open_store(pack_file, read_only=True)
    try:
        return path.suggested_papers(conn, limit=6)
    finally:
        conn.close()


@st.cache_data(show_spinner=False)
def load_title(pack_file: str, mtime: float, paper_id: str) -> str:
    """Return a paper's title (used to fill the search box from a ?paper= link), or ""."""
    conn = store.open_store(pack_file, read_only=True)
    try:
        found = path.paper(conn, paper_id)
        return found["title"] if found else ""
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


@st.cache_data(show_spinner=False)
def load_graph_links(pack_file: str, mtime: float, ids: tuple[str, ...], step_ids: tuple[str, ...]) -> Row:
    """Return CITES edges among the shown papers and the top authors of the path steps."""
    conn = store.open_store(pack_file, read_only=True)
    try:
        return {
            "cites": path.edges_among(conn, ids),
            "authors": path.author_links(conn, step_ids, limit=graph.MAX_AUTHORS),
        }
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


def graph_config() -> Config:
    """Left-to-right hierarchical layout: authors, then papers by year (oldest left), then the target."""
    return Config(
        width=GRAPH_WIDTH, height=GRAPH_HEIGHT, directed=True, physics=False, hierarchical=True,
        direction="LR", sortMethod="directed", levelSeparation=260, nodeSpacing=90, treeSpacing=120,
        blockShifting=True, edgeMinimization=True, parentCentralization=False,
        interaction={"hover": True, "tooltipDelay": 120, "navigationButtons": False},
        edges={"arrows": {"to": {"enabled": True, "scaleFactor": 0.6}},
               "smooth": {"type": "cubicBezier", "forceDirection": "horizontal", "roundness": 0.4}},
    )


def show_graph(result: Row, pack_file: Path, mtime: float) -> None:
    """Show the path as a graph, highlighting the chosen paper's citation chains."""
    steps = result["steps"]
    if not steps:
        return
    st.subheader("Citation graph")
    numbers = {s["id"]: i for i, s in enumerate(steps, start=1)}
    titles = {s["id"]: s["title"] for s in steps}
    focus = st.selectbox("Show why for...", list(numbers), key="focus",
                         format_func=lambda pid: f"{numbers[pid]}. {titles[pid]}")
    shown = tuple(sorted(p["id"] for p in graph.paper_nodes(result, focus)))
    links = load_graph_links(str(pack_file), mtime, shown, tuple(numbers))
    data = graph.build_graph(result, focus, links["cites"], links["authors"])
    st.caption(
        "Navy: your paper · teal: papers to read (numbered) · light teal: papers on the chain · "
        "orange: authors · arrows point from a paper to what it cites; columns run oldest → newest. "
        "Hover a node for its full title."
    )
    agraph(nodes=[Node(**n) for n in data["nodes"]], edges=[Edge(**e) for e in data["edges"]],
           config=graph_config())
    focus_step = steps[numbers[focus] - 1]
    st.markdown(f"**Why {md(focus_step['title'])}:** {md(focus_step['why'])}")


def show_path(result: Row, pack_file: Path, mtime: float, read_all: bool, info: Row) -> None:
    """Show the numbered reading path, the graph, then authors and topics."""
    steps = result["steps"]
    if not steps:
        no_steps(result, read_all, info)
        target_card(1, result["target"])
        return
    st.subheader(f"Read these {len(steps)} papers first, in this order")
    for i, step in enumerate(steps, start=1):
        step_card(i, step)
    target_card(len(steps) + 1, result["target"])
    show_graph(result, pack_file, mtime)
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


def sidebar() -> tuple[Path, int, int, Row]:
    """Show pack choice, path settings and the reading list; return (pack file, size, depth, info)."""
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
        st.sidebar.caption(
            "Nothing here yet. Already know a paper in your path? Click **Mark as read** on it and "
            "ReadPath will skip it and suggest the next one."
        )
    for item in items:
        text_col, button_col = st.sidebar.columns([5, 1])
        text_col.caption(label(item))
        button_col.button("✕", key=f"unread-{item['id']}", on_click=mark_unread, args=(item["id"],),
                          help="Remove from already read")
    if items:
        st.sidebar.button("Clear all", on_click=clear_read)
    return pack_file, size, depth, info


HOW_IT_WORKS = """
**The graph** (one Relate file per topic pack, opened read-only):
- `(:Paper)` — title, year, arXiv abstract, citation count and a 384-number embedding of title + abstract
- `(:Paper)-[:CITES]->(:Paper)` — citation links, kept only when both papers are in the pack
- `(:Paper)-[:BY]->(:Author)` — who wrote each paper
- `(:Paper)-[:ABOUT {primary}]->(:Topic)` — arXiv categories such as `cs.CL`

**Hybrid search.** Your words are matched by meaning (a vector index over the embeddings) and by
exact words (a full-text index), and the two rankings are merged with reciprocal rank fusion;
an exact title always comes first.

**Citation paths.** ReadPath follows `CITES` links 2 or 3 hops back from your paper and ranks
the earlier papers by how many citation routes lead to them.

**Reading order.** The chosen papers are sorted so each one comes after the papers it cites
(a topological sort), with older papers first when they are not linked.
"""


def how_it_works() -> None:
    """Explain the graph model, hybrid search, citation paths and reading order."""
    with st.expander("How ReadPath works"):
        st.markdown(HOW_IT_WORKS)


def built_date(info: Row) -> str:
    """Return the pack's build date as YYYY-MM-DD, or "unknown"."""
    return (info.get("built_at") or "unknown")[:10]


def footer(info: Row) -> None:
    """Credit the data sources (required by the Semantic Scholar API licence) and the pack date."""
    st.divider()
    st.caption(
        "Citation data: [Semantic Scholar](https://www.semanticscholar.org/). "
        "Abstracts: [arXiv](https://arxiv.org/) (CC0). Graph: Relate by Neo4j. "
        f"Pack “{info.get('name') or '?'}” built {built_date(info)}."
    )


def no_results(text: str, info: Row) -> None:
    """Explain that nothing matched and suggest what to try."""
    example = (info.get("seed_titles") or ["a title from this pack"])[0]
    st.info(
        f"No paper in this pack matches “{md(text)}”. Try a few words from the title or abstract, "
        f"the exact title (for example *{md(example)}*), or a Semantic Scholar paperId. "
        f"This pack has {info.get('papers', 0)} papers; other topics need their own pack."
    )


def choose(paper: Row) -> None:
    """Open a paper's reading path: fill the search box, select it, and update the URL."""
    st.session_state.search = paper["title"]
    st.session_state.pop("target", None)  # let the radio pick the linked paper fresh
    st.query_params["paper"] = paper["id"]


def suggestions(pack_file: Path, mtime: float, key: str) -> None:
    """Show one-click "start here" papers that have a full reading path in this pack."""
    papers = load_suggestions(str(pack_file), mtime)
    if not papers:
        return
    st.markdown("**Start here:** papers with a full reading path in this pack (one click):")
    for col, p in zip(st.columns(3) * 2, papers):
        col.button(label(p), key=f"{key}-{p['id']}", on_click=choose, args=(p,),
                   help=f"Cites {p['cites']} papers in this pack", width="stretch")


def candidate_label(c: Row) -> str:
    """Radio label: title, year, citations, and whether it has a reading path in this pack."""
    cites = c.get("cites") or 0
    path_note = (f"cites {cites} paper{'s' if cites != 1 else ''} in this pack" if cites
                 else "no reading path in this pack")
    return f"{label(c)} · cited by {c.get('cited_by') or 0:,} · {path_note}"


def no_steps(result: Row, read_all: bool, info: Row) -> None:
    """Explain an empty reading path: everything is read, or the paper's references are outside the pack."""
    title = md(result["target"]["title"])
    if read_all:
        st.success(f"You have already read every earlier paper ReadPath found for *{title}*. "
                   "Remove some from “Already read” in the sidebar to see them again.")
    else:
        seeds = "; ".join(md(s) for s in info.get("seed_titles") or []) or "its seed papers"
        st.info(f"None of the papers that *{title}* cites are in this pack, so there is no reading "
                f"path for it here. A pack only reaches two citation steps back from its seed papers "
                f"(*{seeds}*), so its oldest papers are the end of the line. Pick one of the papers "
                "below, or a newer paper.")


def main() -> None:
    """Render the ReadPath page."""
    st.set_page_config(page_title="ReadPath", layout="wide")
    pack_file, size, depth, info = sidebar()
    mtime = pack_file.stat().st_mtime
    st.title("ReadPath")
    st.caption("Find the earlier papers to read first, in order, and why each one matters.")
    how_it_works()
    model_ok = get_embedder().available
    if not model_ok:
        st.info("Embedding model not available – using full-text search only.", icon="ℹ️")
    linked = st.query_params.get("paper", "")  # ?paper=<paperId> opens that paper's path directly
    if "search" not in st.session_state:  # first visit: a ?paper= link fills in the title
        st.session_state.search = (load_title(str(pack_file), mtime, linked) or linked) if linked else ""
    text = st.text_input("Which paper do you want to understand?", key="search",
                         placeholder="e.g. Attention Is All You Need")
    if not text.strip():
        suggestions(pack_file, mtime, key="start")
    else:
        found = load_candidates(str(pack_file), mtime, text.strip(), model_ok)
        if not found:
            no_results(text.strip(), info)
            suggestions(pack_file, mtime, key="none")
        else:
            by_id = {c["id"]: c for c in found}
            target_id = st.radio(
                "Pick the paper:", list(by_id), index=0 if linked in by_id else None, key="target",
                format_func=lambda pid: candidate_label(by_id[pid]),
            )
            if target_id:
                st.query_params["paper"] = target_id  # the URL now links to this reading path
                already = reading.ids(reading_list())
                result = load_reading_path(str(pack_file), mtime, target_id, size, depth, already)
                read_all = bool(already) and not result["steps"] and bool(
                    load_reading_path(str(pack_file), mtime, target_id, size, depth, ())["steps"])
                show_path(result, pack_file, mtime, read_all, info)
                if not result["steps"] and not read_all:
                    suggestions(pack_file, mtime, key="empty")
    footer(info)


main()
