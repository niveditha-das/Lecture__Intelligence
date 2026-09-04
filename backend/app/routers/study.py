from __future__ import annotations

import asyncio
from datetime import date

from fastapi import APIRouter
from pydantic import BaseModel

from ..db import acquire
from ..study import mastery as M
from ..study import plan as P
from ..study import quiz as Q
from ..study.topics import extract_topics

router = APIRouter(prefix="/study", tags=["study"])

# Single-user demo. Swap for real auth before this is anything but a portfolio piece.
DEMO_USER = "00000000-0000-0000-0000-000000000001"


@router.post("/topics/extract")
async def topics_extract(course_id: str, limit: int | None = None):
    return await extract_topics(course_id, limit)


@router.get("/topics")
async def topics_list(course_id: str):
    async with acquire() as conn:
        rows = await conn.fetch(
            """SELECT t.id, t.name, t.week, count(ct.chunk_id) AS n_chunks,
                      (SELECT count(*) FROM quiz_questions q WHERE q.topic_id = t.id)
                        AS n_questions
               FROM topics t
               LEFT JOIN chunk_topics ct ON ct.topic_id = t.id
               WHERE t.course_id = $1
               GROUP BY t.id ORDER BY t.week NULLS LAST, t.name""",
            course_id,
        )
    return [dict(r) for r in rows]


class QuizGenIn(BaseModel):
    course_id: str
    per_topic: int = 3
    max_topics: int | None = None


@router.post("/quiz/generate")
async def quiz_generate(body: QuizGenIn):
    """Generate questions for every topic that doesn't have enough yet."""
    async with acquire() as conn:
        rows = await conn.fetch(
            """SELECT t.id FROM topics t
               WHERE t.course_id = $1
                 AND (SELECT count(*) FROM quiz_questions q WHERE q.topic_id = t.id) < $2
                 AND EXISTS (SELECT 1 FROM chunk_topics ct WHERE ct.topic_id = t.id)
               ORDER BY t.week NULLS LAST, t.name
               LIMIT COALESCE($3::int, 100)""",
            body.course_id, body.per_topic, body.max_topics,
        )

    # Serialised: generation is the expensive call and free tiers rate-limit.
    sem = asyncio.Semaphore(1)

    async def one(topic_id):
        async with sem:
            return await Q.generate_for_topic(str(topic_id), body.per_topic)

    results = await asyncio.gather(*(one(r["id"]) for r in rows))
    return {
        "topics_processed": len(results),
        "questions_created": sum(r.get("created", 0) for r in results),
        "results": results,
    }


@router.get("/quiz/next")
async def quiz_next(course_id: str, n: int = 5, user_id: str = DEMO_USER):
    return await Q.next_questions(user_id, course_id, n)


class AnswerIn(BaseModel):
    question_id: str
    chosen: str
    ms_taken: int | None = None
    user_id: str = DEMO_USER


@router.post("/quiz/answer")
async def quiz_answer(body: AnswerIn):
    return await M.record_attempt(body.user_id, body.question_id, body.chosen, body.ms_taken)


@router.get("/mastery")
async def mastery(course_id: str, user_id: str = DEMO_USER):
    return await M.mastery_report(user_id, course_id)


class PlanIn(BaseModel):
    course_id: str
    exam_date: date
    minutes_per_day: int = 60
    user_id: str = DEMO_USER


@router.post("/plan")
async def plan(body: PlanIn):
    return await P.build_plan(
        body.user_id, body.course_id, body.exam_date, body.minutes_per_day
    )


@router.get("/plan/{plan_id}")
async def plan_detail(plan_id: str):
    return await P.get_plan(plan_id)


@router.post("/topics/similarity")
async def topic_similarity(course_id: str):
    """Pairwise similarity of existing topic labels — used to set MERGE_THRESHOLD
    from data rather than by guessing."""
    import numpy as np

    from ..retrieval.embeddings import embed_texts

    async with acquire() as conn:
        rows = await conn.fetch(
            "SELECT name FROM topics WHERE course_id = $1 ORDER BY name", course_id
        )
    names = [r["name"] for r in rows]
    if len(names) < 2:
        return {"error": "not enough topics"}

    V = np.array(await embed_texts(names))
    V = V / (np.linalg.norm(V, axis=1, keepdims=True) + 1e-9)
    sim = V @ V.T

    pairs = [
        {"a": names[i], "b": names[j], "sim": round(float(sim[i, j]), 3)}
        for i in range(len(names)) for j in range(i + 1, len(names))
    ]
    pairs.sort(key=lambda p: -p["sim"])
    return {"n_topics": len(names), "top_pairs": pairs[:25]}


# --- written questions: short and long answer ---------------------------


class WrittenGenIn(BaseModel):
    course_id: str
    format: str = "short"          # short | long
    per_topic: int = 2
    max_topics: int | None = 6


@router.post("/questions/generate")
async def questions_generate(body: WrittenGenIn):
    """Generate written questions for topics that don't have enough yet."""
    from ..study.written import generate_written

    if body.format not in ("short", "long"):
        return {"error": "format must be 'short' or 'long'"}

    async with acquire() as conn:
        rows = await conn.fetch(
            """SELECT t.id FROM topics t
               WHERE t.course_id = $1
                 AND (SELECT count(*) FROM quiz_questions q
                      WHERE q.topic_id = t.id AND q.format = $2) < $3
                 AND EXISTS (SELECT 1 FROM chunk_topics ct WHERE ct.topic_id = t.id)
               ORDER BY t.week NULLS LAST, t.name
               LIMIT COALESCE($4::int, 100)""",
            body.course_id, body.format, body.per_topic, body.max_topics,
        )

    results = []
    for r in rows:
        results.append(await generate_written(str(r["id"]), body.format, body.per_topic))

    return {
        "format": body.format,
        "topics_processed": len(results),
        "questions_created": sum(x.get("created", 0) for x in results),
        "results": results,
    }


@router.get("/questions/next")
async def questions_next(course_id: str, format: str = "short", n: int = 3,
                         user_id: str = DEMO_USER):
    from ..study.written import next_written

    if format not in ("short", "long"):
        return []
    return await next_written(user_id, course_id, format, n)


class SelfAssessIn(BaseModel):
    question_id: str
    correct: bool
    user_id: str = DEMO_USER


@router.post("/questions/assess")
async def questions_assess(body: SelfAssessIn):
    return await M.record_self_assessment(body.user_id, body.question_id, body.correct)


@router.get("/counts")
async def counts(course_id: str):
    """How many questions of each format exist — drives the generate buttons."""
    async with acquire() as conn:
        rows = await conn.fetch(
            """SELECT q.format, count(*) AS n
               FROM quiz_questions q JOIN topics t ON t.id = q.topic_id
               WHERE t.course_id = $1 GROUP BY q.format""",
            course_id,
        )
        topics = await conn.fetchval(
            "SELECT count(*) FROM topics WHERE course_id = $1", course_id
        )
    out = {"mcq": 0, "short": 0, "long": 0, "topics": topics}
    for r in rows:
        out[r["format"]] = r["n"]
    return out


@router.get("/exam")
async def exam(course_id: str, n: int = 5, format: str = "long",
               topic_id: str | None = None, user_id: str = DEMO_USER):
    """A paper: several questions, no model answers until you submit."""
    from ..study.exam import build_paper

    return await build_paper(user_id, course_id, n, format, topic_id)
