"""Metrics. Deliberately boring and unit-testable — they are the product."""
from __future__ import annotations


def recall_at_k(retrieved: list[int], gold: list[int], k: int) -> float:
    """Fraction of gold chunks appearing in the top-k."""
    if not gold:
        return float("nan")
    top = set(retrieved[:k])
    return len([g for g in gold if g in top]) / len(gold)


def hit_at_k(retrieved: list[int], gold: list[int], k: int) -> float:
    if not gold:
        return float("nan")
    return 1.0 if set(retrieved[:k]) & set(gold) else 0.0


def mrr(retrieved: list[int], gold: list[int]) -> float:
    """Reciprocal rank of the first gold chunk. Punishes burying the answer at #9."""
    if not gold:
        return float("nan")
    goldset = set(gold)
    for i, cid in enumerate(retrieved, start=1):
        if cid in goldset:
            return 1.0 / i
    return 0.0


def citation_precision(cited: list[int], gold: list[int]) -> float:
    """Of the chunks the model actually cited, how many were correct sources?

    This is the one recruiters care about: a fluent answer citing the wrong
    slide is worse than no answer.
    """
    if not cited:
        return float("nan")
    goldset = set(gold)
    return len([c for c in cited if c in goldset]) / len(cited)


def mean(xs: list[float]) -> float | None:
    vals = [x for x in xs if x == x]           # drop NaN
    return round(sum(vals) / len(vals), 4) if vals else None
