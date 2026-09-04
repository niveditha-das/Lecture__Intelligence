"""Align a transcript to the slide deck it was recorded against.

A lecturer moves through slides in order, so segment -> slide is monotonically
non-decreasing. `align.py` solves that with a constrained DTW over the
similarity matrix; this module is the part that finds the two sides, feeds them
in, and writes the result back.

The payoff is bidirectional and shows up directly in citations:

  * a transcript chunk gains a slide number, so "what did the lecturer actually
    say about slide 23?" becomes answerable;
  * a slide chunk gains a timestamp, so a citation reads "Lecture 7, slide 23
    @ 06:52" and the player can seek there.

Alignment only runs when a deck and a recording share a course and week, which
is the only situation where the monotonic assumption holds.
"""
from __future__ import annotations

import logging

import numpy as np

from ..db import acquire
from .align import align, slide_time_ranges

log = logging.getLogger(__name__)

MIN_SEGMENTS = 4
MIN_SLIDES = 2


def _parse_vector(raw) -> list[float] | None:
    """pgvector comes back as a '[0.1,0.2]' string over asyncpg."""
    if raw is None:
        return None
    if isinstance(raw, (list, tuple)):
        return list(raw)
    try:
        return [float(x) for x in str(raw).strip("[]").split(",")]
    except ValueError:
        return None


async def align_audio_source(source_id: str) -> dict:
    async with acquire() as conn:
        src = await conn.fetchrow(
            "SELECT id, course_id, week, kind, title FROM sources WHERE id = $1", source_id
        )
        if src is None or src["kind"] != "audio":
            return {"aligned": False, "reason": "not an audio source"}

        segments = await conn.fetch(
            """SELECT id, ordinal, locator, embedding FROM chunks
               WHERE source_id = $1 ORDER BY ordinal""",
            source_id,
        )

        # The deck this recording was made against: same course, same week.
        deck = await conn.fetchrow(
            """SELECT id, title FROM sources
               WHERE course_id = $1 AND kind IN ('pdf','pptx') AND status = 'ready'
                 AND ($2::int IS NULL OR week = $2::int)
               ORDER BY created_at LIMIT 1""",
            src["course_id"], src["week"],
        )
        if deck is None:
            return {"aligned": False, "reason": "no slide deck for this week"}

        slides = await conn.fetch(
            """SELECT id, ordinal, locator, embedding FROM chunks
               WHERE source_id = $1 ORDER BY ordinal""",
            deck["id"],
        )

    seg_vecs, seg_ids, seg_times = [], [], []
    for r in segments:
        v = _parse_vector(r["embedding"])
        loc = r["locator"] or {}
        if v and "t_start" in loc:
            seg_vecs.append(v)
            seg_ids.append(r["id"])
            seg_times.append((float(loc["t_start"]), float(loc.get("t_end", loc["t_start"]))))

    slide_vecs, slide_ids, slide_pages = [], [], []
    for r in slides:
        v = _parse_vector(r["embedding"])
        loc = r["locator"] or {}
        page = loc.get("slide") or loc.get("page")
        if v and page:
            slide_vecs.append(v)
            slide_ids.append(r["id"])
            slide_pages.append(int(page))

    if len(seg_vecs) < MIN_SEGMENTS or len(slide_vecs) < MIN_SLIDES:
        return {"aligned": False, "reason": "not enough material to align"}

    path = align(np.array(seg_vecs), np.array(slide_vecs))

    # transcript chunk -> slide number
    seg_updates = [
        (seg_ids[i], slide_pages[path[i]])
        for i in range(len(seg_ids))
        if 0 <= path[i] < len(slide_pages)
    ]

    # slide chunk -> the span of time spent on it
    ranges = slide_time_ranges(path, seg_times, len(slide_ids))
    slide_updates = [
        (slide_ids[idx], round(t0, 2), round(t1, 2)) for idx, (t0, t1) in ranges.items()
    ]

    async with acquire() as conn:
        async with conn.transaction():
            await conn.executemany(
                """UPDATE chunks
                   SET locator = locator || jsonb_build_object('slide', $2::int)
                   WHERE id = $1""",
                seg_updates,
            )
            await conn.executemany(
                """UPDATE chunks
                   SET locator = locator || jsonb_build_object('t_start', $2::real,
                                                               't_end', $3::real)
                   WHERE id = $1""",
                slide_updates,
            )
            await conn.execute(
                """UPDATE sources SET meta = meta || jsonb_build_object(
                       'aligned_to', $2::text, 'aligned_segments', $3::int)
                   WHERE id = $1""",
                source_id, deck["title"], len(seg_updates),
            )

    log.info("aligned %s to %s: %d segments, %d slides timestamped",
             src["title"], deck["title"], len(seg_updates), len(slide_updates))

    return {
        "aligned": True,
        "deck": deck["title"],
        "segments_placed": len(seg_updates),
        "slides_timestamped": len(slide_updates),
        "slide_range": [min(slide_pages), max(slide_pages)] if slide_pages else None,
    }
