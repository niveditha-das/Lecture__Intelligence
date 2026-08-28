from __future__ import annotations

import os

from fastapi import APIRouter, BackgroundTasks, File, Form, HTTPException, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel

from .. import storage
from ..db import acquire
from ..ingest.pdf import render_page
from ..ingest.pipeline import ingest_source

router = APIRouter(tags=["ingestion"])

EXT_KIND = {
    ".pdf": "pdf", ".pptx": "pptx", ".ppt": "pptx",
    ".md": "notes", ".txt": "notes",
    ".mp3": "audio", ".m4a": "audio", ".wav": "audio", ".mp4": "audio",
}


class CourseIn(BaseModel):
    name: str


@router.post("/courses")
async def create_course(body: CourseIn):
    async with acquire() as conn:
        row = await conn.fetchrow(
            "INSERT INTO courses (name) VALUES ($1) RETURNING id, name", body.name
        )
    return dict(row)


@router.get("/courses")
async def list_courses():
    async with acquire() as conn:
        rows = await conn.fetch("SELECT id, name, created_at FROM courses ORDER BY created_at")
    return [dict(r) for r in rows]


@router.post("/sources")
async def upload_source(
    background: BackgroundTasks,
    course_id: str = Form(...),
    file: UploadFile = File(...),
    title: str | None = Form(None),
    week: int | None = Form(None),
):
    ext = os.path.splitext(file.filename or "")[1].lower()
    kind = EXT_KIND.get(ext)
    if kind is None:
        raise HTTPException(415, f"unsupported file type '{ext}'")

    uri = storage.save(await file.read(), file.filename or "upload")

    async with acquire() as conn:
        row = await conn.fetchrow(
            """INSERT INTO sources (course_id, kind, title, week, storage_uri)
               VALUES ($1,$2,$3,$4,$5) RETURNING id, status""",
            course_id, kind, title or (file.filename or "untitled"), week, uri,
        )

    # NOTE: fine for PDFs; move audio to a real queue (arq/Celery) before deploying.
    background.add_task(_safe_ingest, str(row["id"]))
    return {"id": str(row["id"]), "kind": kind, "status": "pending"}


async def _safe_ingest(source_id: str) -> None:
    try:
        await ingest_source(source_id)
    except Exception:
        pass  # status/error already persisted on the row


@router.get("/sources")
async def list_sources(course_id: str | None = None):
    async with acquire() as conn:
        rows = await conn.fetch(
            """SELECT id, course_id, kind, title, week, status, error, meta, created_at
               FROM sources WHERE ($1::uuid IS NULL OR course_id=$1::uuid)
               ORDER BY week NULLS LAST, created_at""",
            course_id,
        )
    return [dict(r) for r in rows]


@router.get("/sources/{source_id}/page/{page_no}.png")
async def source_page(source_id: str, page_no: int, dpi: int = 144):
    """Rendered page behind a citation. The frontend overlays the bbox on top."""
    async with acquire() as conn:
        row = await conn.fetchrow("SELECT kind, storage_uri FROM sources WHERE id=$1", source_id)
    if row is None:
        raise HTTPException(404, "no such source")
    if row["kind"] != "pdf":
        raise HTTPException(400, "page rendering is only available for PDFs")
    return Response(render_page(row["storage_uri"], page_no, dpi), media_type="image/png")


@router.get("/sources/{source_id}/file")
async def source_file(source_id: str):
    async with acquire() as conn:
        row = await conn.fetchrow("SELECT kind, storage_uri FROM sources WHERE id=$1", source_id)
    if row is None:
        raise HTTPException(404, "no such source")
    media = {"audio": "audio/mpeg", "pdf": "application/pdf"}.get(row["kind"], "application/octet-stream")
    return Response(storage.read(row["storage_uri"]), media_type=media)
