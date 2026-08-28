"""Lecture audio -> Blocks carrying (t_start, t_end) so a citation can seek
the player to the exact moment the lecturer said it.

faster-whisper runs on CPU with int8 (~1x realtime for `small`). For anything
longer than ~20 min, move this behind the job queue (see app/jobs.py) or push
it to a GPU service — never run it inside a request handler.
"""
from __future__ import annotations

from .base import Block
from ..config import settings

_model = None


def _load():
    global _model
    if _model is None:
        from faster_whisper import WhisperModel

        s = settings()
        _model = WhisperModel(
            s.whisper_model, device="cpu", compute_type=s.whisper_compute_type
        )
    return _model


def transcribe(path: str, language: str | None = None) -> list[Block]:
    model = _load()
    segments, _info = model.transcribe(
        path,
        language=language,
        vad_filter=True,               # drop silence: fewer empty segments
        word_timestamps=False,         # segment-level is enough for citations
        beam_size=5,
    )

    blocks: list[Block] = []
    for order, seg in enumerate(segments):
        text = (seg.text or "").strip()
        if len(text) < 3:
            continue
        blocks.append(
            Block(
                text=text,
                locator={
                    "t_start": round(float(seg.start), 2),
                    "t_end": round(float(seg.end), 2),
                },
                order=order,
            )
        )
    return blocks


def fmt_timestamp(seconds: float) -> str:
    m, s = divmod(int(seconds), 60)
    h, m = divmod(m, 60)
    return f"{h:d}:{m:02d}:{s:02d}" if h else f"{m:d}:{s:02d}"
