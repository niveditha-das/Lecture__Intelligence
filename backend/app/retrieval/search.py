"""Hybrid retrieval in a single Postgres round-trip.

Arm A: pgvector HNSW cosine ANN.
Arm B: tsvector/GIN keyword search (catches exact identifiers: "O(log n)",
       "Dijkstra", "Q3.2" — where dense retrieval is famously weak).
Fusion: Reciprocal Rank Fusion, score = sum 1/(k + rank). No score
       normalisation needed, which is why RRF beats naive weighted sums here.
Then:  optional cross-encoder rerank of the fused candidates.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from ..config import settings
from ..db import acquire, to_vector_literal
from .embeddings import embed_query

SQL = """
WITH vec AS (
    SELECT id, ROW_NUMBER() OVER (ORDER BY embedding <=> $1::vector) AS rank
    FROM chunks
    WHERE embedding IS NOT NULL
      AND ($2::uuid IS NULL OR course_id = $2::uuid)
      AND ($3::int  IS NULL OR week = $3::int)
    ORDER BY embedding <=> $1::vector
    LIMIT $4
),
kw AS (
    SELECT c.id,
           ROW_NUMBER() OVER (ORDER BY ts_rank_cd(c.tsv, q) DESC) AS rank
    FROM chunks c, plainto_tsquery('english', $5) q
    WHERE c.tsv @@ q
      AND ($2::uuid IS NULL OR c.course_id = $2::uuid)
      AND ($3::int  IS NULL OR c.week = $3::int)
    ORDER BY ts_rank_cd(c.tsv, q) DESC
    LIMIT $4
),
fused AS (
    SELECT id,
           SUM(score) AS rrf,
           BOOL_OR(arm = 'vec') AS in_vec,
           BOOL_OR(arm = 'kw')  AS in_kw
    FROM (
        SELECT id, 1.0 / ($6 + rank) AS score, 'vec' AS arm FROM vec
        UNION ALL
        SELECT id, 1.0 / ($6 + rank) AS score, 'kw'  AS arm FROM kw
    ) t
    GROUP BY id
)
SELECT c.id, c.text, c.locator, c.week, c.source_id,
       s.title AS source_title, s.kind AS source_kind, s.storage_uri,
       f.rrf, f.in_vec, f.in_kw
FROM fused f
JOIN chunks  c ON c.id = f.id
JOIN sources s ON s.id = c.source_id
ORDER BY f.rrf DESC
LIMIT $7;
"""


@dataclass
class Hit:
    chunk_id: int
    text: str
    locator: dict[str, Any]
    source_id: str
    source_title: str
    source_kind: str
    storage_uri: str
    week: int | None
    rrf: float
    rerank_score: float | None = None
    arms: list[str] = field(default_factory=list)


async def search(
    query: str,
    *,
    course_id: str | None = None,
    week: int | None = None,
    top_k: int | None = None,
    rerank: bool | None = None,
) -> list[Hit]:
    s = settings()
    top_k = top_k or s.top_k
    rerank = s.rerank_enabled if rerank is None else rerank

    qvec = to_vector_literal(await embed_query(query))
    fetch = max(top_k, s.candidates_per_arm) if rerank else top_k

    async with acquire() as conn:
        rows = await conn.fetch(
            SQL, qvec, course_id, week, s.candidates_per_arm, query, s.rrf_k, fetch
        )

    hits = [
        Hit(
            chunk_id=r["id"],
            text=r["text"],
            locator=r["locator"],
            source_id=str(r["source_id"]),
            source_title=r["source_title"],
            source_kind=r["source_kind"],
            storage_uri=r["storage_uri"],
            week=r["week"],
            rrf=float(r["rrf"]),
            arms=[a for a, on in (("vec", r["in_vec"]), ("kw", r["in_kw"])) if on],
        )
        for r in rows
    ]

    if rerank and hits:
        from .rerank import rerank_hits

        hits = await rerank_hits(query, hits)

    return hits[:top_k]
