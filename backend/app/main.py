from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .db import acquire, close_pool, init_pool
from .retrieval import embeddings, rerank
from .routers import ask, evaluation, slides, sources, study

logging.basicConfig(level=logging.INFO)


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_pool()
    warmup = asyncio.gather(
        asyncio.create_task(embeddings.warm()),
        asyncio.create_task(rerank.warm()),
    )
    yield
    warmup.cancel()
    await close_pool()


app = FastAPI(title="Lecture Intelligence Platform", version="0.1.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(sources.router)
app.include_router(ask.router)
app.include_router(evaluation.router)
app.include_router(study.router)
app.include_router(slides.router)


@app.get("/health")
async def health():
    async with acquire() as conn:
        chunks = await conn.fetchval("SELECT count(*) FROM chunks")
        ready = await conn.fetchval("SELECT count(*) FROM sources WHERE status='ready'")
    return {"ok": True, "chunks": chunks, "sources_ready": ready}
