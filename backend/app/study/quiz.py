"""Quiz generation and adaptive selection.

Every question is grounded in specific chunks and stores their ids, which means
a quiz question carries the same provenance guarantee as an answer: you can show
the student exactly which slide the question came from, and the eval harness can
check whether a question is answerable from its own sources.

Selection is adaptive: the most informative question for a student is one they
have roughly a 50/50 chance on. Under the logistic model that is a question
whose difficulty sits near the student's ability, so `next_questions` targets
|b - theta| rather than always serving the hardest or the newest.
"""
from __future__ import annotations

import logging

from ..answer.llm import complete_json
from ..config import settings
from ..db import acquire

log = logging.getLogger(__name__)

QUIZ_SYSTEM = """You write exam-style multiple-choice questions from lecture material.

Rules:
- Every question must be answerable from the supplied passages alone.
- Never refer to the source in the question: no "according to the passage",
  "as the slides state", "in the given text". A student sees the question, not
  the passage. Ask about the concept directly.
- Distractors must be plausible to a student who half-understands the topic:
  common misconceptions, off-by-one errors, swapped formulas, confusing a
  definition with a closely related one. Never obviously silly options.
- Exactly one option is correct.
- No "all of the above" or "none of the above".
- Plain text only. No LaTeX, no $...$ delimiters, no backslash commands.
  Write "S = {a, b, c}" not "$S = \\{a, b, c\\}$", and "P(E)" not "$P(E)$".
- difficulty is -1.5 (recall a stated definition) to 1.5 (multi-step reasoning),
  where 0 is a typical exam question.

Return JSON: [{"stem": "...", "options": {"A": "...", "B": "...", "C": "...", "D": "..."},
"answer": "A", "rationale": "why the answer is right, one sentence",
"difficulty": 0.0}]"""


async def generate_for_topic(topic_id: str, n: int = 4) -> dict:
    async with acquire() as conn:
        topic = await conn.fetchrow("SELECT id, name FROM topics WHERE id = $1", topic_id)
        if topic is None:
            return {"error": "no such topic"}
        chunks = await conn.fetch(
            """SELECT c.id, c.text FROM chunks c
               JOIN chunk_topics ct ON ct.chunk_id = c.id
               WHERE ct.topic_id = $1 ORDER BY ct.weight DESC, c.id LIMIT 5""",
            topic_id,
        )

    if not chunks:
        return {"error": "topic has no chunks", "topic": topic["name"]}

    passages = "\n\n---\n\n".join(f"[{c['id']}] {c['text']}" for c in chunks)
    try:
        items = await complete_json(
            QUIZ_SYSTEM,
            f"TOPIC: {topic['name']}\n\nPASSAGES\n{passages}\n\nWrite {n} questions.",
            model=settings().llm_model, max_tokens=2000, temperature=0.6,
        )
    except Exception as exc:
        log.exception("quiz generation failed")
        return {"error": f"{type(exc).__name__}: {exc}", "topic": topic["name"]}

    if not isinstance(items, list):
        return {"error": "model did not return a list", "topic": topic["name"]}

    rows, skipped = [], 0
    for it in items:
        try:
            options = it["options"]
            answer = str(it["answer"]).strip()
            # A question whose answer key isn't one of its options is unusable.
            if answer not in options or len(options) < 3:
                skipped += 1
                continue
            rows.append((
                topic_id, str(it["stem"]).strip(), options, answer,
                it.get("rationale"), float(it.get("difficulty", 0.0)),
                [c["id"] for c in chunks],
            ))
        except (KeyError, TypeError, ValueError):
            skipped += 1

    if rows:
        async with acquire() as conn:
            await conn.executemany(
                """INSERT INTO quiz_questions
                     (topic_id, stem, options, answer, rationale, difficulty,
                      grounding_chunk_ids)
                   VALUES ($1,$2,$3::jsonb,$4,$5,$6,$7)""",
                rows,
            )

    return {"topic": topic["name"], "created": len(rows), "skipped": skipped}


async def next_questions(user_id: str, course_id: str, n: int = 5) -> list[dict]:
    """Pick questions near the student's current ability on each topic.

    Ordering rationale, in SQL terms: unseen topics first (we know nothing about
    them), then questions whose difficulty is closest to the student's theta.
    Questions already answered correctly are excluded.
    """
    async with acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT q.id, q.stem, q.options, q.difficulty, q.grounding_chunk_ids,
                   t.id AS topic_id, t.name AS topic,
                   COALESCE(m.theta, 0.0) AS theta,
                   COALESCE(m.n_seen, 0)  AS n_seen
            FROM quiz_questions q
            JOIN topics t ON t.id = q.topic_id
            LEFT JOIN mastery m ON m.topic_id = t.id AND m.user_id = $1
            WHERE t.course_id = $2
              AND NOT EXISTS (
                  SELECT 1 FROM attempts a
                  WHERE a.question_id = q.id AND a.user_id = $1 AND a.correct
              )
            ORDER BY COALESCE(m.n_seen, 0) ASC,
                     abs(q.difficulty - COALESCE(m.theta, 0.0)) ASC,
                     random()
            LIMIT $3
            """,
            user_id, course_id, n,
        )

    return [
        {
            "question_id": str(r["id"]),
            "topic_id": str(r["topic_id"]),
            "topic": r["topic"],
            "stem": r["stem"],
            "options": r["options"],
            "difficulty": round(float(r["difficulty"]), 2),
            "grounding_chunk_ids": list(r["grounding_chunk_ids"] or []),
        }
        for r in rows
    ]
