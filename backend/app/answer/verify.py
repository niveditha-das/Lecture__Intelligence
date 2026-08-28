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


async def _check(sentence: str, passages: list[str]) -> dict:
    body = "PASSAGES\n" + "\n---\n".join(passages) + f"\n\nCLAIM\n{sentence}"
    last = "no attempt"
    async with _judge_gate:
        for attempt in range(3):
            try:
                res = await complete_json(
                    prompts.VERIFIER_SYSTEM, body,
                    model=settings().judge_model, max_tokens=400, temperature=0.0,
                )
                if isinstance(res, dict) and "verdict" in res:
                    return res
                last = "bad judge output"
            except Exception as exc:
                last = f"judge error: {type(exc).__name__}"
                if "RateLimit" not in type(exc).__name__:
                    break
            await asyncio.sleep(2 ** attempt * 3)   # 3s, 6s, 12s
    return {"verdict": "UNKNOWN", "why": last}


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
        jobs.append(_check(CITE.sub("", sent).strip(), [hits[n - 1].text for n in ns]))

    verdicts = await asyncio.gather(*jobs) if jobs else []
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
