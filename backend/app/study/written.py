"""Written questions: short answer and long answer.

MCQs test recognition. Exams mostly don't. A short-answer question makes you
produce the definition rather than pick it out of four, and a long-answer
question makes you structure an argument across several ideas — which is why
these need more than one chunk of source material.

Both store a model answer and a list of marking points, so the student can grade
themselves against something concrete rather than a vague impression of whether
they were close. That self-assessment feeds the same mastery model as MCQs.
"""
from __future__ import annotations

import logging

from ..answer.llm import complete_json
from ..config import settings
from ..db import acquire

log = logging.getLogger(__name__)

SHORT_SYSTEM = """You write short-answer exam questions from lecture material.

Rules:
- Answerable from the supplied passages alone, in 2-4 sentences.
- Ask for a definition, a mechanism, or a reason — something with a right answer.
- Never refer to the source: no "according to the passage" or "as the slides say".
  The student sees only the question.
- Plain text. No LaTeX, no markdown, no $ delimiters.
- model_answer is what full marks looks like, written as a student would write it.
- marking_points are the 2-4 things a marker looks for, each a short phrase.
- difficulty is -1.5 (recall) to 1.5 (requires reasoning), 0 is typical.

Return JSON: [{"stem": "...", "model_answer": "...",
"marking_points": ["...", "..."], "difficulty": 0.0}]"""

LONG_SYSTEM = """You write long-answer exam questions from lecture material.

Rules:
- Each question must require connecting at least two ideas from the passages —
  compare, explain a trade-off, walk through a mechanism end to end. Not recall.
- Answerable from the supplied passages alone. Do not require outside knowledge.
- Never refer to the source: no "according to the passage". The student sees
  only the question.
- Plain text. No LaTeX, no markdown, no $ delimiters.
- model_answer is a full-marks answer of roughly 150-250 words.
- marking_points are the 4-6 things a marker looks for, each a short phrase.
- difficulty is -1.5 to 1.5; long answers are usually 0.3 or above.

Return JSON: [{"stem": "...", "model_answer": "...",
"marking_points": ["...", "..."], "difficulty": 0.5}]"""

# A long answer needs enough material to connect ideas across.
CHUNKS_FOR = {"short": 4, "long": 8}


async def generate_written(topic_id: str, fmt: str, n: int = 2) -> dict:
    if fmt not in ("short", "long"):
        return {"error": f"unknown format {fmt}"}

    async with acquire() as conn:
        topic = await conn.fetchrow("SELECT id, name FROM topics WHERE id = $1", topic_id)
        if topic is None:
            return {"error": "no such topic"}
        chunks = await conn.fetch(
            """SELECT c.id, c.text FROM chunks c
               JOIN chunk_topics ct ON ct.chunk_id = c.id
               WHERE ct.topic_id = $1 ORDER BY ct.weight DESC, c.id LIMIT $2""",
            topic_id, CHUNKS_FOR[fmt],
        )

    if not chunks:
        return {"error": "topic has no chunks", "topic": topic["name"]}

    # A long-answer question that only has one slide behind it will not require
    # connecting anything, so don't pretend otherwise.
    if fmt == "long" and len(chunks) < 2:
        return {"topic": topic["name"], "created": 0, "skipped": 0,
                "note": "not enough material for a long answer"}

    passages = "\n\n---\n\n".join(f"[{c['id']}] {c['text']}" for c in chunks)
    system = SHORT_SYSTEM if fmt == "short" else LONG_SYSTEM

    try:
        items = await complete_json(
            system,
            f"TOPIC: {topic['name']}\n\nPASSAGES\n{passages}\n\nWrite {n} questions.",
            model=settings().llm_model,
            max_tokens=3000 if fmt == "long" else 1600,
            temperature=0.6,
        )
    except Exception as exc:
        log.exception("written generation failed")
        return {"error": f"{type(exc).__name__}: {exc}", "topic": topic["name"]}

    if not isinstance(items, list):
        return {"error": "model did not return a list", "topic": topic["name"]}

    rows, skipped = [], 0
    for it in items:
        try:
            stem = str(it["stem"]).strip()
            model_answer = str(it["model_answer"]).strip()
            points = it.get("marking_points") or []
            if not stem or len(model_answer) < 20 or not isinstance(points, list):
                skipped += 1
                continue
            rows.append((
                topic_id, stem, fmt, model_answer,
                [str(p) for p in points][:6],
                float(it.get("difficulty", 0.3 if fmt == "long" else 0.0)),
                [c["id"] for c in chunks],
            ))
        except (KeyError, TypeError, ValueError):
            skipped += 1

    if rows:
        async with acquire() as conn:
            await conn.executemany(
                """INSERT INTO quiz_questions
                     (topic_id, stem, format, model_answer, marking_points,
                      difficulty, grounding_chunk_ids, options)
                   VALUES ($1,$2,$3,$4,$5::jsonb,$6,$7,'{}'::jsonb)""",
                [(t, s, f, m, p, d, g) for (t, s, f, m, p, d, g) in rows],
            )

    return {"topic": topic["name"], "format": fmt, "created": len(rows), "skipped": skipped}


async def next_written(user_id: str, course_id: str, fmt: str, n: int = 3) -> list[dict]:
    """Written questions the student hasn't yet marked themselves correct on."""
    async with acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT q.id, q.stem, q.model_answer, q.marking_points, q.difficulty,
                   q.grounding_chunk_ids, t.id AS topic_id, t.name AS topic
            FROM quiz_questions q
            JOIN topics t ON t.id = q.topic_id
            LEFT JOIN mastery m ON m.topic_id = t.id AND m.user_id = $1
            WHERE t.course_id = $2 AND q.format = $3
              AND NOT EXISTS (
                  SELECT 1 FROM attempts a
                  WHERE a.question_id = q.id AND a.user_id = $1 AND a.correct
              )
            ORDER BY COALESCE(m.n_seen, 0) ASC,
                     abs(q.difficulty - COALESCE(m.theta, 0.0)) ASC,
                     random()
            LIMIT $4
            """,
            user_id, course_id, fmt, n,
        )

    return [
        {
            "question_id": str(r["id"]),
            "topic_id": str(r["topic_id"]),
            "topic": r["topic"],
            "stem": r["stem"],
            "model_answer": r["model_answer"],
            "marking_points": list(r["marking_points"] or []),
            "difficulty": round(float(r["difficulty"]), 2),
            "grounding_chunk_ids": list(r["grounding_chunk_ids"] or []),
        }
        for r in rows
    ]
