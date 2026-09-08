"""Equation and table labels for ingest embedding_text and retrieve expansion (EMB-02, RETR-07)."""

from __future__ import annotations

import re

__all__ = ["equation_label", "table_label", "table_number_for"]

_LEADING_TABLE = re.compile(r"(?i)^Table\s+(\S+)")
_TRAILING_PUNCT = ".,:;)]}"


def equation_label(tag: str) -> str:
    """Return ``Equation ({tag})`` when tag is set, otherwise ``Equation``."""
    if tag:
        return f"Equation ({tag})"
    return "Equation"


def table_label(number: str, caption: str) -> str:
    """Format a table label, using caption as-is when it already starts with Table."""
    if not caption:
        return f"Table {number}"
    if caption.lower().startswith("table"):
        return caption
    return f"Table {number}: {caption}"


def table_number_for(*, tag: str, caption: str, index_among_tables: int) -> str:
    """Prefer tag, else a leading ``Table <token>`` in caption, else the 1-based index."""
    if tag:
        return tag
    match = _LEADING_TABLE.match(caption)
    if match:
        return match.group(1).rstrip(_TRAILING_PUNCT)
    return str(index_among_tables)
