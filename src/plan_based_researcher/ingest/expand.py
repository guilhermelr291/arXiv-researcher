"""Expand packed chunk hits into Writer excerpt strings (RETR-07, RETR-09)."""

from __future__ import annotations

import re

from plan_based_researcher.ingest.labels import equation_label, table_label, table_number_for
from plan_based_researcher.ports.chunks import ChunkRecord

_PLACEHOLDER = re.compile(r"\[(TABLE|EQUATION):([^\]]+)\]")
_ATOMIC_KINDS = frozenset({"table", "equation"})

__all__ = ["expand_hits"]


def expand_hits(packed: list[ChunkRecord], corpus: list[ChunkRecord]) -> list[str]:
    """Return one excerpt per packed hit: full unit body once, then labels."""
    units: dict[str, ChunkRecord] = {}
    for chunk in corpus:
        if chunk.kind in _ATOMIC_KINDS and chunk.unit_id and chunk.unit_id not in units:
            units[chunk.unit_id] = chunk

    shown: set[str] = set()
    excerpts: list[str] = []
    for hit in packed:
        if hit.kind in _ATOMIC_KINDS:
            section = hit.metadata.get("section") or ""
            excerpts.append(f"{section}\n{hit.content}" if section else hit.content)
            if hit.unit_id is not None:
                shown.add(hit.unit_id)
            continue
        excerpts.append(_expand_prose(hit.content, units, shown))
    return excerpts


def _expand_prose(
    content: str, units: dict[str, ChunkRecord], shown: set[str]
) -> str:
    def replace(match: re.Match[str]) -> str:
        kind, unit_id = match.group(1), match.group(2)
        unit = units.get(unit_id)
        if unit is not None and unit_id not in shown:
            shown.add(unit_id)
            return unit.content
        if unit is None:
            return match.group(0)
        return _label_for(kind, unit)

    return _PLACEHOLDER.sub(replace, content)


def _label_for(kind: str, unit: ChunkRecord) -> str:
    caption = unit.metadata.get("caption") or ""
    if kind == "EQUATION":
        return equation_label(caption)
    number = table_number_for(tag="", caption=caption, index_among_tables=1)
    return table_label(number, caption)
