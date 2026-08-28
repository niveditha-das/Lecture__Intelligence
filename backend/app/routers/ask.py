from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel, Field

from ..answer.generate import answer_question, label_for
from ..retrieval.search import search

router = APIRouter(tags=["tutor"])


class AskIn(BaseModel):
    question: str
    course_id: str | None = None
    week: int | None = Field(None, description='"only material from Week 4"')
    mode: str = "simple"          # simple | technical | example | socratic | quiz
    top_k: int | None = None
    verify: bool = True


@router.post("/ask")
async def ask(body: AskIn):
    return await answer_question(
        body.question,
        course_id=body.course_id,
        week=body.week,
        mode=body.mode,
        top_k=body.top_k,
        verify=body.verify,
    )


@router.get("/search")
async def raw_search(q: str, course_id: str | None = None, week: int | None = None,
                     top_k: int = 10, rerank: bool = True):
    """Retrieval without generation — useful for debugging and for the eval UI."""
    hits = await search(q, course_id=course_id, week=week, top_k=top_k, rerank=rerank)
    return [
        {
            "chunk_id": h.chunk_id,
            "label": label_for(h),
            "text": h.text[:400],
            "locator": h.locator,
            "rrf": round(h.rrf, 5),
            "rerank_score": h.rerank_score,
            "arms": h.arms,
        }
        for h in hits
    ]
