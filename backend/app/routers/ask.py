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


@router.post("/eval/run")
async def eval_run(label: str = "run", k: int = 5, rerank: bool = True,
                   course_id: str | None = None):
    """Run the retrieval eval inside the API process.

    `docker compose exec` starts a second interpreter that loads its own copy of
    the embedding model, which OOMs under Docker Desktop's default memory limit.
    Reusing the already-warm model in this process avoids that.
    """
    from ..db import acquire
    from ..evaluation import metrics as M

    async with acquire() as conn:
        rows = await conn.fetch(
            """SELECT id, question, gold_chunk_ids, kind, week FROM eval_examples
               WHERE ($1::uuid IS NULL OR course_id = $1::uuid) ORDER BY id""",
            course_id,
        )

    recalls, mrrs = [], []
    for r in rows:
        if r["kind"] == "unanswerable":
            continue
        hits = await search(r["question"], course_id=course_id,
                            week=r["week"], top_k=k, rerank=rerank)
        got = [h.chunk_id for h in hits]
        gold = list(r["gold_chunk_ids"] or [])
        recalls.append(M.recall_at_k(got, gold, k))
        mrrs.append(M.mrr(got, gold))

    return {"label": label, "k": k, "rerank": rerank,
            "n_factual": len(recalls),
            "recall_at_k": M.mean(recalls), "mrr": M.mean(mrrs)}

@router.post("/eval/refusal")
async def eval_refusal(course_id: str | None = None):
    """Refusal accuracy on the unanswerable controls.

    Refusing correctly is a measurable behaviour, not an assumption. These
    questions sound like the course but are answerable from no chunk in it.
    """
    from ..answer.generate import answer_question
    from ..db import acquire

    async with acquire() as conn:
        rows = await conn.fetch(
            """SELECT question, week FROM eval_examples
               WHERE kind = 'unanswerable'
                 AND ($1::uuid IS NULL OR course_id = $1::uuid)""",
            course_id,
        )

    results = []
    for r in rows:
        res = await answer_question(r["question"], course_id=course_id,
                                    week=r["week"], verify=False)
        results.append({"question": r["question"][:70],
                        "refused": res["refused"],
                        "answer": res["answer"][:120]})

    n = len(results)
    correct = sum(1 for x in results if x["refused"])
    return {"n": n,
            "refusal_accuracy": round(correct / n, 3) if n else None,
            "results": results}