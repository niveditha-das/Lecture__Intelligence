"""Thin asyncpg wrapper.

Embeddings are passed as pgvector *text literals* and cast in SQL (`$1::vector`).
That avoids depending on codec registration and works identically for
vector/halfvec if you later switch the column type.
"""
from __future__ import annotations

import json
from collections.abc import AsyncIterator, Sequence
from contextlib import asynccontextmanager

import asyncpg

from .config import settings

_pool: asyncpg.Pool | None = None


async def init_pool() -> asyncpg.Pool:
    global _pool
    if _pool is None:
        _pool = await asyncpg.create_pool(
            settings().database_url,
            min_size=1,
            max_size=10,
            init=_init_conn,
        )
    return _pool


async def _init_conn(conn: asyncpg.Connection) -> None:
    # let us read/write jsonb columns as python dicts
    await conn.set_type_codec(
        "jsonb", encoder=json.dumps, decoder=json.loads, schema="pg_catalog"
    )


async def close_pool() -> None:
    global _pool
    if _pool is not None:
        await _pool.close()
        _pool = None


def pool() -> asyncpg.Pool:
    if _pool is None:
        raise RuntimeError("pool not initialised; call init_pool() on startup")
    return _pool


@asynccontextmanager
async def acquire() -> AsyncIterator[asyncpg.Connection]:
    async with pool().acquire() as conn:
        yield conn


def to_vector_literal(vec: Sequence[float]) -> str:
    """[0.1, 0.2] -> '[0.1,0.2]' (pgvector's text input format)."""
    return "[" + ",".join(f"{float(x):.6f}" for x in vec) + "]"
