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

# ---------- reads ----------

COUNT_NODES_BY_LABEL = """
MATCH (n)
UNWIND labels(n) AS label
RETURN label, count(*) AS n
ORDER BY label
"""

COUNT_RELS_BY_TYPE = """
MATCH ()-[r]->()
RETURN type(r) AS type, count(*) AS n
ORDER BY type
"""
