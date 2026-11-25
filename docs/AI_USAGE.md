# AI Usage Log

ReadPath is built with help from Claude Code. Each completed step adds one line:
date - step - what Claude Code did - what I decided or checked.

- 2026-11-25 - Project skeleton - created package layout, Makefile, requirements, smoke test - reviewed plan
- 2026-11-25 - API clients - wrote Semantic Scholar + arXiv clients, shared cache/retry helper, fixture tests, `search` CLI - approved plan, checked live search output (survived five 429s)
- 2026-11-25 - Pack collection - wrote build_pack.py collection (seeds, 2 reference levels, in-pack edges, arXiv metadata) with pure ranking/edge functions and fake-data tests - approved plan, checked transformers dry-run summary (694 papers, 4204 edges)
- 2026-11-25 - Relate store - wrote store.py/queries.py (schema, one-transaction UNWIND writes) and the embed + write + `relate clone` path in build_pack.py, with a fake-pack .rl test - approved plan, checked counts with the relate CLI and committed data/packs/transformers.rl (5.0 MB)
