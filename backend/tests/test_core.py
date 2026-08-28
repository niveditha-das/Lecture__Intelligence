"""Unit tests for the parts that must never silently break.

Provenance is the product: if the chunker drops a bbox, every citation
downstream is a lie. These run without a database or an API key.
"""
from __future__ import annotations

import numpy as np
import pytest

from app.evaluation import metrics as M
from app.ingest.align import align
from app.ingest.base import Block
from app.ingest.chunker import chunk_blocks


def pdf_block(page: int, order: int, words: int = 30, y: float = 0.1) -> Block:
    return Block(
        text=" ".join(f"w{order}_{i}" for i in range(words)),
        locator={"page": page, "regions": [{"page": page, "bbox": [0.1, y, 0.9, y + 0.05]}]},
        order=order,
        section=f"p{page}",
    )


def test_every_chunk_keeps_a_renderable_locator():
    blocks = [pdf_block(1, i) for i in range(6)]
    chunks = chunk_blocks(blocks, target_tokens=120, overlap_tokens=20)
    assert chunks
    for c in chunks:
        assert c.locator["regions"], "chunk lost its bbox -> citation cannot render"
        assert c.locator["page"] == 1


def test_never_merges_across_pages():
    blocks = [pdf_block(1, 0), pdf_block(1, 1), pdf_block(2, 2), pdf_block(2, 3)]
    for c in chunk_blocks(blocks, target_tokens=10_000, overlap_tokens=0):
        pages = {r["page"] for r in c.locator["regions"]}
        assert len(pages) == 1, "a chunk spanning two pages cannot be cited precisely"


def test_oversized_block_is_split_but_keeps_its_page():
    big = pdf_block(3, 0, words=2000)
    chunks = chunk_blocks([big], target_tokens=200, overlap_tokens=0)
    assert len(chunks) > 1
    assert all(c.locator["page"] == 3 for c in chunks)


def test_chunking_terminates_and_covers_input():
    blocks = [pdf_block(1, i, words=200) for i in range(10)]
    chunks = chunk_blocks(blocks, target_tokens=150, overlap_tokens=100)
    assert 0 < len(chunks) < 200          # overlap must not cause runaway growth
    assert "w0_0" in chunks[0].text


def test_transcript_segments_map_to_slides_monotonically():
    rng = np.random.default_rng(0)
    slides = rng.normal(size=(4, 8))
    # 3 segments per slide, in order, with noise
    segs = np.vstack([slides[i] + 0.1 * rng.normal(size=(3, 8)) for i in range(4)])
    path = align(segs, slides)
    assert path == sorted(path), "alignment must be non-decreasing"
    assert path[0] == 0 and path[-1] == 3


@pytest.mark.parametrize(
    "retrieved,gold,k,expected",
    [([1, 2, 3], [2], 3, 1.0), ([1, 2, 3], [9], 3, 0.0), ([1, 2, 3], [2, 9], 3, 0.5)],
)
def test_recall_at_k(retrieved, gold, k, expected):
    assert M.recall_at_k(retrieved, gold, k) == expected


def test_mrr_rewards_rank_one():
    assert M.mrr([5, 2, 3], [5]) == 1.0
    assert M.mrr([1, 5, 3], [5]) == 0.5
    assert M.mrr([1, 2, 3], [5]) == 0.0


def test_citation_precision_punishes_wrong_source():
    assert M.citation_precision([1, 2], [1, 2]) == 1.0
    assert M.citation_precision([1, 9], [1, 2]) == 0.5
