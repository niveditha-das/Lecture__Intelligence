"""Post-hoc grounding check.

Split the answer into sentences, take each sentence's own citations, and ask a
cheap judge whether those passages entail it. Two things fall out:

  * a UI guardrail - flag sentences the sources don't back;
  * `unsupported_claim_rate`, the headline number in the README. This is a real
    measurement, not a vibe, which is exactly what the eval section is for.
"""
from __future__ import annotations

import asyncio
import re

from ..config import settings
from ..retrieval.search import Hit
from . import prompts
from .llm import complete_json

CITE = re.compile(r"\[(\d+)\]")

# Free-tier providers rate-limit hard (Gemini: ~15 req/min). Serialise the judge
# and back off on 429 instead of firing every sentence at once.
_judge_gate = asyncio.Semaphore(2)


async def _check_all(items: list[tuple[str, list[str]]]) -> list[dict]:
    """Check every sentence in ONE judge call.

    Previously this made one call per sentence. With the central 4.5s pacer
    that put a six-sentence answer at ~30s, which is unusable interactively —
    the throttle that fixed batch evaluation broke the thing people actually
    wait on. One call costs the same 4.5s regardless of sentence count.
    """
    if not items:
        return []

    body = "\n\n".join(
        f"CLAIM {i}\n{sent}\nPASSAGES\n" + "\n---\n".join(passages)
        for i, (sent, passages) in enumerate(items)
    )
    system = (
        "You check whether each numbered claim is supported by its own passages.\n"
        "SUPPORTED only if the passages state or directly entail the claim.\n"
        "PARTIAL if they support part of it but the claim adds specifics they do not.\n"
        "UNSUPPORTED if the passages do not establish it.\n"
        'Return JSON: {"0": {"verdict": "SUPPORTED", "why": "<12 words"}, "1": {...}} '
        "with one key per claim index. Include every index."
    )

    async with _judge_gate:
        for attempt in range(3):
            try:
                res = await complete_json(
                    system, body,
                    model=settings().judge_model,
                    max_tokens=120 * len(items) + 200,
                    temperature=0.0,
                )
                if isinstance(res, dict):
                    return [
                        res.get(str(i)) or {"verdict": "UNKNOWN", "why": "missing from judge output"}
                        for i in range(len(items))
                    ]
            except Exception as exc:
                last = f"judge error: {type(exc).__name__}"
                if "RateLimit" not in type(exc).__name__:
                    return [{"verdict": "UNKNOWN", "why": last} for _ in items]
                await asyncio.sleep(2 ** attempt * 3)
    return [{"verdict": "UNKNOWN", "why": "judge unavailable"} for _ in items]


async def verify_answer(answer: str, hits: list[Hit]) -> dict:
    from .generate import split_sentences

    sentences = split_sentences(answer)
    jobs, targets = [], []

    for sent in sentences:
        ns = [int(n) for n in CITE.findall(sent) if 1 <= int(n) <= len(hits)]
        if not ns:
            targets.append((sent, None))
            continue
        targets.append((sent, ns))
        jobs.append((CITE.sub("", sent).strip(), [hits[n - 1].text for n in ns]))

    verdicts = await _check_all(jobs) if jobs else []
    out, vi = [], 0
    supported = checked = 0

    for sent, ns in targets:
        if ns is None:
            out.append({"sentence": sent, "citations": [], "verdict": "UNCITED"})
            continue
        v = verdicts[vi]; vi += 1
        # UNKNOWN = the judge failed, which is missing data, not evidence of a
        # hallucination. Excluding it keeps the metric honest.
        if v.get("verdict") != "UNKNOWN":
            checked += 1
            if v.get("verdict") == "SUPPORTED":
                supported += 1
        out.append({"sentence": sent, "citations": ns, **v})

    uncited = sum(1 for _, ns in targets if ns is None)
    return {
        "sentences": out,
        "n_sentences": len(targets),
        "n_checked": checked,
        "n_unknown": sum(1 for o in out if o.get("verdict") == "UNKNOWN"),
        "supported_ratio": round(supported / checked, 3) if checked else None,
        "uncited_sentences": uncited,
        "unsupported_claim_rate": (
            round(1 - supported / checked, 3) if checked else None
        ),
    }
