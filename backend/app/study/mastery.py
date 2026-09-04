"""Mastery model: persistence around app/study/scoring.py.

The update rule itself lives in `scoring.py` with no imports, so it can be unit
tested without a database. This module is only the part that needs Postgres:
recording an attempt, updating the stored ability estimate, and reporting.

See scoring.py for the model and why K decays with experience.
"""
from __future__ import annotations

from datetime import datetime, timezone

from ..db import acquire
from .scoring import retention, sigmoid, update_theta

__all__ = ["record_attempt", "mastery_report", "retention", "sigmoid", "update_theta"]


async def record_attempt(user_id: str, question_id: str, chosen: str,
                         ms_taken: int | None = None) -> dict:
    async with acquire() as conn:
        q = await conn.fetchrow(
            """SELECT q.id, q.answer, q.difficulty, q.rationale, q.topic_id,
                      q.grounding_chunk_ids, t.name AS topic
               FROM quiz_questions q JOIN topics t ON t.id = q.topic_id
               WHERE q.id = $1""",
            question_id,
        )
        if q is None:
            return {"error": "no such question"}

        correct = chosen.strip().upper() == str(q["answer"]).strip().upper()

        async with conn.transaction():
            await conn.execute(
                """INSERT INTO attempts (user_id, question_id, correct, ms_taken)
                   VALUES ($1,$2,$3,$4)""",
                user_id, question_id, correct, ms_taken,
            )
            m = await conn.fetchrow(
                "SELECT theta, n_seen FROM mastery WHERE user_id=$1 AND topic_id=$2",
                user_id, q["topic_id"],
            )
            theta = float(m["theta"]) if m else 0.0
            n_seen = int(m["n_seen"]) if m else 0
            new_theta = update_theta(theta, float(q["difficulty"]), correct, n_seen)

            await conn.execute(
                """INSERT INTO mastery (user_id, topic_id, theta, n_seen, last_seen)
                   VALUES ($1,$2,$3,1,now())
                   ON CONFLICT (user_id, topic_id) DO UPDATE
                     SET theta = $3, n_seen = mastery.n_seen + 1, last_seen = now()""",
                user_id, q["topic_id"], new_theta,
            )

    return {
        "correct": correct,
        "answer": q["answer"],
        "rationale": q["rationale"],
        "topic": q["topic"],
        "grounding_chunk_ids": list(q["grounding_chunk_ids"] or []),
        "theta_before": round(theta, 3),
        "theta_after": round(new_theta, 3),
        "predicted_p": round(sigmoid(theta - float(q["difficulty"])), 3),
    }


async def mastery_report(user_id: str, course_id: str) -> list[dict]:
    """Every topic with its ability estimate and current predicted retention."""
    async with acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT t.id, t.name, t.week,
                   COALESCE(m.theta, 0.0) AS theta,
                   COALESCE(m.n_seen, 0)  AS n_seen,
                   m.last_seen,
                   (SELECT count(*) FROM attempts a
                    JOIN quiz_questions q ON q.id = a.question_id
                    WHERE q.topic_id = t.id AND a.user_id = $1 AND a.correct) AS n_correct,
                   (SELECT count(*) FROM quiz_questions q WHERE q.topic_id = t.id) AS n_questions
            FROM topics t
            LEFT JOIN mastery m ON m.topic_id = t.id AND m.user_id = $1
            WHERE t.course_id = $2
            ORDER BY COALESCE(m.theta, 0.0) ASC, t.name
            """,
            user_id, course_id,
        )

    now = datetime.now(timezone.utc)
    out = []
    for r in rows:
        days = (now - r["last_seen"]).total_seconds() / 86400 if r["last_seen"] else None
        out.append({
            "topic_id": str(r["id"]),
            "topic": r["name"],
            "week": r["week"],
            "theta": round(float(r["theta"]), 3),
            "n_seen": r["n_seen"],
            "n_correct": r["n_correct"],
            "n_questions": r["n_questions"],
            "days_since_review": round(days, 2) if days is not None else None,
            "retention": (
                round(retention(float(r["theta"]), r["n_correct"], days), 3)
                if days is not None else None
            ),
        })
    return out


async def record_self_assessment(user_id: str, question_id: str, correct: bool) -> dict:
    """Mastery update for a written answer the student graded themselves.

    Identical to the MCQ path apart from where the verdict comes from. Marking
    yourself is noisier than a multiple-choice comparison, so the attempt is
    flagged `self_assessed` — a later calibration pass can down-weight these
    without having to guess which rows they were.
    """
    async with acquire() as conn:
        q = await conn.fetchrow(
            """SELECT q.id, q.difficulty, q.topic_id, t.name AS topic
               FROM quiz_questions q JOIN topics t ON t.id = q.topic_id
               WHERE q.id = $1""",
            question_id,
        )
        if q is None:
            return {"error": "no such question"}

        async with conn.transaction():
            await conn.execute(
                """INSERT INTO attempts (user_id, question_id, correct, self_assessed)
                   VALUES ($1,$2,$3,true)""",
                user_id, question_id, correct,
            )
            m = await conn.fetchrow(
                "SELECT theta, n_seen FROM mastery WHERE user_id=$1 AND topic_id=$2",
                user_id, q["topic_id"],
            )
            theta = float(m["theta"]) if m else 0.0
            n_seen = int(m["n_seen"]) if m else 0
            new_theta = update_theta(theta, float(q["difficulty"]), correct, n_seen)

            await conn.execute(
                """INSERT INTO mastery (user_id, topic_id, theta, n_seen, last_seen)
                   VALUES ($1,$2,$3,1,now())
                   ON CONFLICT (user_id, topic_id) DO UPDATE
                     SET theta = $3, n_seen = mastery.n_seen + 1, last_seen = now()""",
                user_id, q["topic_id"], new_theta,
            )

    return {
        "correct": correct,
        "topic": q["topic"],
        "theta_before": round(theta, 3),
        "theta_after": round(new_theta, 3),
        "predicted_p": round(sigmoid(theta - float(q["difficulty"])), 3),
    }
