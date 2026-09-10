"""Originals must be kept: citations render the actual page/slide/audio.

Local disk today, S3/R2 tomorrow — same two functions.
"""
from __future__ import annotations

import os
import re
import uuid

from .config import settings

SAFE = re.compile(r"[^A-Za-z0-9._-]+")


def _root() -> str:
    root = settings().storage_dir
    os.makedirs(root, exist_ok=True)
    return root


def save(data: bytes, filename: str) -> str:
    """Store the file and return its *key*, not an absolute path.

    An absolute path baked into the database breaks the moment the app moves
    between environments — uploads made while running on the host recorded
    /Users/... paths that a container could not open, so every citation failed
    to render. A key resolved against STORAGE_DIR at read time survives the
    move, and is the same shape a key in S3 or R2 would take.
    """
    name = SAFE.sub("_", os.path.basename(filename))[-120:]
    key = f"{uuid.uuid4().hex[:12]}_{name}"
    with open(os.path.join(_root(), key), "wb") as fh:
        fh.write(data)
    return key


def resolve(uri: str) -> str:
    """Accept a bare key or a legacy absolute path; return a readable path."""
    if os.path.isabs(uri) and os.path.exists(uri):
        return uri
    return os.path.join(_root(), os.path.basename(uri))


def read(uri: str) -> bytes:
    with open(resolve(uri), "rb") as fh:
        return fh.read()
