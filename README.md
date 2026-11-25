# ReadPath

Give it any research paper and get the 5-7 earlier papers to read first, in order, with the citation chain that explains why each one matters.

Built on [Relate](https://relatedb.ai), the embedded graph database, for the Relate by Neo4j Hackathon.

## Quick start

Needs Python 3.10+ and `make`. Everything is free: no account, no API key.

```bash
make setup    # creates .venv, installs CPU-only torch, then requirements.txt
make test     # runs the test suite (no network needed)
```

Use `make setup` rather than `pip install -r requirements.txt` on its own: the Makefile installs the
small CPU-only build of torch first, instead of the multi-GB CUDA build.

Ask for a reading path in the ready-made `transformers` pack:

```bash
.venv/bin/python -m readpath path "Attention Is All You Need" --pack transformers
.venv/bin/python -m readpath path "Attention Is All You Need" --pack transformers --depth 2 --size 5
.venv/bin/python -m readpath find "self-attention for machine translation" --pack transformers
```

`path` takes an exact title, a Semantic Scholar paperId, or any words (then the best hybrid-search
match is used). `--read id1,id2` skips papers you have already read.

## Works with no API key

- The packs in `data/packs/*.rl` are committed, so nothing is downloaded to use them.
- The embedding model (all-MiniLM-L6-v2) is downloaded once on first use. Without internet,
  search falls back to full-text only, and exact titles still work.

## Ask Claude Code about the pack (MCP)

The repo's `.mcp.json` registers a `readpath` MCP server. It runs
`relate serve --mcp stdio` on `data/packs/transformers.rl`, read-only.
To use it, have `relate` on your PATH and start `claude` in the repo folder. Approve the
"readpath" project server when Claude Code asks, then type `/mcp` to check that it is
connected. The server has two tools, `get_schema` and `read_cypher`, and it cannot write.

## Rebuilding or adding a pack

```bash
.venv/bin/python build_pack.py --name transformers --seed "Attention Is All You Need" --max-papers 800
```

This calls the Semantic Scholar and arXiv APIs (free, no account; every response is cached in
`data/raw/`). An optional free Semantic Scholar key in `.env` as `S2_API_KEY=...` gives a higher rate
limit. Rebuilding needs the `relate` CLI for the final `relate clone`.

## Credits

- Paper metadata and citation links: [Semantic Scholar](https://www.semanticscholar.org/)
  (Semantic Scholar Academic Graph API, Allen Institute for AI).
- Abstracts and categories: [arXiv](https://arxiv.org/) (metadata is CC0). Thank you to arXiv for use
  of its open access interoperability. Abstracts come only from arXiv.
- Embeddings: [sentence-transformers](https://www.sbert.net/) all-MiniLM-L6-v2.
