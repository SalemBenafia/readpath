---
name: reading-path
description: Build a reading path for a paper with the ReadPath Relate MCP server. Use when asked
what to read before a paper, or how two papers connect.
argument-hint: [paper title]
---
Build a reading path for: $ARGUMENTS
Use only the `readpath` MCP server (a read-only Relate graph of papers).
Pass values as query parameters when the tool allows it.
1. If you have not seen the schema in this session, call get_schema once.
2. Find the paper with read_cypher:
MATCH (p:Paper)
SEARCH p IN (FULLTEXT INDEX paper_text FOR $q LIMIT 5) SCORE AS score
RETURN p.id AS id, p.title AS title, p.year AS year, score
ORDER BY score DESC
Pick the best match and say which one you picked.
3. Get its foundations:
MATCH (t:Paper {id: $target})-[:CITES*1..3]->(f:Paper)
WITH f, count(*) AS routes
RETURN f.id AS id, f.title AS title, f.year AS year, routes
ORDER BY routes DESC, year ASC LIMIT 6
4. For each foundation, get its shortest citation chain:
MATCH path = (t:Paper {id: $target})-[:CITES*1..3]->(f:Paper {id: $f})
RETURN [n IN nodes(path) | n.title] AS chain
ORDER BY length(path) ASC LIMIT 1
5. Answer with a numbered reading list, oldest prerequisites first. For each paper give
one line explaining WHY, based only on the chains you found.
Never invent papers that are not in the graph.
