"""Build the eval set semi-automatically, then review it by hand.

    python -m app.evaluation.build_set --course-id <uuid> --n 60 --out evalsets/algorithms.jsonl
    # ...edit the jsonl, delete bad questions, then:
    python -m app.evaluation.build_set --load evalsets/algorithms.jsonl --course-id <uuid>

Method: sample chunks, ask a model for a question answerable *only* from that
chunk, and record the chunk id as gold. Then add `unanswerable` controls —
plausible course-adjacent questions the material genuinely doesn't cover. Those
controls are what let you measure refusal instead of assuming it.

The hand-review step is not optional. A gold set you didn't check is a
benchmark that measures your generator's agreement with itself.
"""
from __future__ import annotations

import argparse
import asyncio
import json

from ..answer.llm import complete_json
from ..config import settings
from ..db import acquire, close_pool, init_pool

GEN_SYSTEM = """You write evaluation questions for a lecture retrieval system.
Given one passage from a lecture, write ONE question that:
  - a student would plausibly type;
  - is answerable using this passage alone;
  - does NOT quote the passage verbatim or say "according to the passage";
  - names the concept, so it is findable without seeing the passage.
Also give the short gold answer.
Return JSON: {"question": "...", "gold_answer": "...", "kind": "factual"|"synthesis"}"""

UNANS_SYSTEM = """You write CONTROL questions for a retrieval system: questions that
sound like they belong to this course but are NOT answerable from the given topics.
Stay in the same subject area; do not be absurd. A good control is one a student
might really ask about material the lecturer never covered.
Return JSON: [{"question": "...", "kind": "unanswerable"}]"""


async def sample_chunks(course_id: str, n: int) -> list[dict]:
    async with acquire() as conn:
        rows = await conn.fetch(
            """SELECT c.id, c.text, c.week, s.title
               FROM chunks c JOIN sources s ON s.id = c.source_id
               WHERE c.course_id = $1 AND c.n_tokens > 80
               ORDER BY random() LIMIT $2""",
            course_id, n,
        )
    return [dict(r) for r in rows]


async def generate(course_id: str, n: int, out: str, n_unanswerable: int) -> None:
    chunks = await sample_chunks(course_id, n)
    if not chunks:
        print("no chunks — ingest some lectures first")
        return

    sem = asyncio.Semaphore(4)

    async def one(ch):
        async with sem:
            try:
                res = await complete_json(
                    GEN_SYSTEM, f"PASSAGE ({ch['title']})\n{ch['text']}",
                    model=settings().judge_model, max_tokens=300, temperature=0.4,
                )
                return {
                    "question": res["question"],
                    "gold_chunk_ids": [ch["id"]],
                    "gold_answer": res.get("gold_answer"),
                    "kind": res.get("kind", "factual"),
                    "week": ch["week"],
                    "_passage_preview": ch["text"][:200],   # for your hand review
                }
            except Exception as exc:
                print(f"skip chunk {ch['id']}: {exc}")
                return None

    items = [x for x in await asyncio.gather(*(one(c) for c in chunks)) if x]

    if n_unanswerable:
        topics = "\n".join(f"- {c['title']}: {c['text'][:120]}" for c in chunks[:20])
        try:
            controls = await complete_json(
                UNANS_SYSTEM,
                f"Write {n_unanswerable} control questions.\nCOVERED MATERIAL\n{topics}",
                model=settings().judge_model, max_tokens=800, temperature=0.7,
            )
            for c in controls if isinstance(controls, list) else []:
                items.append({"question": c["question"], "gold_chunk_ids": [],
                              "gold_answer": None, "kind": "unanswerable", "week": None})
        except Exception as exc:
            print(f"control generation failed: {exc}")

    with open(out, "w", encoding="utf-8") as fh:
        for it in items:
            fh.write(json.dumps(it, ensure_ascii=False) + "\n")
    print(f"wrote {len(items)} candidates to {out}\nREVIEW THEM BY HAND, then --load the file.")


async def load(path: str, course_id: str) -> None:
    rows = []
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            if not line.strip():
                continue
            it = json.loads(line)
            rows.append((course_id, it["question"], it.get("gold_chunk_ids") or [],
                         it.get("gold_answer"), it.get("kind", "factual"), it.get("week")))
    async with acquire() as conn:
        await conn.executemany(
            """INSERT INTO eval_examples
                 (course_id, question, gold_chunk_ids, gold_answer, kind, week)
               VALUES ($1,$2,$3,$4,$5,$6)""",
            rows,
        )
    print(f"loaded {len(rows)} eval examples")


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--course-id", required=True)
    ap.add_argument("--n", type=int, default=50)
    ap.add_argument("--unanswerable", type=int, default=10)
    ap.add_argument("--out", default="evalsets/candidates.jsonl")
    ap.add_argument("--load")
    args = ap.parse_args()

    await init_pool()
    try:
        if args.load:
            await load(args.load, args.course_id)
        else:
            await generate(args.course_id, args.n, args.out, args.unanswerable)
    finally:
        await close_pool()


if __name__ == "__main__":
    asyncio.run(main())
