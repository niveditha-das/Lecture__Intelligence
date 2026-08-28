"""extract -> chunk -> embed -> store, with status tracking on `sources`."""
from __future__ import annotations

import logging

from ..config import settings
from ..db import acquire, to_vector_literal
from ..retrieval.embeddings import embed_texts
from . import notes as notes_x
from . import pdf as pdf_x
from . import pptx as pptx_x
from .base import Block, Chunk
from .chunker import chunk_blocks

log = logging.getLogger(__name__)

EXTRACTORS = {"pdf": pdf_x.extract, "pptx": pptx_x.extract, "notes": notes_x.extract}


def extract_blocks(kind: str, path: str) -> list[Block]:
    if kind == "audio":
        from .audio import transcribe          # imported lazily: heavy model

        return transcribe(path)
    try:
        return EXTRACTORS[kind](path)
    except KeyError:
        raise ValueError(f"unsupported source kind: {kind}") from None


async def ingest_source(source_id: str) -> int:
    """Process one source end to end. Returns the number of chunks written."""
    async with acquire() as conn:
        row = await conn.fetchrow(
            "SELECT id, course_id, kind, week, storage_uri FROM sources WHERE id=$1",
            source_id,
        )
        if row is None:
            raise ValueError(f"no such source {source_id}")
        await conn.execute(
            "UPDATE sources SET status='processing', error=NULL WHERE id=$1", source_id
        )

    try:
        s = settings()
        blocks = extract_blocks(row["kind"], row["storage_uri"])
        chunks = chunk_blocks(blocks, s.chunk_target_tokens, s.chunk_overlap_tokens)
        if not chunks:
            raise ValueError("no extractable text found")

        vectors = await embed_texts([c.text for c in chunks])
        for c, v in zip(chunks, vectors):
            c.embedding = v

        await _store(str(row["id"]), str(row["course_id"]), row["week"], chunks)

        async with acquire() as conn:
            await conn.execute(
                "UPDATE sources SET status='ready', meta = meta || $2::jsonb WHERE id=$1",
                source_id,
                {"n_blocks": len(blocks), "n_chunks": len(chunks)},
            )
        log.info("ingested %s: %d blocks -> %d chunks", source_id, len(blocks), len(chunks))
        return len(chunks)

    except Exception as exc:
        log.exception("ingest failed for %s", source_id)
        async with acquire() as conn:
            await conn.execute(
                "UPDATE sources SET status='failed', error=$2 WHERE id=$1",
                source_id, f"{type(exc).__name__}: {exc}"[:500],
            )
        raise


async def _store(source_id: str, course_id: str, week: int | None, chunks: list[Chunk]) -> None:
    async with acquire() as conn:
        async with conn.transaction():
            await conn.execute("DELETE FROM chunks WHERE source_id=$1", source_id)
            await conn.executemany(
                """
                INSERT INTO chunks
                    (source_id, course_id, week, ordinal, text, n_tokens, locator, embedding)
                VALUES ($1, $2, $3, $4, $5, $6, $7::jsonb, $8::vector)
                """,
                [
                    (
                        source_id, course_id, week, c.ordinal, c.text, c.n_tokens,
                        c.locator, to_vector_literal(c.embedding or []),
                    )
                    for c in chunks
                ],
            )
