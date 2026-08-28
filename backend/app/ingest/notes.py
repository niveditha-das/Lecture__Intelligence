"""Markdown / plain-text notes -> Blocks with line ranges + heading context."""
from __future__ import annotations

import re

from .base import Block

HEADING = re.compile(r"^(#{1,6})\s+(.*)$")


def extract(path: str) -> list[Block]:
    with open(path, encoding="utf-8", errors="replace") as fh:
        lines = fh.read().splitlines()

    blocks: list[Block] = []
    order = 0
    heading: str | None = None
    buf: list[str] = []
    start = 1

    def flush(end_line: int) -> None:
        nonlocal order, buf, start
        text = "\n".join(buf).strip()
        buf = []
        if len(text) < 3:
            return
        blocks.append(
            Block(
                text=text,
                locator={"line_start": start, "line_end": end_line},
                order=order,
                section=heading,
            )
        )
        order += 1

    for i, line in enumerate(lines, start=1):
        m = HEADING.match(line)
        if m:
            flush(i - 1)
            heading = m.group(2).strip()
            start = i
            buf = [line]
            continue
        if not line.strip():          # blank line = paragraph boundary
            flush(i - 1)
            start = i + 1
            continue
        if not buf:
            start = i
        buf.append(line)

    flush(len(lines))
    return blocks
