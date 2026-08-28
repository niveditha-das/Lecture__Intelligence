"""Make the eval set reproducible on a machine that has never seen your database.

The problem: `eval_examples.gold_chunk_ids` holds bigserial ids. Those are
assigned at ingest time, so a fresh database — a colleague's laptop, a CI
runner — gets different numbers for the same passages, and every gold label
silently points at the wrong chunk. A benchmark that only works on the machine
that created it is not a benchmark.

The fix: export gold labels as (source_title, ordinal) pairs, which are stable
for a given source file, and resolve them back to ids at import time.

    python -m app.evaluation.seed --export --out evalsets/goldset.jsonl
    python -m app.evaluation.seed --samples ../samples
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os

from ..db import acquire, close_pool, init_pool
from ..ingest.pipeline import ingest_source

KINDS = {".pdf": "pdf", ".pptx": "pptx", ".md": "notes", ".txt": "notes"}


async def export(out: str, course_id: str | None) -> None:
    async with acquire() as conn:
        rows = await conn.fetch(
            """SELECT e.question, e.gold_answer, e.kind, e.week, e.gold_chunk_ids
               FROM eval_examples e
               WHERE ($1::uuid IS NULL OR e.course_id = $1::uuid) ORDER BY e.id""",
            course_id,
        )
        chunks = await conn.fetch(
            "SELECT c.id, c.ordinal, s.title FROM chunks c JOIN sources s ON s.id = c.source_id"
        )

    by_id = {r["id"]: {"source_title": r["title"], "ordinal": r["ordinal"]} for r in chunks}

    n = 0
    with open(out, "w", encoding="utf-8") as fh:
        for r in rows:
            refs = [by_id[cid] for cid in (r["gold_chunk_ids"] or []) if cid in by_id]
            fh.write(json.dumps({
                "question": r["question"],
                "gold_answer": r["gold_answer"],
                "kind": r["kind"],
                "week": r["week"],
                "gold_refs": refs,
            }, ensure_ascii=False) + "\n")
            n += 1
    print(f"exported {n} examples to {out} (gold labels as title+ordinal, not ids)")


async def seed(samples_dir: str, goldset: str, course_name: str) -> None:
    async with acquire() as conn:
        course_id = await conn.fetchval(
            "INSERT INTO courses (name) VALUES ($1) RETURNING id", course_name
        )

    files = sorted(
        f for f in os.listdir(samples_dir)
        if os.path.splitext(f)[1].lower() in KINDS
    )
    if not files:
        raise SystemExit(f"no ingestable files in {samples_dir}")

    for fname in files:
        path = os.path.abspath(os.path.join(samples_dir, fname))
        stem = os.path.splitext(fname)[0]
        week = next((int(p) for p in stem.replace("-", "_").split("_") if p.isdigit()), None)
        async with acquire() as conn:
            source_id = await conn.fetchval(
                """INSERT INTO sources (course_id, kind, title, week, storage_uri)
                   VALUES ($1,$2,$3,$4,$5) RETURNING id""",
                course_id, KINDS[os.path.splitext(fname)[1].lower()],
                stem.replace("_", " "), week, path,
            )
        n = await ingest_source(str(source_id))
        print(f"ingested {fname}: {n} chunks (week {week})")

    if not os.path.exists(goldset):
        print(f"no goldset at {goldset} — corpus seeded, no eval examples loaded")
        return

    async with acquire() as conn:
        chunk_rows = await conn.fetch(
            """SELECT c.id, c.ordinal, s.title FROM chunks c
               JOIN sources s ON s.id = c.source_id WHERE c.course_id = $1""",
            course_id,
        )
        index = {(r["title"], r["ordinal"]): r["id"] for r in chunk_rows}

        loaded = dropped = 0
        for line in open(goldset, encoding="utf-8"):
            if not line.strip():
                continue
            ex = json.loads(line)
            gold, missing = [], False
            for ref in ex.get("gold_refs", []):
                cid = index.get((ref["source_title"], ref["ordinal"]))
                if cid is None:
                    missing = True
                    break
                gold.append(cid)
            # A factual example whose gold chunk can't be resolved would score as
            # a retrieval miss. Drop it loudly rather than corrupt the metric.
            if missing:
                dropped += 1
                continue
            await conn.execute(
                """INSERT INTO eval_examples
                     (course_id, question, gold_chunk_ids, gold_answer, kind, week)
                   VALUES ($1,$2,$3,$4,$5,$6)""",
                course_id, ex["question"], gold, ex.get("gold_answer"),
                ex.get("kind", "factual"), ex.get("week"),
            )
            loaded += 1

    print(f"loaded {loaded} eval examples" + (f", dropped {dropped} unresolvable" if dropped else ""))
    print(f"course_id: {course_id}")


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--export", action="store_true")
    ap.add_argument("--out", default="evalsets/goldset.jsonl")
    ap.add_argument("--goldset", default="evalsets/goldset.jsonl")
    ap.add_argument("--samples", default="../samples")
    ap.add_argument("--course-id")
    ap.add_argument("--course-name", default="Probability and Statistics")
    args = ap.parse_args()

    await init_pool()
    try:
        if args.export:
            await export(args.out, args.course_id)
        else:
            await seed(args.samples, args.goldset, args.course_name)
    finally:
        await close_pool()


if __name__ == "__main__":
    asyncio.run(main())
