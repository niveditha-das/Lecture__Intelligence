"""Topic extraction.

Two passes, because asking one model call to produce a clean global taxonomy
over a whole course does not work reliably:

  1. Label each chunk independently (1-3 short topic names).
  2. Merge near-duplicate labels using the embedding model we already have.
     "Conditional probability", "Conditional probabilities" and "Probability,
     conditional" are one topic; an LLM asked to dedupe a long list will
     silently drop or invent entries, whereas cosine similarity over labels is
     deterministic and inspectable.

The result is a topic per concept, with weighted chunk membership, which is what
quiz generation and the mastery model both need.
"""
from __future__ import annotations

import asyncio
import logging
import time

import numpy as np

from ..answer.llm import complete_json
from ..config import settings
from ..db import acquire
from ..retrieval.embeddings import embed_texts

log = logging.getLogger(__name__)

MERGE_THRESHOLD = 0.90   # cosine over label embeddings; set from measured pairs
MIN_CHUNKS_PER_TOPIC = 2  # a topic backed by one slide cannot carry a quiz
# Note: on a small corpus this prunes aggressively — most concepts appear on
# exactly one slide. Revisit both constants against a full semester of
# material rather than tuning them against 36 chunks.

BATCH_SIZE = 8          # passages per request
MIN_INTERVAL = 5.0      # seconds between requests: free tiers cap at ~15/min

LABEL_SYSTEM = """You label lecture passages with the concepts they teach.

You are given several numbered passages. For each, give 1-3 short topic names,
1-4 words each, in the vocabulary a lecturer would use. Name concepts, not
activities: "Conditional probability", not "Worked example". Title slides and
tables of contents get an empty list.

Return JSON: {"0": ["..."], "1": [], "2": ["...", "..."]} with one key per
passage index. Include every index."""


_last_call = 0.0
_pace = asyncio.Lock()


async def _throttled():
    """One request every MIN_INTERVAL seconds.

    Free tiers cap requests per minute, and the SDK's automatic retries fire
    within milliseconds, so an unpaced burst spends the whole quota on 429s
    without a single success. Pacing at the source is the only thing that works.
    """
    global _last_call
    async with _pace:
        wait = MIN_INTERVAL - (time.monotonic() - _last_call)
        if wait > 0:
            await asyncio.sleep(wait)
        _last_call = time.monotonic()


async def _label_batch(texts: list[str]) -> list[list[str]]:
    body = "\n\n".join(f"[{i}] {t[:1200]}" for i, t in enumerate(texts))
    for attempt in range(4):
        await _throttled()
        try:
            res = await complete_json(
                LABEL_SYSTEM, body,
                model=settings().judge_model, max_tokens=900, temperature=0.0,
            )
            if isinstance(res, dict):
                return [
                    [t.strip() for t in res.get(str(i), []) if isinstance(t, str) and t.strip()]
                    for i in range(len(texts))
                ]
        except Exception as exc:
            log.warning("labelling batch failed (attempt %d): %s", attempt + 1, exc)
            await asyncio.sleep(20 * (attempt + 1))
    return [[] for _ in texts]


def _merge_labels(labels: list[str], vecs: np.ndarray) -> dict[str, str]:
    """Greedy clustering over label embeddings. Returns label -> canonical label.

    Two things matter here, both learned by measuring rather than guessing:

    * Case and trivial punctuation are normalised *before* embedding. "Conditional
      probability" and "Conditional Probability" scored 0.974 as separate labels —
      an expensive way to discover a lowercase() call was missing.
    * A candidate is compared against every member of a cluster, not just its
      head. Comparing only to heads leaves chains unmerged: A matches B, B
      matches C, but A never meets C.

    The threshold is set from measured pairs on real labels: singular/plural
    variants score ~0.98, genuinely distinct concepts ~0.75.
    """
    norm = vecs / (np.linalg.norm(vecs, axis=1, keepdims=True) + 1e-9)
    clusters: list[list[int]] = []
    mapping: dict[str, str] = {}

    for i, label in enumerate(labels):
        best_c, best_sim = None, 0.0
        for ci, members in enumerate(clusters):
            sim = max(float(norm[i] @ norm[j]) for j in members)
            if sim > best_sim:
                best_c, best_sim = ci, sim
        if best_c is not None and best_sim >= MERGE_THRESHOLD:
            clusters[best_c].append(i)
            mapping[label] = labels[clusters[best_c][0]]
        else:
            clusters.append([i])
            mapping[label] = label
    return mapping


def _normalise(label: str) -> str:
    """Collapse case and stray punctuation before anything else sees the label."""
    return " ".join(label.strip().strip(".,;:").split()).lower()


async def extract_topics(course_id: str, limit: int | None = None) -> dict:
    async with acquire() as conn:
        chunks = await conn.fetch(
            """SELECT c.id, c.text, c.week FROM chunks c
               WHERE c.course_id = $1 AND c.n_tokens > 40
               ORDER BY c.id LIMIT COALESCE($2::int, 5000)""",
            course_id, limit,
        )
    if not chunks:
        return {"error": "no chunks for this course", "topics": 0}

    # One request per BATCH_SIZE chunks, paced. 43 chunks becomes ~6 calls
    # instead of 43, which fits inside a free-tier minute.
    labelled: list[tuple] = []
    for i in range(0, len(chunks), BATCH_SIZE):
        batch = chunks[i : i + BATCH_SIZE]
        results = await _label_batch([r["text"] for r in batch])
        labelled.extend(
            (r["id"], r["week"], topics) for r, topics in zip(batch, results)
        )
        log.info("labelled %d/%d chunks", len(labelled), len(chunks))

    # Normalise first: case-only duplicates must never reach the embedder.
    labelled = [(cid, wk, sorted({_normalise(t) for t in ts})) for cid, wk, ts in labelled]
    raw = sorted({t for _, _, ts in labelled for t in ts})
    if not raw:
        return {"error": "no topics produced", "topics": 0}

    vecs = np.array(await embed_texts(raw))
    mapping = _merge_labels(raw, vecs)
    canonical = sorted(set(mapping.values()))

    async with acquire() as conn:
        async with conn.transaction():
            ids: dict[str, str] = {}
            for name in canonical:
                week = min(
                    (w for _, w, ts in labelled
                     if w is not None and any(mapping.get(t) == name for t in ts)),
                    default=None,
                )
                ids[name] = await conn.fetchval(
                    """INSERT INTO topics (course_id, name, week) VALUES ($1,$2,$3)
                       ON CONFLICT (course_id, name)
                       DO UPDATE SET week = COALESCE(topics.week, EXCLUDED.week)
                       RETURNING id""",
                    course_id, name, week,
                )

            pairs = {
                (chunk_id, ids[mapping[t]])
                for chunk_id, _, ts in labelled for t in ts if mapping.get(t) in ids
            }
            await conn.executemany(
                """INSERT INTO chunk_topics (chunk_id, topic_id, weight)
                   VALUES ($1,$2,1.0) ON CONFLICT DO NOTHING""",
                list(pairs),
            )

    async with acquire() as conn:
        pruned = await conn.execute(
            """DELETE FROM topics t WHERE t.course_id = $1 AND (
                   SELECT count(*) FROM chunk_topics ct WHERE ct.topic_id = t.id
               ) < $2""",
            course_id, MIN_CHUNKS_PER_TOPIC,
        )

    return {
        "pruned_single_chunk_topics": pruned,
        "chunks_labelled": len(chunks),
        "raw_labels": len(raw),
        "topics": len(canonical),
        "merged": len(raw) - len(canonical),
        "links": len(pairs),
    }
