"""PDF -> Blocks, keeping page number and a *normalised* bbox for every block.

bbox is stored as [x0, y0, x1, y1] in 0..1 page-relative coordinates so the
frontend can draw the highlight at any render scale / DPI without knowing the
original page size.
"""
from __future__ import annotations

import fitz  # PyMuPDF

from .base import Block

MIN_CHARS = 3


def extract(path: str) -> list[Block]:
    doc = fitz.open(path)
    blocks: list[Block] = []
    order = 0
    try:
        for pno, page in enumerate(doc, start=1):
            w, h = page.rect.width, page.rect.height
            if w <= 0 or h <= 0:
                continue
            # sort=True gives natural reading order (handles 2-column slides)
            page_dict = page.get_text("dict", sort=True)
            for blk in page_dict.get("blocks", []):
                if blk.get("type") != 0:  # 0 = text, 1 = image
                    continue
                text = "\n".join(
                    "".join(span["text"] for span in line.get("spans", []))
                    for line in blk.get("lines", [])
                ).strip()
                if len(text) < MIN_CHARS:
                    continue
                x0, y0, x1, y1 = blk["bbox"]
                bbox = [
                    round(max(0.0, x0 / w), 4),
                    round(max(0.0, y0 / h), 4),
                    round(min(1.0, x1 / w), 4),
                    round(min(1.0, y1 / h), 4),
                ]
                blocks.append(
                    Block(
                        text=text,
                        locator={"page": pno, "regions": [{"page": pno, "bbox": bbox}]},
                        order=order,
                        section=f"p{pno}",  # never merge across pages
                    )
                )
                order += 1
    finally:
        doc.close()
    return blocks


def page_count(path: str) -> int:
    doc = fitz.open(path)
    try:
        return doc.page_count
    finally:
        doc.close()


def render_page(path: str, page_no: int, dpi: int = 144) -> bytes:
    """PNG of one page — used by the citation viewer endpoint."""
    doc = fitz.open(path)
    try:
        page = doc.load_page(page_no - 1)
        return page.get_pixmap(dpi=dpi).tobytes("png")
    finally:
        doc.close()
