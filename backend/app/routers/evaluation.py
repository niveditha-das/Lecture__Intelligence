"""Evaluation endpoints.

The eval runs *inside* the API process on purpose. `docker compose exec` starts a
second interpreter that loads its own copy of the embedding model and the
cross-encoder; under Docker Desktop's default memory limit that OOMs, and
PyTorch fails with "Cannot copy out of meta tensor". Reusing the already-warm
models in this process avoids the problem entirely, and it means CI can evaluate
a running container over HTTP instead of needing a GPU-sized runner.

Every run is written to `eval_runs` with its git SHA and full retrieval config,
and every per-example result to `eval_results`, so regressions are diffable
rather than remembered.
"""
from __future__ import annotations

import asyncio
import math
import os
import subprocess
import time
from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel

from ..answer.generate import answer_question
from ..config import settings
from ..db import acquire
from ..evaluation import metrics as M
from ..retrieval.search import search

router = APIRouter(prefix="/eval", tags=["evaluation"])


def _git_sha() -> str | None:
    # CI and docker-compose pass this in; the container has no git of its own.
    env = os.environ.get("GIT_SHA")
    if env:
        return env[:7]
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"], text=True, stderr=subprocess.DEVNULL
        ).strip()
    except Exception:
        return None


def _clean(x: float | None) -> float | None:
    """NaN is 'not applicable' here, not a number worth storing."""
    if x is None or (isinstance(x, float) and math.isnan(x)):
        return None
    return round(float(x), 4)


class EvalRequest(BaseModel):
    label: str = "run"
    course_id: str | None = None
    k: int = 5
    rerank: bool = True
    generate: bool = True
    limit: int | None = None


async def _run_example(ex: dict, k: int, rerank: bool, generate: bool,
                       course_id: str | None) -> dict[str, Any]:
    t0 = time.perf_counter()
    unanswerable = ex["kind"] == "unanswerable"
    gold = list(ex["gold_chunk_ids"] or [])

    hits = await search(ex["question"], course_id=course_id, week=ex["week"],
                        top_k=k, rerank=rerank)
    retrieved = [h.chunk_id for h in hits]

    row: dict[str, Any] = {
        "example_id": ex["id"],
        "question": ex["question"],
        "kind": ex["kind"],
        "retrieved_ids": retrieved,
        "recall_at_k": None if unanswerable else _clean(M.recall_at_k(retrieved, gold, k)),
        "mrr": None if unanswerable else _clean(M.mrr(retrieved, gold)),
        "citation_precision": None,
        "supported_ratio": None,
        "refused": None,
        "answer": None,
    }

    if generate:
        res = await answer_question(ex["question"], course_id=course_id,
                                    week=ex["week"], top_k=k, verify=not unanswerable)
        row["answer"] = res["answer"]
        row["refused"] = bool(res["refused"])
        if not unanswerable:
            cited = [c["chunk_id"] for c in res["citations"]]
            by_n = {c["n"]: c["chunk_id"] for c in res["citations"]}
            supported: set[int] = set()
            for sent in (res.get("verification") or {}).get("sentences", []):
                if sent.get("verdict") == "SUPPORTED":
                    supported.update(by_n[n] for n in sent.get("citations", []) if n in by_n)
            row["citation_precision"] = _clean(
                M.citation_precision_supported(cited, gold, supported)
            )
            row["citation_precision_strict"] = _clean(M.citation_precision(cited, gold))
            if res.get("verification"):
                row["supported_ratio"] = _clean(res["verification"].get("supported_ratio"))

    row["latency_ms"] = int((time.perf_counter() - t0) * 1000)
    return row


@router.post("/run")
async def run_eval(body: EvalRequest):
    async with acquire() as conn:
        examples = [
            dict(r)
            for r in await conn.fetch(
                """SELECT id, question, gold_chunk_ids, kind, week FROM eval_examples
                   WHERE ($1::uuid IS NULL OR course_id = $1::uuid)
                   ORDER BY id LIMIT COALESCE($2::int, 1000)""",
                body.course_id, body.limit,
            )
        ]

    if not examples:
        return {"error": "no eval examples — load an eval set first", "n": 0}

    # Generation hits an LLM, and free tiers rate-limit hard, so serialise it.
    # Retrieval-only runs are local and can go wide.
    # llm.py paces all model calls centrally; this only bounds local work.
    sem = asyncio.Semaphore(2 if body.generate else 8)

    async def guarded(ex: dict) -> dict[str, Any]:
        async with sem:
            return await _run_example(ex, body.k, body.rerank, body.generate, body.course_id)

    rows = await asyncio.gather(*(guarded(e) for e in examples))

    def col(name: str) -> list[float]:
        return [r[name] for r in rows if r[name] is not None]

    summary: dict[str, Any] = {
        "n": len(rows),
        "n_factual": sum(1 for r in rows if r["kind"] != "unanswerable"),
        "k": body.k,
        "recall_at_k": M.mean(col("recall_at_k")),
        "mrr": M.mean(col("mrr")),
        "citation_precision": M.mean(col("citation_precision")),
        "p50_latency_ms": sorted(r["latency_ms"] for r in rows)[len(rows) // 2],
    }

    supported = col("supported_ratio")
    if supported:
        summary["supported_ratio"] = M.mean(supported)
        summary["unsupported_claim_rate"] = round(1 - summary["supported_ratio"], 4)

    controls = [r for r in rows if r["kind"] == "unanswerable"]
    if controls and body.generate:
        summary["refusal_accuracy"] = round(
            sum(1 for r in controls if r["refused"]) / len(controls), 4
        )

    s = settings()
    config = {
        "rerank": body.rerank,
        "rerank_model": s.rerank_model if body.rerank else None,
        "generate": body.generate,
        "embedding_provider": s.embedding_provider,
        "llm_model": s.llm_model if body.generate else None,
        "candidates_per_arm": s.candidates_per_arm,
        "rrf_k": s.rrf_k,
        "chunk_target_tokens": s.chunk_target_tokens,
    }

    async with acquire() as conn:
        run_id = await conn.fetchval(
            """INSERT INTO eval_runs (git_sha, label, config, metrics)
               VALUES ($1,$2,$3::jsonb,$4::jsonb) RETURNING id""",
            _git_sha(), body.label, config, summary,
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

    return {
        "run_id": str(run_id),
        "label": body.label,
        "git_sha": _git_sha(),
        "config": config,
        "metrics": summary,
        "results": [
            {k: v for k, v in r.items() if k != "answer"} for r in rows
        ],
    }


@router.get("/runs")
async def list_runs(limit: int = 20):
    """Run history — this is what makes a regression visible rather than remembered."""
    async with acquire() as conn:
        rows = await conn.fetch(
            """SELECT id, label, git_sha, started_at, config, metrics
               FROM eval_runs ORDER BY started_at DESC LIMIT $1""",
            limit,
        )
    return [dict(r) for r in rows]


@router.get("/runs/{run_id}")
async def run_detail(run_id: str):
    async with acquire() as conn:
        run = await conn.fetchrow("SELECT * FROM eval_runs WHERE id=$1", run_id)
        results = await conn.fetch(
            """SELECT r.*, e.question, e.kind
               FROM eval_results r JOIN eval_examples e ON e.id = r.example_id
               WHERE r.run_id = $1""",
            run_id,
        )
    return {"run": dict(run) if run else None, "results": [dict(r) for r in results]}
