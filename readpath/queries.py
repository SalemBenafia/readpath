"""All Cypher statements used by ReadPath, as named constants."""

# ---------- schema ----------

CREATE_PAPER_ID_UNIQUE = (
    "CREATE CONSTRAINT paper_id IF NOT EXISTS FOR (p:Paper) REQUIRE p.id IS UNIQUE"
)
CREATE_AUTHOR_ID_UNIQUE = (
    "CREATE CONSTRAINT author_id IF NOT EXISTS FOR (a:Author) REQUIRE a.id IS UNIQUE"
)
CREATE_TOPIC_ID_UNIQUE = (
    "CREATE CONSTRAINT topic_id IF NOT EXISTS FOR (t:Topic) REQUIRE t.id IS UNIQUE"
)
CREATE_PAPER_ARXIV_INDEX = "CREATE INDEX paper_arxiv IF NOT EXISTS FOR (p:Paper) ON (p.arxiv)"
CREATE_PAPER_EMBEDDING_INDEX = (
    "CREATE VECTOR INDEX paper_embedding IF NOT EXISTS FOR (p:Paper) ON (p.embedding) "
    "OPTIONS {indexConfig: {`vector.dimensions`: 384, `vector.similarity_function`: 'cosine'}}"
)
CREATE_PAPER_TEXT_INDEX = (
    "CREATE FULLTEXT INDEX paper_text IF NOT EXISTS FOR (p:Paper) ON EACH [p.title, p.abstract]"
)

SCHEMA_STATEMENTS = (
    CREATE_PAPER_ID_UNIQUE,
    CREATE_AUTHOR_ID_UNIQUE,
    CREATE_TOPIC_ID_UNIQUE,
    CREATE_PAPER_ARXIV_INDEX,
    CREATE_PAPER_EMBEDDING_INDEX,
    CREATE_PAPER_TEXT_INDEX,
)

# ---------- pack writes (each takes $rows, a list of maps) ----------

MERGE_PAPERS = """
UNWIND $rows AS row
MERGE (p:Paper {id: row.id})
SET p.title = row.title,
    p.year = row.year,
    p.abstract = row.abstract,
    p.citedBy = row.citedBy,
    p.arxiv = row.arxiv,
    p.doi = row.doi,
    p.embedding = vector(row.emb, 384, FLOAT32)
"""

MERGE_AUTHORS = """
UNWIND $rows AS row
MATCH (p:Paper {id: row.paper})
MERGE (a:Author {id: row.id})
SET a.name = row.name
MERGE (p)-[:BY]->(a)
"""

MERGE_TOPICS = """
UNWIND $rows AS row
MATCH (p:Paper {id: row.paper})
MERGE (t:Topic {id: row.topic})
MERGE (p)-[r:ABOUT]->(t)
SET r.primary = row.primary
"""

MERGE_CITES = """
UNWIND $rows AS row
MATCH (src:Paper {id: row.src})
MATCH (dst:Paper {id: row.dst})
MERGE (src)-[:CITES]->(dst)
"""

MERGE_PACK = """
MERGE (k:Pack {name: $name})
SET k.seeds = $seeds, k.builtAt = $builtAt
"""

# ---------- search ----------

VECTOR_SEARCH = """
MATCH (p:Paper)
SEARCH p IN (VECTOR INDEX paper_embedding FOR vector($vector, 384, FLOAT32) LIMIT $k) SCORE AS score
RETURN p.id AS id, p.title AS title, p.year AS year, p.citedBy AS cited_by, score
ORDER BY score DESC, id
"""

FULLTEXT_SEARCH = """
MATCH (p:Paper)
SEARCH p IN (FULLTEXT INDEX paper_text FOR $query LIMIT $k) SCORE AS score
RETURN p.id AS id, p.title AS title, p.year AS year, p.citedBy AS cited_by, score
ORDER BY score DESC, id
"""

# ---------- reading paths ----------
# Variable-length bounds cannot be parameters, so there is one constant per depth.

FOUNDATIONS_D2 = """
MATCH (t:Paper {id: $target})-[:CITES*1..2]->(f:Paper)
WHERE NOT f.id IN $already_read AND f.id <> $target
WITH f, count(*) AS routes
RETURN f.id AS id, f.title AS title, f.year AS year, f.citedBy AS cited_by,
       f.arxiv AS arxiv, f.doi AS doi, routes
ORDER BY routes DESC, cited_by DESC, id
LIMIT $limit
"""

FOUNDATIONS_D3 = """
MATCH (t:Paper {id: $target})-[:CITES*1..3]->(f:Paper)
WHERE NOT f.id IN $already_read AND f.id <> $target
WITH f, count(*) AS routes
RETURN f.id AS id, f.title AS title, f.year AS year, f.citedBy AS cited_by,
       f.arxiv AS arxiv, f.doi AS doi, routes
ORDER BY routes DESC, cited_by DESC, id
LIMIT $limit
"""

WHY_CHAINS_D2 = """
MATCH path = (t:Paper {id: $target})-[:CITES*1..2]->(f:Paper {id: $foundation})
RETURN [n IN nodes(path) | {id: n.id, title: n.title, year: n.year}] AS chain
ORDER BY length(path) ASC
LIMIT 3
"""

WHY_CHAINS_D3 = """
MATCH path = (t:Paper {id: $target})-[:CITES*1..3]->(f:Paper {id: $foundation})
RETURN [n IN nodes(path) | {id: n.id, title: n.title, year: n.year}] AS chain
ORDER BY length(path) ASC
LIMIT 3
"""

FOUNDATIONS = {2: FOUNDATIONS_D2, 3: FOUNDATIONS_D3}
WHY_CHAINS = {2: WHY_CHAINS_D2, 3: WHY_CHAINS_D3}

AUTHORS_TO_FOLLOW = """
MATCH (f:Paper)-[:BY]->(a:Author)
WHERE f.id IN $ids
RETURN a.name AS author, count(DISTINCT f) AS papers
ORDER BY papers DESC, author
LIMIT 5
"""

AUTHORS_OF_PAPERS = """
MATCH (f:Paper)-[:BY]->(a:Author)
WHERE f.id IN $ids
WITH a, collect(DISTINCT f.id) AS papers
RETURN a.id AS id, a.name AS name, papers
ORDER BY size(papers) DESC, name
LIMIT $limit
"""

# A primary arXiv category counts 1.0, a secondary one 0.5.
TOPICS_IN_PATH = """
MATCH (f:Paper)-[r:ABOUT]->(t:Topic)
WHERE f.id IN $ids
RETURN t.id AS topic,
       sum(CASE WHEN r.primary THEN 1.0 ELSE 0.5 END) AS score,
       count(DISTINCT f) AS papers
ORDER BY score DESC, topic
LIMIT 5
"""

PAPER_BY_TITLE = """
MATCH (p:Paper)
WHERE toLower(p.title) = $title
RETURN p.id AS id, p.title AS title, p.year AS year, p.citedBy AS cited_by,
       p.arxiv AS arxiv, p.doi AS doi
ORDER BY cited_by DESC, id
LIMIT 1
"""

EDGES_AMONG = """
MATCH (a:Paper)-[:CITES]->(b:Paper)
WHERE a.id IN $ids AND b.id IN $ids
RETURN a.id AS src, b.id AS dst
"""

PAPER_BY_ID = """
MATCH (p:Paper {id: $id})
RETURN p.id AS id, p.title AS title, p.year AS year, p.citedBy AS cited_by,
       p.arxiv AS arxiv, p.doi AS doi
"""

# ---------- reads ----------

COUNT_NODES_BY_LABEL = """
MATCH (n)
UNWIND labels(n) AS label
RETURN label, count(*) AS n
ORDER BY label
"""

PACK_INFO = """
MATCH (k:Pack)
RETURN k.name AS name, k.seeds AS seeds, k.builtAt AS built_at
"""

PACK_SUMMARY = """
MATCH (k:Pack)
OPTIONAL MATCH (s:Paper) WHERE s.id IN k.seeds
RETURN k.name AS name, k.builtAt AS built_at, k.seeds AS seeds, collect(s.title) AS seed_titles
"""

COUNT_PAPERS = """
MATCH (p:Paper)
RETURN count(p) AS papers
"""

PRIMARY_TOPICS = """
MATCH (p:Paper)-[:ABOUT {primary: true}]->(t:Topic)
RETURN p.id AS paper, t.id AS topic
ORDER BY paper, topic
"""

MIN_EMBEDDING_DIMENSIONS = """
MATCH (p:Paper)
RETURN min(vector_dimension_count(p.embedding)) AS dimensions
"""

COUNT_RELS_BY_TYPE = """
MATCH ()-[r]->()
RETURN type(r) AS type, count(*) AS n
ORDER BY type
"""
