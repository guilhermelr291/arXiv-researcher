"""Heading-aware 512/50 chunk drafts from a parsed paper (SPLIT-01, EMB-02)."""

from __future__ import annotations

import re
from typing import Literal

import tiktoken
from langchain_text_splitters import (
    MarkdownHeaderTextSplitter,
    RecursiveCharacterTextSplitter,
)
from tiktoken import Encoding

from plan_based_researcher.ingest.html_parse import ParsedPaper, ParsedUnit
from plan_based_researcher.ingest.labels import equation_label, table_label
from plan_based_researcher.policy import Policy
from plan_based_researcher.ports.chunks import ChunkDraft

__all__ = ["build_chunk_drafts"]

_PLACEHOLDER = re.compile(r"\[(TABLE|EQUATION):([^\]]+)\]")
_TABLE_SEPARATOR = re.compile(r"^\s*\|?\s*:?-{3,}:?(?:\s*\|\s*:?-{3,}:?)*\s*\|?\s*$")
_HEADER_KEYS = (
    "Header 1",
    "Header 2",
    "Header 3",
    "Header 4",
    "Header 5",
    "Header 6",
)
_HEADER_SPLITTER = MarkdownHeaderTextSplitter(
    headers_to_split_on=[
        ("#", "Header 1"),
        ("##", "Header 2"),
        ("###", "Header 3"),
        ("####", "Header 4"),
        ("#####", "Header 5"),
        ("######", "Header 6"),
    ],
    strip_headers=True,
)
_EQUATION_WINDOW_TOKENS = 200
_Kind = Literal["prose", "table", "equation"]


def build_chunk_drafts(parsed: ParsedPaper) -> list[ChunkDraft]:
    """Return ordered prose then atomic ChunkDraft rows; empty if unusable."""
    if not parsed.usable:
        return []

    enc = tiktoken.get_encoding(Policy.chunk_encoding)
    splitter = RecursiveCharacterTextSplitter.from_tiktoken_encoder(
        encoding_name=Policy.chunk_encoding,
        chunk_size=Policy.chunk_size,
        chunk_overlap=Policy.chunk_overlap,
        disallowed_special=(),
    )
    units_by_id: dict[str, ParsedUnit] = {}
    for unit in parsed.units:
        units_by_id.setdefault(unit.html_id, unit)

    sections = [
        (_section_from_metadata(doc.metadata), doc.page_content)
        for doc in _HEADER_SPLITTER.split_text(parsed.prose_markdown)
    ]
    drafts: list[ChunkDraft] = []
    for section, text in sections:
        for piece in _split_section(text, enc, splitter):
            drafts.append(_prose_draft(piece, section, units_by_id))
    for unit in parsed.units:
        drafts.append(_atomic_draft(unit, sections, parsed.prose_markdown, enc))
    return drafts


def _split_section(
    text: str,
    enc: Encoding,
    splitter: RecursiveCharacterTextSplitter,
) -> list[str]:
    if len(_token_ids(enc, text)) > Policy.chunk_size:
        return splitter.split_text(text)
    return [text]


def _prose_draft(
    content: str,
    section: str,
    units_by_id: dict[str, ParsedUnit],
) -> ChunkDraft:
    return _draft(
        kind="prose",
        unit_id=None,
        embedding_text=_replace_placeholders(content, units_by_id),
        content=content,
        section=section,
        caption="",
        unit_ids=_placeholder_ids(content),
    )


def _atomic_draft(
    unit: ParsedUnit,
    sections: list[tuple[str, str]],
    prose_markdown: str,
    enc: Encoding,
) -> ChunkDraft:
    section, section_text = _containing_section(
        unit.html_id, unit.kind, sections, prose_markdown
    )
    if unit.kind == "table":
        label = table_label(unit.table_number, unit.caption)
        embedding_text = _table_embedding_text(unit.caption, unit.body)
    else:
        label = equation_label(unit.caption)
        window = _centered_window(
            section_text,
            f"[EQUATION:{unit.html_id}]",
            enc,
        )
        embedding_text = "\n".join((section, window, label, unit.body))
    return _draft(
        kind=unit.kind,
        unit_id=unit.html_id,
        embedding_text=embedding_text,
        content=f"{label}\n{unit.body}",
        section=section,
        caption=unit.caption,
        unit_ids=[unit.html_id],
    )


def _containing_section(
    html_id: str,
    kind: str,
    sections: list[tuple[str, str]],
    prose_markdown: str,
) -> tuple[str, str]:
    needle = f"[{kind.upper()}:{html_id}]"
    for section, text in sections:
        if needle in text:
            return section, text
    for section, text in sections:
        if section == Policy.PREAMBLE_SECTION:
            return Policy.PREAMBLE_SECTION, text
    return Policy.PREAMBLE_SECTION, prose_markdown


def _centered_window(text: str, placeholder: str, enc: Encoding) -> str:
    idx = text.find(placeholder)
    if idx < 0:
        ids = _token_ids(enc, text)
        return enc.decode(ids[: min(len(ids), _EQUATION_WINDOW_TOKENS)])
    left_ids = _token_ids(enc, text[:idx])
    placeholder_ids = _token_ids(enc, placeholder)
    right_ids = _token_ids(enc, text[idx + len(placeholder) :])
    all_ids = left_ids + placeholder_ids + right_ids
    total = len(all_ids)
    window = min(total, _EQUATION_WINDOW_TOKENS)
    if window == 0:
        return ""
    span_start = len(left_ids)
    span_end = span_start + len(placeholder_ids)
    mid = (span_start + span_end) / 2
    start = int(mid - window / 2)
    start = max(0, min(start, total - window))
    return enc.decode(all_ids[start : start + window])


def _table_embedding_text(caption: str, body: str) -> str:
    nonempty = [line for line in body.splitlines() if line.strip()]
    sep_at = next(
        (i for i, line in enumerate(nonempty) if _is_table_separator(line)),
        None,
    )
    if (
        sep_at is None
        or sep_at == 0
        or "|" not in nonempty[sep_at - 1]
    ):
        rows = nonempty[:3]
    else:
        data = [
            line
            for line in nonempty[sep_at + 1 :]
            if not _is_table_separator(line)
        ][:2]
        rows = [nonempty[sep_at - 1], *data]
    return "\n".join(part for part in [caption, *rows] if part)


def _is_table_separator(line: str) -> bool:
    stripped = line.strip()
    if "-" not in stripped:
        return False
    return _TABLE_SEPARATOR.fullmatch(stripped) is not None


def _section_from_metadata(metadata: dict) -> str:
    parts = [str(metadata[key]) for key in _HEADER_KEYS if metadata.get(key)]
    return " > ".join(parts) if parts else Policy.PREAMBLE_SECTION


def _placeholder_ids(content: str) -> list[str]:
    seen: set[str] = set()
    ids: list[str] = []
    for match in _PLACEHOLDER.finditer(content):
        html_id = match.group(2)
        if html_id not in seen:
            seen.add(html_id)
            ids.append(html_id)
    return ids


def _replace_placeholders(content: str, units_by_id: dict[str, ParsedUnit]) -> str:
    def repl(match: re.Match[str]) -> str:
        unit = units_by_id.get(match.group(2))
        if unit is None:
            return match.group(0)
        if unit.kind == "table":
            return table_label(unit.table_number, unit.caption)
        if unit.kind == "equation":
            return equation_label(unit.caption)
        return match.group(0)

    return _PLACEHOLDER.sub(repl, content)


def _token_ids(enc: Encoding, text: str) -> list[int]:
    return enc.encode(text, disallowed_special=())


def _draft(
    *,
    kind: _Kind,
    unit_id: str | None,
    embedding_text: str,
    content: str,
    section: str,
    caption: str,
    unit_ids: list[str],
) -> ChunkDraft:
    return ChunkDraft(
        kind=kind,
        unit_id=None if unit_id is None else _strip_nul(unit_id),
        embedding_text=_strip_nul(embedding_text),
        content=_strip_nul(content),
        metadata={
            "section": _strip_nul(section),
            "caption": _strip_nul(caption),
            "unit_ids": [_strip_nul(item) for item in unit_ids],
        },
    )


def _strip_nul(value: str) -> str:
    return value.replace("\x00", "")
