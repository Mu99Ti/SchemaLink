"""Hashing utilities for incremental sync."""

from __future__ import annotations

import hashlib


def content_hash(*parts: str) -> str:
    h = hashlib.sha256()
    for part in parts:
        h.update(part.encode())
    return h.hexdigest()[:16]
