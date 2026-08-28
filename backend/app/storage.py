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
    name = SAFE.sub("_", os.path.basename(filename))[-120:]
    key = f"{uuid.uuid4().hex[:12]}_{name}"
    path = os.path.join(_root(), key)
    with open(path, "wb") as fh:
        fh.write(data)
    return path


def read(uri: str) -> bytes:
    with open(uri, "rb") as fh:
        return fh.read()
