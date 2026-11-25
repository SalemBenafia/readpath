# ReadPath

ReadPath builds a reading path for any research paper: given a target paper, it finds the
5-7 earlier papers to read first, puts them in order, and explains WHY each one matters by
showing the citation chain. Built for the Relate by Neo4j Hackathon
(deadline: Fri 11 Dec 2026, 6 PM PST).

## Stack
- Python 3.10+ in a virtualenv at .venv (run `source .venv/bin/activate` first)
- Relate, the embedded graph database: Python package `relate-db` (import relate)
  and the `relate` CLI
- Free data, no account needed:
  - Semantic Scholar Graph API: papers, authors, years, citation links.
    Optional free key in .env as S2_API_KEY. Never read, print, log or commit .env.
  - arXiv API: abstracts and categories (metadata is CC0). Max 1 request every 3 seconds.
- sentence-transformers all-MiniLM-L6-v2 (384-dim embeddings, CPU only)
- networkx (reading order), Streamlit + streamlit-agraph (UI), pytest (tests)

## Layout
- readpath/s2.py        Semantic Scholar client + cache in data/raw/
- readpath/arxiv.py     arXiv client (abstracts, categories) + cache in data/raw/
- readpath/store.py     open stores, create schema, write packs
- readpath/queries.py   ALL Cypher statements live here as named constants
- readpath/search.py    vector + full-text search, reciprocal rank fusion
- readpath/path.py      foundations, citation chains, authors and topics
- readpath/order.py     reading order (topological sort, year tie-break)
- readpath/cli.py       `python -m readpath ...` commands
- build_pack.py         builds data/packs/<name>.rl from seed papers
- app.py                Streamlit app
- tests/                pytest tests (tiny fixture pack, no network)
- data/packs/*.rl       ready-made topic packs, COMMITTED (judges start here)

## Graph model
- (:Paper {id, title, year, abstract, citedBy, arxiv, doi, embedding})
  id = Semantic Scholar paperId (40 hex chars); arxiv = arXiv id like "1706.03762"
- (:Author {id, name}), (:Topic {id}) = arXiv category like "cs.CL",
  (:Pack {name, seeds, builtAt})
- (Paper)-[:CITES]->(Paper)   only between papers inside the pack
- (Paper)-[:BY]->(Author), (Paper)-[:ABOUT {primary}]->(Topic)

## Data rules
- Everything must stay free: no paid APIs, no paid services.
- Abstracts come ONLY from arXiv (CC0). Never request or store the Semantic Scholar
  abstract field. Papers without an arXiv id get an empty abstract (embed the title).
- Credit "Semantic Scholar" and "arXiv" in the README and the app footer
  (the Semantic Scholar API licence requires the credit).
- Cache every API response in data/raw/ so nothing is downloaded twice.

## Relate rules (Relate is NOT full Neo4j)
- No APOC and no GDS. Run algorithms in Python on query results.
- Variable-length paths need an upper bound, e.g. [:CITES*1..3].
  The bound cannot be a parameter: keep one constant per depth.
- Store embeddings as typed vectors: SET p.embedding = vector($emb, 384, FLOAT32)
- Vector search: MATCH (p:Paper)
  SEARCH p IN (VECTOR INDEX paper_embedding FOR $v LIMIT 10) SCORE AS score
- Full-text: SEARCH p IN (FULLTEXT INDEX paper_text FOR $q LIMIT 10) SCORE AS score
  (LIMIT is required inside SEARCH)
- Always pass values as parameters ($name). Never format values into Cypher strings.
- Only ONE process may write a store. The app and the MCP server open stores read-only.
  Stop them before rebuilding a pack.
- A connection belongs to the thread that opened it. In Streamlit, open a new read-only
  connection inside each data function; never cache connections.
- When unsure about syntax, use the installed Relate skill or run `relate agent-context`.

## Commands
- make setup   create .venv and install everything (CPU-only torch)
- make test    run pytest
- make run     start the Streamlit app
- python build_pack.py --name transformers --seed "Attention Is All You Need" --max-papers 800
- relate --database data/packs/transformers.rl --read-only 'MATCH (p:Paper) RETURN count(p)'

## Working rules
- Small steps. After each step: run `make test`, then commit with a clear message.
- Keep functions small, typed, with a one-line docstring.
- The app must work with NO API keys, using only the committed packs.
- After each completed step, add one line to docs/AI_USAGE.md:
  date - step - what Claude Code did - what I decided or checked.
