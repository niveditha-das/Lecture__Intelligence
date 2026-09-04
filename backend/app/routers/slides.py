"""Browse a source page by page, and ask about one slide.

The rest of the app goes question -> answer -> source. This goes the other way:
start from a slide you didn't understand and get it explained from the material
around it. Same provenance guarantee, opposite direction of travel.
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from ..answer import prompts
from ..answer.llm import complete
from ..db import acquire

router = APIRouter(tags=["slides"])


@router.get("/sources/{source_id}/pages")
async def source_pages(source_id: str):
    """Every page of a source with a preview, for a thumbnail grid."""
    async with acquire() as conn:
        src = await conn.fetchrow(
            "SELECT id, title, kind, week FROM sources WHERE id = $1", source_id
        )
        if src is None:
            raise HTTPException(404, "no such source")
        rows = await conn.fetch(
            "SELECT id, ordinal, text, locator FROM chunks WHERE source_id = $1 ORDER BY ordinal",
            source_id,
        )

    pages: dict[int, dict] = {}
    for r in rows:
        loc = r["locator"] or {}
        page = loc.get("slide") or loc.get("page")
        if page is None:
            continue
        entry = pages.setdefault(
            int(page),
            {"page": int(page), "chunk_ids": [], "preview": "", "t_start": loc.get("t_start")},
        )
        entry["chunk_ids"].append(r["id"])
        if not entry["preview"]:
            entry["preview"] = " ".join(r["text"].split())[:120]

    return {
        "source": {"id": str(src["id"]), "title": src["title"], "kind": src["kind"],
                   "week": src["week"]},
        "pages": [pages[k] for k in sorted(pages)],
    }


class ExplainIn(BaseModel):
    source_id: str
    page: int
    mode: str = "simple"


@router.post("/explain-slide")
async def explain_slide(body: ExplainIn):
    """Explain one slide, grounded in that slide plus its immediate neighbours.

    Neighbours are included deliberately: a slide mid-derivation is meaningless
    without the one before it, and a definition is often stated on the next.
    They are supplied as context but the answer must be about the chosen page.
    """
    async with acquire() as conn:
        src = await conn.fetchrow(
            "SELECT id, title, kind FROM sources WHERE id = $1", body.source_id
        )
        if src is None:
            raise HTTPException(404, "no such source")
        rows = await conn.fetch(
            """SELECT id, text, locator FROM chunks
               WHERE source_id = $1
                 AND COALESCE((locator->>'slide')::int, (locator->>'page')::int)
                     BETWEEN $2 - 1 AND $2 + 1
               ORDER BY ordinal""",
            body.source_id, body.page,
        )

    if not rows:
        raise HTTPException(404, f"no content found on page {body.page}")

    target, context = [], []
    for r in rows:
        loc = r["locator"] or {}
        page = loc.get("slide") or loc.get("page")
        (target if int(page) == body.page else context).append(r)

    if not target:
        raise HTTPException(404, f"no content on page {body.page}")

    excerpts = [
        (i + 1, f"{src['title']}, p.{body.page}", r["text"]) for i, r in enumerate(target)
    ]
    for i, r in enumerate(context):
        loc = r["locator"] or {}
        pg = loc.get("slide") or loc.get("page")
        excerpts.append((len(target) + i + 1, f"{src['title']}, p.{pg} (nearby)", r["text"]))

    system = prompts.answer_system(body.mode) + (
        "\n\nThe student is looking at one specific slide and wants it explained. "
        "Explain what that slide is saying and why it matters. Nearby slides are "
        "given only as context — do not drift onto their subject matter."
    )
    user = prompts.build_user_prompt(
        f"Explain what this slide is about, in your own words.", excerpts
    )

    answer = await complete(system, user, max_tokens=900)

    return {
        "answer": answer.strip(),
        "source_id": str(src["id"]),
        "source_title": src["title"],
        "page": body.page,
        "chunk_ids": [r["id"] for r in target],
    }
