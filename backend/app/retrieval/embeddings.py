"""Embeddings behind one interface so the eval harness can A/B providers.

Both defaults are 1024-dim, matching `vector(1024)` in the schema:
  openai -> text-embedding-3-large with dimensions=1024
  local  -> BAAI/bge-m3 (sentence-transformers, CPU-friendly)
"""
from __future__ import annotations

import asyncio
import threading

from ..config import settings

_local_model = None
# Without this lock, concurrent requests each see `_local_model is None` and every
# one of them starts building its own copy of a 568M model. Memory runs out
# mid-load and torch leaves the weights on the meta device, which surfaces as
# "Cannot copy out of meta tensor". One loader, everyone else waits.
_load_lock = threading.Lock()


def _load_local():
    global _local_model
    if _local_model is None:
        with _load_lock:
            if _local_model is None:          # re-check: another thread may have won
                from sentence_transformers import SentenceTransformer

                _local_model = SentenceTransformer("BAAI/bge-m3")
    return _local_model


async def warm() -> None:
    """Load the embedding model at startup so no request races to build it."""
    if settings().embedding_provider != "openai":
        await asyncio.to_thread(_load_local)


async def embed_texts(texts: list[str], *, is_query: bool = False) -> list[list[float]]:
    if not texts:
        return []
    s = settings()
    if s.embedding_provider == "openai":
        return await _embed_openai(texts, s)
    return await asyncio.to_thread(_embed_local, texts, is_query)


async def embed_query(text: str) -> list[float]:
    return (await embed_texts([text], is_query=True))[0]


async def _embed_openai(texts: list[str], s) -> list[list[float]]:
    from openai import AsyncOpenAI

    client = AsyncOpenAI(api_key=s.openai_api_key)
    out: list[list[float]] = []
    for i in range(0, len(texts), 128):                     # batch
        resp = await client.embeddings.create(
            model=s.embedding_model,
            input=texts[i : i + 128],
            dimensions=s.embedding_dim,
        )
        out.extend(d.embedding for d in resp.data)
    return out


def _embed_local(texts: list[str], is_query: bool) -> list[list[float]]:
    model = _load_local()
    # bge-m3 wants no prefix; bge-large-en would want "Represent this sentence..."
    vecs = model.encode(texts, normalize_embeddings=True, batch_size=16)
    return [v.tolist() for v in vecs]
