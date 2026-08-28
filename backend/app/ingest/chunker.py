"""Merge Blocks into Chunks under a token budget without losing provenance.

Rules:
  1. Never merge across a hard `section` boundary (page / slide / heading).
  2. Split blocks that are individually over budget, keeping the same locator.
  3. Overlap is taken from whole trailing blocks, so the overlapping region's
     locator stays truthful. A chunk never overlaps by its entire content.
"""
from __future__ import annotations

from .base import Block, Chunk, approx_tokens, merge_locators


def _split_oversized(block: Block, budget: int) -> list[Block]:
    if block.tokens <= budget:
        return [block]
    words = block.text.split()
    per = max(40, int(budget / 1.3))
    out: list[Block] = []
    for i in range(0, len(words), per):
        loc = dict(block.locator)
        loc["partial"] = True
        out.append(
            Block(
                text=" ".join(words[i : i + per]),
                locator=loc,
                order=block.order,
                section=block.section,
            )
        )
    return out


def _tail(buf: list[Block], overlap_tokens: int) -> list[Block]:
    """Trailing blocks worth ~overlap_tokens, never the whole buffer."""
    if len(buf) < 2 or overlap_tokens <= 0:
        return []
    carry: list[Block] = []
    total = 0
    for b in reversed(buf[1:]):
        if total >= overlap_tokens:
            break
        carry.insert(0, b)
        total += b.tokens
    return carry


def chunk_blocks(
    blocks: list[Block], target_tokens: int = 320, overlap_tokens: int = 60
) -> list[Chunk]:
    expanded: list[Block] = []
    for b in sorted(blocks, key=lambda x: x.order):
        expanded.extend(_split_oversized(b, target_tokens))

    chunks: list[Chunk] = []
    buf: list[Block] = []
    buf_tokens = 0

    def emit() -> None:
        if not buf:
            return
        text = "\n".join(b.text for b in buf).strip()
        if not text:
            return
        chunks.append(
            Chunk(
                text=text,
                locator=merge_locators(buf),
                ordinal=len(chunks),
                n_tokens=approx_tokens(text),
            )
        )

    prev_section: str | None = None
    for b in expanded:
        if buf and b.section != prev_section:          # hard boundary
            emit()
            buf, buf_tokens = [], 0
        elif buf and buf_tokens + b.tokens > target_tokens:
            emit()
            buf = _tail(buf, overlap_tokens)
            buf_tokens = sum(x.tokens for x in buf)
        buf.append(b)
        buf_tokens += b.tokens
        prev_section = b.section

    emit()
    return chunks
