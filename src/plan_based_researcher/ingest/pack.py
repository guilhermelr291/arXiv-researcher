"""Pack overfetched ranked hits to at most k unique unit_id slots (RETR-08)."""

from __future__ import annotations

import re

from plan_based_researcher.ports.chunks import ChunkRecord

_PLACEHOLDER = re.compile(r"\[(TABLE|EQUATION):([^\]]+)\]")
_ATOMIC_KINDS = frozenset({"table", "equation"})

__all__ = ["pack_hits"]


def pack_hits(ranked: list[ChunkRecord], k: int) -> list[ChunkRecord]:
    """Keep the first k unique hits, dropping later atomics whose unit_id is covered."""
    covered: set[str] = set()
    kept: list[ChunkRecord] = []
    for chunk in ranked:
        if len(kept) == k:
            break
        if chunk.kind in _ATOMIC_KINDS:
            if chunk.unit_id in covered:
                continue
            kept.append(chunk)
            if chunk.unit_id is not None:
                covered.add(chunk.unit_id)
            continue
        kept.append(chunk)
        covered.update(match.group(2) for match in _PLACEHOLDER.finditer(chunk.content))
    return kept
