# AI Usage Log

ReadPath is built with help from Claude Code. Each completed step adds one line:
date - step - what Claude Code did - what I decided or checked.

- 2026-11-25 - Project skeleton - created package layout, Makefile, requirements, smoke test - reviewed plan
- 2026-11-25 - API clients - wrote Semantic Scholar + arXiv clients, shared cache/retry helper, fixture tests, `search` CLI - approved plan, checked live search output (survived five 429s)
- 2026-11-25 - Pack collection - wrote build_pack.py collection (seeds, 2 reference levels, in-pack edges, arXiv metadata) with pure ranking/edge functions and fake-data tests - approved plan, checked transformers dry-run summary (694 papers, 4204 edges)
- 2026-11-25 - Relate store - wrote store.py/queries.py (schema, one-transaction UNWIND writes) and the embed + write + `relate clone` path in build_pack.py, with a fake-pack .rl test - approved plan, checked counts with the relate CLI and committed data/packs/transformers.rl (5.0 MB)
- 2026-11-25 - Hybrid search - wrote search.py (lazy Embedder with full-text fallback, vector + full-text SEARCH, reciprocal rank fusion, query cleaning tested against real Relate syntax errors), conftest fixture pack and `find` CLI - checked "self-attention for machine translation" results and that the model loads offline from cache
- 2026-11-25 - Reading paths - wrote path.py (foundations, why-chains at depth 2/3, authors, topics, why_text, reading_path) with an obvious-answer fixture pack - timed foundations on the real pack (max 25 ms at depth 3, so depth 3 stays default) and checked the Attention reading path
- 2026-11-25 - Reading order + path CLI - wrote order.py (networkx lexicographical topological sort, year tie-break, cycle fallback, target last), EDGES_AMONG and the `path` CLI - caught that hybrid search picked the wrong target for an exact title (vector rank 20), so the CLI now tries an exact title match first; checked the Attention reading list
- 2026-11-25 - Review against CLAUDE.md - reviewed all code (Cypher formatting, threads, read-only, tests, docstrings, speed, no-key use) and fixed: README credits + judge quick start, pack rebuild that can no longer delete the old pack, tests for no-key/offline paths, shared path.find_paper, test Cypher moved to queries.py, docstrings/types in tests - approved the findings list, checked `path` runs in 0.41 s
