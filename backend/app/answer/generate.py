"""Generate a grounded answer and turn [n] markers into renderable citations."""
from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from typing import Any

from ..config import settings
from ..ingest.audio import fmt_timestamp
from ..retrieval.search import Hit, search
from . import prompts
from .llm import complete
from .verify import verify_answer

CITE = re.compile(r"\[(\d+)\]")
SENTENCE = re.compile(r"(?<=[.!?])\s+(?=[A-Z0-9])")


@dataclass
class Citation:
    n: int
    chunk_id: int
    source_id: str
    source_title: str
    source_kind: str
    course_name: str
    label: str
    locator: dict[str, Any]


def label_for(hit: Hit) -> str:
    """Human-readable citation label: 'Lecture 7, slide 23' / 'Lecture 7 @ 06:52'."""
    loc = hit.locator or {}
    bits: list[str] = [hit.source_title]
    if "slide" in loc:
        bits.append(f"slide {loc['slide']}")
    elif "page" in loc:
        bits.append(f"p.{loc['page']}")
    elif "line_start" in loc:
        bits.append(f"lines {loc['line_start']}-{loc['line_end']}")
    if "t_start" in loc:
        bits.append(f"@ {fmt_timestamp(loc['t_start'])}")
    return ", ".join(bits[:2]) + (f" {bits[2]}" if len(bits) > 2 else "")


async def answer_question(
    question: str,
    *,
    course_id: str | None = None,
    week: int | None = None,
    mode: str = "simple",
    top_k: int | None = None,
    verify: bool = True,
) -> dict[str, Any]:
    s = settings()
    # The UI sends "" for "all courses"; asyncpg rejects it as a UUID.
    course_id = course_id or None
    hits = await search(question, course_id=course_id, week=week, top_k=top_k or s.top_k)

    if not hits:
        return {
            "answer": "I couldn't find anything about that in the material you've "
                      "uploaded for this course.",
            "citations": [], "refused": True, "hits": [], "verification": None,
        }

    excerpts = [(i + 1, label_for(h), h.text) for i, h in enumerate(hits)]
    raw = await complete(
        prompts.answer_system(mode),
        prompts.build_user_prompt(question, excerpts),
    )

    used = sorted({int(n) for n in CITE.findall(raw) if 1 <= int(n) <= len(hits)})
    citations = [
        Citation(
            n=n,
            chunk_id=hits[n - 1].chunk_id,
            source_id=hits[n - 1].source_id,
            source_title=hits[n - 1].source_title,
            source_kind=hits[n - 1].source_kind,
            course_name=getattr(hits[n - 1], "course_name", ""),
            label=label_for(hits[n - 1]),
            locator=hits[n - 1].locator,
        )
        for n in used
    ]

    refused = not used and _looks_like_refusal(raw)
    verification = None
    if verify and used:
        verification = await verify_answer(raw, hits)

    return {
        "answer": raw.strip(),
        "citations": [asdict(c) for c in citations],
        "refused": refused,
        "verification": verification,
        "hits": [
            {
                "chunk_id": h.chunk_id,
                "label": label_for(h),
                "rrf": round(h.rrf, 5),
                "rerank_score": h.rerank_score,
                "arms": h.arms,
            }
            for h in hits
        ],
    }


def _looks_like_refusal(text: str) -> bool:
    t = text.lower()
    return any(
        p in t
        for p in (
            "isn't covered", "is not covered", "couldn't find", "could not find",
            "don't have", "do not have", "not in the material", "no material",
        )
    )


def split_sentences(text: str) -> list[str]:
    """Split into claims for verification.

    Naive sentence splitting destroys maths: "S = {(a,b,c), (a,c,b)}" looks like
    four sentence boundaries. So we mask bracketed expressions before splitting
    and restore them afterwards.
    """
    clean = re.sub(r"^[-*\d.)\s]+", "", text, flags=re.MULTILINE)
    clean = re.sub(r"\*\*|__", "", clean)          # strip markdown emphasis

    masked, store = [], []
    def hide(m):
        store.append(m.group(0))
        return f"\x00{len(store) - 1}\x00"
    clean = re.sub(r"\{[^{}]*\}|\([^()]*\)", hide, clean)

    for part in SENTENCE.split(clean):
        part = re.sub(r"\x00(\d+)\x00", lambda m: store[int(m.group(1))], part)
        part = part.strip()
        if len(part) > 15:
            masked.append(part)
    return masked
