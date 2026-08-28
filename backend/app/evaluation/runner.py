"""Run the eval suite and persist every result.

    python -m app.evaluation.runner --label "rrf+rerank" --k 5
    python -m app.evaluation.runner --no-rerank --label "no rerank"     # ablation
    python -m app.evaluation.runner --fail-under recall_at_k=0.80       # for CI

Every run records the git SHA and the full retrieval config, so the numbers in
your README are reproducible and regressions fail the build.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import subprocess
import time

from ..answer.generate import answer_question
from ..config import settings
from ..db import acquire, close_pool, init_pool
from ..retrieval.search import search
from . import metrics as M


def git_sha() -> str | None:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"], text=True
        ).strip()
    except Exception:
        return None


async def load_examples(course_id: str | None, limit: int | None) -> list[dict]:
    async with acquire() as conn:
        rows = await conn.fetch(
            """SELECT id, question, gold_chunk_ids, gold_answer, kind, week
               FROM eval_examples
               WHERE ($1::uuid IS NULL OR course_id = $1::uuid)
               ORDER BY id
               LIMIT COALESCE($2::int, 1000)""",
            course_id, limit,
        )
    return [dict(r) for r in rows]


async def run_one(ex: dict, k: int, rerank: bool, generate: bool, course_id: str | None) -> dict:
    t0 = time.perf_counter()

    hits = await search(ex["question"], course_id=course_id, week=ex.get("week"),
                        top_k=k, rerank=rerank)
    retrieved = [h.chunk_id for h in hits]
    gold = list(ex["gold_chunk_ids"] or [])
    unanswerable = ex["kind"] == "unanswerable"

    row = {
        "example_id": ex["id"],
        "retrieved_ids": retrieved,
        "recall_at_k": None if unanswerable else M.recall_at_k(retrieved, gold, k),
        "mrr": None if unanswerable else M.mrr(retrieved, gold),
        "citation_precision": None,
        "supported_ratio": None,
        "refused": None,
        "answer": None,
        "latency_ms": None,
    }

    if generate:
        res = await answer_question(
            ex["question"], course_id=course_id, week=ex.get("week"), top_k=k
        )
        cited = [c["chunk_id"] for c in res["citations"]]
        row["answer"] = res["answer"]
        row["refused"] = bool(res["refused"])
        if not unanswerable:
            row["citation_precision"] = M.citation_precision(cited, gold)
        if res.get("verification"):
            row["supported_ratio"] = res["verification"].get("supported_ratio")

    row["latency_ms"] = int((time.perf_counter() - t0) * 1000)
    return row


async def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--course-id")
    ap.add_argument("--label", default="run")
    ap.add_argument("--k", type=int, default=5)
    ap.add_argument("--limit", type=int)
    ap.add_argument("--no-rerank", action="store_true")
    ap.add_argument("--retrieval-only", action="store_true",
                    help="skip generation: fast, free, still catches most regressions")
    ap.add_argument("--concurrency", type=int, default=4)
    ap.add_argument("--fail-under", action="append", default=[],
                    metavar="metric=value", help="CI gate, e.g. recall_at_k=0.8")
    args = ap.parse_args()

    await init_pool()
    try:
        examples = await load_examples(args.course_id, args.limit)
        if not examples:
            print("no eval examples found — run app.evaluation.build_set first")
            return 2

        rerank = not args.no_rerank
        generate = not args.retrieval_only
        sem = asyncio.Semaphore(args.concurrency)

        async def guarded(ex):
            async with sem:
                return await run_one(ex, args.k, rerank, generate, args.course_id)

        rows = await asyncio.gather(*(guarded(e) for e in examples))

        s = settings()
        summary = {
            "n": len(rows),
            "k": args.k,
            "recall_at_k": M.mean([r["recall_at_k"] for r in rows if r["recall_at_k"] is not None]),
            "mrr": M.mean([r["mrr"] for r in rows if r["mrr"] is not None]),
            "citation_precision": M.mean(
                [r["citation_precision"] for r in rows if r["citation_precision"] is not None]
            ),
            "supported_ratio": M.mean(
                [r["supported_ratio"] for r in rows if r["supported_ratio"] is not None]
            ),
            "p50_latency_ms": sorted(r["latency_ms"] for r in rows)[len(rows) // 2],
        }
        if summary["supported_ratio"] is not None:
            summary["unsupported_claim_rate"] = round(1 - summary["supported_ratio"], 4)

        unans = [r for r, e in zip(rows, examples) if e["kind"] == "unanswerable"]
        if unans and generate:
            summary["refusal_accuracy"] = round(
                sum(1 for r in unans if r["refused"]) / len(unans), 4
            )

        config = {
            "rerank": rerank, "generate": generate,
            "embedding_model": s.embedding_model, "llm_model": s.llm_model,
            "candidates_per_arm": s.candidates_per_arm, "rrf_k": s.rrf_k,
            "chunk_target_tokens": s.chunk_target_tokens,
        }

        async with acquire() as conn:
            run_id = await conn.fetchval(
                """INSERT INTO eval_runs (git_sha, label, config, metrics)
                   VALUES ($1,$2,$3::jsonb,$4::jsonb) RETURNING id""",
                git_sha(), args.label, config, summary,
            )
            await conn.executemany(
                """INSERT INTO eval_results (run_id, example_id, retrieved_ids,
                       recall_at_k, mrr, citation_precision, supported_ratio,
                       refused, answer, latency_ms)
                   VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10)""",
                [
                    (run_id, r["example_id"], r["retrieved_ids"], r["recall_at_k"],
                     r["mrr"], r["citation_precision"], r["supported_ratio"],
                     r["refused"], r["answer"], r["latency_ms"])
                    for r in rows
                ],
            )

        print(f"\n### eval `{args.label}`  ({git_sha() or 'no-sha'})\n")
        print("| metric | value |\n|---|---|")
        for key, val in summary.items():
            print(f"| {key} | {val} |")
        print(f"\nconfig: {json.dumps(config)}")

        for gate in args.fail_under:
            name, _, target = gate.partition("=")
            got = summary.get(name)
            if got is None or got < float(target):
                print(f"\nFAIL: {name}={got} < {target}")
                return 1
        return 0
    finally:
        await close_pool()


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
