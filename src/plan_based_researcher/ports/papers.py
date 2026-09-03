"""Outbound port for arXiv paper search and HTML/PDF load (ARX-01)."""

from dataclasses import dataclass
from datetime import datetime
from typing import Literal, Protocol

__all__ = ["HtmlLoadResult", "PaperHit", "PaperPort"]


@dataclass(frozen=True, slots=True)
class PaperHit:
    arxiv_id: str
    version: str
    title: str
    year: int
    url: str
    categories: list[str]
    published_at: datetime
    abstract: str


@dataclass(frozen=True, slots=True)
class HtmlLoadResult:
    status: Literal["ok", "missing", "empty", "not_html"]
    body: bytes = b""
    content_type: str = ""


class PaperPort(Protocol):
    async def search(self, query: str, *, max_results: int) -> list[PaperHit]: ...

    async def load_html(self, arxiv_id: str, version: str) -> HtmlLoadResult: ...

    async def load_pdf_text(self, arxiv_id: str, version: str) -> str: ...
