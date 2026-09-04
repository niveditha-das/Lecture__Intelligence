"""Exam mode.

Practice mode reveals the answer immediately, which is the right shape for
learning but the wrong shape for rehearsal — you never find out whether you can
hold four answers in your head without help. Exam mode withholds every model
answer until the whole paper is submitted.

Question selection is deliberately not adaptive here. Practice targets your
current ability; an exam should sample the syllabus, including the parts you
have quietly avoided. So it spreads across topics and prefers ones you have
seen least.
"""
from __future__ import annotations

from ..db import acquire


async def build_paper(user_id: str, course_id: str, n: int = 5,
                      fmt: str = "long", topic_id: str | None = None) -> dict:
    async with acquire() as conn:
        rows = await conn.fetch(
            """
            WITH ranked AS (
                SELECT q.id, q.stem, q.model_answer, q.marking_points, q.difficulty,
                       q.grounding_chunk_ids, t.id AS topic_id, t.name AS topic,
                       t.week,
                       COALESCE(m.n_seen, 0) AS n_seen,
                       ROW_NUMBER() OVER (
                           PARTITION BY t.id ORDER BY random()
                       ) AS rn
                FROM quiz_questions q
                JOIN topics t ON t.id = q.topic_id
                LEFT JOIN mastery m ON m.topic_id = t.id AND m.user_id = $1
                WHERE t.course_id = $2 AND q.format = $3
                  AND ($4::uuid IS NULL OR t.id = $4::uuid)
            )
            -- rn = 1 first, so every topic contributes before any topic repeats
            SELECT * FROM ranked
            ORDER BY rn ASC, n_seen ASC, random()
            LIMIT $5
            """,
            user_id, course_id, fmt, topic_id, n,
        )

    questions = [
        {
            "question_id": str(r["id"]),
            "topic_id": str(r["topic_id"]),
            "topic": r["topic"],
            "week": r["week"],
            "stem": r["stem"],
            "model_answer": r["model_answer"],
            "marking_points": list(r["marking_points"] or []),
            "difficulty": round(float(r["difficulty"]), 2),
        }
        for r in rows
    ]

    # A rough minute budget, so the paper feels like a paper.
    minutes = sum(12 if fmt == "long" else 5 for _ in questions)

    return {
        "format": fmt,
        "n": len(questions),
        "suggested_minutes": minutes,
        "topics": sorted({q["topic"] for q in questions}),
        "questions": questions,
    }
