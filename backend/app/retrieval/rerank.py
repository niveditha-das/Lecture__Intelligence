"""Cross-encoder reranking of fused candidates.

Bi-encoders score query and chunk independently; a cross-encoder reads the pair
together and is much better at "does this passage actually answer this?".
Expensive per pair, so it only ever sees the top ~40 candidates.

Measure this: run the eval suite with rerank_enabled true/false and put the
delta in your README. That comparison is the whole point of having a harness.
"""
from __future__ import annotations

import asyncio
import logging

from ..config import settings

log = logging.getLogger(__name__)
_models: dict[str, object] = {}


def _load(name: str | None = None):
    """Cache one CrossEncoder per model name so we can A/B them."""
    name = name or settings().rerank_model
    if name not in _models:
        from sentence_transformers import CrossEncoder

        _models[name] = CrossEncoder(name, max_length=512)
    return _models[name]


def _score(query: str, texts: list[str]) -> list[float]:
    model = _load()
    return [float(x) for x in model.predict([(query, t) for t in texts])]


async def rerank_hits(query: str, hits: list) -> list:
    try:
        scores = await asyncio.to_thread(_score, query, [h.text for h in hits])
    except Exception as exc:                      # model missing / OOM
        log.warning("rerank unavailable, falling back to RRF order: %s", exc)
        return hits
    for h, sc in zip(hits, scores):
        h.rerank_score = sc
    return sorted(hits, key=lambda h: h.rerank_score, reverse=True)


async def warm() -> None:
    """Load the cross-encoder at startup so the first request isn't slow."""
    await asyncio.to_thread(_load)
