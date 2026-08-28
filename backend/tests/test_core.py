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


# --- mastery model ------------------------------------------------------
from app.study.scoring import (  # noqa: E402
    half_life_days, k_factor, retention, sigmoid, update_theta, urgency,
)


def test_correct_answer_raises_theta_wrong_lowers_it():
    up = update_theta(0.0, 0.0, True, 0)
    down = update_theta(0.0, 0.0, False, 0)
    assert up > 0.0 > down
    # A 50/50 question moves ability by exactly K/2 either way.
    assert abs(up - 0.3) < 1e-6 and abs(down + 0.3) < 1e-6


def test_easy_question_teaches_less_than_a_hard_one():
    """Getting an easy question right is weak evidence; a hard one is strong."""
    easy = update_theta(0.0, -1.5, True, 0) - 0.0
    hard = update_theta(0.0, 1.5, True, 0) - 0.0
    assert hard > easy > 0


def test_k_factor_decays_with_experience():
    assert k_factor(0) > k_factor(5) > k_factor(50)
    assert k_factor(10_000) > 0.14


def test_theta_converges_towards_true_ability():
    """Simulate a student whose real ability is 1.0 and check the estimate finds it.

    Questions are drawn across a difficulty range and answered correctly with
    probability sigmoid(true_ability - difficulty), which is the model's own
    assumption. If the update rule is right, theta should climb from 0 to near 1.
    """
    rng = np.random.default_rng(7)
    true_ability = 1.0
    theta = 0.0
    for i in range(400):
        b = float(rng.uniform(-1.5, 1.5))
        correct = rng.random() < sigmoid(true_ability - b)
        theta = update_theta(theta, b, correct, i)
    assert abs(theta - true_ability) < 0.5, theta


def test_theta_falls_for_a_struggling_student():
    rng = np.random.default_rng(11)
    theta = 0.0
    for i in range(400):
        b = float(rng.uniform(-1.5, 1.5))
        correct = rng.random() < sigmoid(-1.0 - b)   # true ability -1.0
        theta = update_theta(theta, b, correct, i)
    assert theta < -0.5, theta


def test_retention_decays_and_mastery_slows_the_decay():
    weak = retention(theta=-1.0, n_correct=0, days_since=7)
    strong = retention(theta=1.0, n_correct=5, days_since=7)
    assert 0.0 < weak < strong < 1.0
    assert retention(0.0, 0, 0) == 1.0


def test_half_life_grows_with_ability():
    assert half_life_days(1.0, 0) > half_life_days(0.0, 0) > half_life_days(-1.0, 0)


def test_never_assessed_topic_outranks_a_mastered_one():
    """A first plan must cover the whole course, not just known failures."""
    unseen = urgency(theta=0.0, n_correct=0, days_since=None, days_to_exam=7)
    mastered = urgency(theta=1.2, n_correct=8, days_since=1, days_to_exam=7)
    assert unseen > mastered


def test_weak_topic_outranks_strong_one_all_else_equal():
    weak = urgency(theta=-1.0, n_correct=0, days_since=5, days_to_exam=7)
    strong = urgency(theta=1.0, n_correct=6, days_since=5, days_to_exam=7)
    assert weak > strong
