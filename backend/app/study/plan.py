"""Study planner.

"I have an algorithms exam next Friday, make me a plan."

The scheduling itself is deterministic, not an LLM call. An LLM asked to build a
revision timetable produces something plausible-looking that cannot be checked,
re-planned, or explained. Here the planner is an explicit rule:

    urgency(topic) = (1 - predicted_retention_at_exam) * (1 + weakness)

where weakness rises as theta falls. Topics you know well and reviewed recently
score low; topics you have never been quizzed on score high because their
retention is unknown and assumed poor. Sessions are then laid out backwards from
the exam so the weakest material gets both an early pass and a late one — spaced
repetition rather than one long block.

Plan items are rows, not prose, so each is checkable, re-orderable and
re-plannable. The LLM's only job is writing the one-line rationale a student
actually reads.
"""
from __future__ import annotations

from datetime import date, timedelta
from uuid import UUID

from ..db import acquire
from .mastery import mastery_report
from .scoring import urgency as _urgency

MIN_SESSION_MIN = 20
MAX_SESSIONS_PER_DAY = 4


def urgency(topic: dict, days_to_exam: float) -> float:
    return _urgency(topic["theta"], topic["n_correct"],
                    topic["days_since_review"], days_to_exam)


async def build_plan(user_id: str, course_id: str, exam_date: date,
                     minutes_per_day: int = 60,
                     start: date | None = None) -> dict:
    start = start or date.today()
    if exam_date <= start:
        return {"error": "exam date must be in the future"}

    topics = await mastery_report(user_id, course_id)
    if not topics:
        return {"error": "no topics — run topic extraction first"}

    days = [start + timedelta(days=i) for i in range((exam_date - start).days)]
    sessions_per_day = max(1, min(MAX_SESSIONS_PER_DAY, minutes_per_day // MIN_SESSION_MIN))
    session_minutes = max(MIN_SESSION_MIN, minutes_per_day // sessions_per_day)

    scored = sorted(
        ((urgency(t, (exam_date - start).days), t) for t in topics),
        key=lambda x: -x[0],
    )

    # Round-robin the ranked topics across the available slots. The weakest
    # topic therefore recurs most often and appears both early and late.
    slots = [(d, s) for d in days for s in range(sessions_per_day)]
    items: list[dict] = []
    i = 0
    for day, _slot in slots:
        score, topic = scored[i % len(scored)]
        seen_before = any(it["topic_id"] == topic["topic_id"] for it in items)
        items.append({
            "_date": day,          # asyncpg needs a real date; isoformat is for JSON
            "day": day.isoformat(),
            "topic_id": topic["topic_id"],
            "topic": topic["topic"],
            "activity": "quiz" if seen_before else "review",
            "minutes": session_minutes,
            "rationale": _why(topic, score, seen_before),
        })
        i += 1

    # Final day is consolidation on the three weakest topics.
    last = days[-1].isoformat()
    items = [it for it in items if it["day"] != last]
    for _score, topic in scored[:3]:
        items.append({
            "_date": days[-1],
            "day": last,
            "topic_id": topic["topic_id"],
            "topic": topic["topic"],
            "activity": "quiz",
            "minutes": max(MIN_SESSION_MIN, minutes_per_day // 3),
            "rationale": "Final pass on your weakest topic before the exam.",
        })

    async with acquire() as conn:
        plan_id = await conn.fetchval(
            """INSERT INTO study_plans (user_id, course_id, exam_date)
               VALUES ($1,$2,$3) RETURNING id""",
            user_id, course_id, exam_date,
        )
        await conn.executemany(
            """INSERT INTO study_plan_items
                 (plan_id, day, topic_id, activity, minutes, rationale)
               VALUES ($1,$2,$3,$4,$5,$6)""",
            [(plan_id, it["_date"], UUID(it["topic_id"]), it["activity"],
              it["minutes"], it["rationale"]) for it in items],
        )

    return {
        "plan_id": str(plan_id),
        "exam_date": exam_date.isoformat(),
        "days": (exam_date - start).days,
        "minutes_per_day": minutes_per_day,
        "n_items": len(items),
        "ranking": [
            {"topic": t["topic"], "urgency": round(s, 3), "theta": t["theta"],
             "n_seen": t["n_seen"]}
            for s, t in scored
        ],
        "items": [{k: v for k, v in it.items() if k != "_date"} for it in items],
    }


def _why(topic: dict, score: float, repeat: bool) -> str:
    if topic["n_seen"] == 0:
        return "Not assessed yet, so mastery is unknown — start here."
    if repeat:
        return f"Spaced repeat; ability estimate {topic['theta']:+.2f}."
    if topic["theta"] < -0.2:
        return f"Weakest area (theta {topic['theta']:+.2f}) — needs the most time."
    if topic["retention"] is not None and topic["retention"] < 0.6:
        return f"Retention has decayed to {topic['retention']:.0%} since last review."
    return f"Maintenance pass; ability estimate {topic['theta']:+.2f}."


async def get_plan(plan_id: str) -> dict:
    async with acquire() as conn:
        plan = await conn.fetchrow("SELECT * FROM study_plans WHERE id=$1", plan_id)
        items = await conn.fetch(
            """SELECT i.*, t.name AS topic FROM study_plan_items i
               LEFT JOIN topics t ON t.id = i.topic_id
               WHERE i.plan_id = $1 ORDER BY i.day, i.id""",
            plan_id,
        )
    return {"plan": dict(plan) if plan else None, "items": [dict(i) for i in items]}
