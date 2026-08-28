"""Ingestion primitives.

RULE OF THE PROJECT: provenance is atomic. Every extractor emits `Block`s that
already know exactly where they came from, and the chunker may only *merge*
blocks — never invent, drop or blur a locator. If a bbox/timestamp is lost at
extraction time you can never render a citation for it later without
re-ingesting the whole corpus.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


def approx_tokens(text: str) -> int:
    """Cheap token estimate (~1.3 tokens/word). Good enough for chunk budgets."""
    return max(1, int(len(text.split()) * 1.3))


@dataclass
class Block:
    """Smallest unit an extractor can point at: a PDF text block, a PPTX shape,
    a transcript segment, a markdown paragraph."""

    text: str
    locator: dict[str, Any]
    order: int          # reading order within the source
    section: str | None = None   # optional hard boundary (page/slide/heading)

    @property
    def tokens(self) -> int:
        return approx_tokens(self.text)


@dataclass
class Chunk:
    """A retrievable unit. `locator` is the union of its blocks' locators."""

    text: str
    locator: dict[str, Any]
    ordinal: int
    n_tokens: int = 0
    embedding: list[float] | None = None
    meta: dict[str, Any] = field(default_factory=dict)


def merge_locators(blocks: list[Block]) -> dict[str, Any]:
    """Union block locators into one renderable citation target."""
    out: dict[str, Any] = {}
    regions = [r for b in blocks for r in b.locator.get("regions", [])]
    if regions:
        out["regions"] = regions
        out["page"] = regions[0]["page"]
        pages = sorted({r["page"] for r in regions})
        if len(pages) > 1:
            out["pages"] = pages

    slides = sorted({b.locator["slide"] for b in blocks if "slide" in b.locator})
    if slides:
        out["slide"] = slides[0]
        if len(slides) > 1:
            out["slides"] = slides
        shapes = [s for b in blocks for s in b.locator.get("shapes", [])]
        if shapes:
            out["shapes"] = shapes

    starts = [b.locator["t_start"] for b in blocks if "t_start" in b.locator]
    if starts:
        out["t_start"] = min(starts)
        out["t_end"] = max(b.locator["t_end"] for b in blocks if "t_end" in b.locator)

    lines = [b.locator["line_start"] for b in blocks if "line_start" in b.locator]
    if lines:
        out["line_start"] = min(lines)
        out["line_end"] = max(b.locator["line_end"] for b in blocks if "line_end" in b.locator)

    headings = [b.section for b in blocks if b.section]
    if headings:
        out["section"] = headings[0]
    return out
