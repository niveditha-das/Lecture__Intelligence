"""Embeddings behind one interface so the eval harness can A/B providers.

Both defaults are 1024-dim, matching `vector(1024)` in the schema:
  openai -> text-embedding-3-large with dimensions=1024
  local  -> BAAI/bge-m3 (sentence-transformers, CPU-friendly)
"""
from __future__ import annotations

import asyncio

from ..config import settings

_local_model = None


def _load_local():
    global _local_model
    if _local_model is None:
        from sentence_transformers import SentenceTransformer

        _local_model = SentenceTransformer("BAAI/bge-m3")
    return _local_model


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
