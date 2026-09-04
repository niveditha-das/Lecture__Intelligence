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
    ".webm": "audio", ".ogg": "audio", ".flac": "audio",
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
# --- append to backend/app/routers/sources.py -----------------------------


@router.delete("/sources/{source_id}")
async def delete_source(source_id: str, keep_file: bool = False):
    """Remove a source and everything derived from it.

    Chunks cascade on the foreign key. The original file is deleted too unless
    asked otherwise — keeping orphaned uploads around would quietly fill the
    volume with files nothing references.
    """
    async with acquire() as conn:
        row = await conn.fetchrow(
            "SELECT storage_uri, title FROM sources WHERE id = $1", source_id
        )
        if row is None:
            raise HTTPException(404, "no such source")
        n_chunks = await conn.fetchval(
            "SELECT count(*) FROM chunks WHERE source_id = $1", source_id
        )
        await conn.execute("DELETE FROM sources WHERE id = $1", source_id)

    if not keep_file:
        try:
            os.remove(row["storage_uri"])
        except OSError:
            pass  # already gone, or on object storage

    return {"deleted": row["title"], "chunks_removed": n_chunks}


@router.post("/sources/{source_id}/reingest")
async def reingest_source(source_id: str, background: BackgroundTasks):
    """Re-run extraction on a source — after a chunker change, or a failure."""
    async with acquire() as conn:
        row = await conn.fetchrow("SELECT id FROM sources WHERE id = $1", source_id)
    if row is None:
        raise HTTPException(404, "no such source")
    background.add_task(_safe_ingest, source_id)
    return {"status": "pending"}


@router.patch("/sources/{source_id}")
async def update_source(source_id: str, title: str | None = None, week: int | None = None):
    async with acquire() as conn:
        row = await conn.fetchrow(
            """UPDATE sources
               SET title = COALESCE($2, title), week = COALESCE($3, week)
               WHERE id = $1 RETURNING id, title, week""",
            source_id, title, week,
        )
    if row is None:
        raise HTTPException(404, "no such source")
    return dict(row)


@router.get("/sources/{source_id}/transcript.txt")
async def source_transcript(source_id: str):
    """Plain-text transcript of a recording, with timestamps.

    Rebuilt from the stored chunks rather than kept as a separate artifact, so
    it can never drift from what the retriever actually searches.
    """
    async with acquire() as conn:
        src = await conn.fetchrow("SELECT title, kind FROM sources WHERE id = $1", source_id)
        if src is None:
            raise HTTPException(404, "no such source")
        rows = await conn.fetch(
            "SELECT text, locator FROM chunks WHERE source_id = $1 ORDER BY ordinal",
            source_id,
        )

    lines = [src["title"], "=" * len(src["title"]), ""]
    for r in rows:
        t = (r["locator"] or {}).get("t_start")
        if t is not None:
            m, s = divmod(int(t), 60)
            lines.append(f"[{m:02d}:{s:02d}] {r['text']}")
        else:
            lines.append(r["text"])
        lines.append("")

    return Response(
        "\n".join(lines),
        media_type="text/plain",
        headers={"content-disposition": f'attachment; filename="{source_id[:8]}-transcript.txt"'},
    )


@router.delete("/courses/{course_id}")
async def delete_course(course_id: str):
    async with acquire() as conn:
        row = await conn.fetchrow("SELECT name FROM courses WHERE id = $1", course_id)
        if row is None:
            raise HTTPException(404, "no such course")
        files = await conn.fetch("SELECT storage_uri FROM sources WHERE course_id = $1", course_id)
        await conn.execute("DELETE FROM courses WHERE id = $1", course_id)

    for f in files:
        try:
            os.remove(f["storage_uri"])
        except OSError:
            pass
    return {"deleted": row["name"], "files_removed": len(files)}
