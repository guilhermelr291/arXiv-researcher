"""LangChain arXiv adapter for PaperPort (ARX-01, RUN-01)."""

from __future__ import annotations

import asyncio
import re
from datetime import date, datetime, timezone
from urllib.parse import urlparse

import arxiv
import httpx
from langchain_community.document_loaders import ArxivLoader

from plan_based_researcher.policy import Policy
from plan_based_researcher.ports.papers import HtmlLoadResult, PaperHit

_ABS_ID_RE = re.compile(
    r"(?:/abs/)?(?P<arxiv_id>\d{4}\.\d{4,5}|[a-z-]+/\d{7})(?:v(?P<version>\d+))?",
    re.IGNORECASE,
)

_CLIENT = arxiv.Client(page_size=8, delay_seconds=3.0)
_REQUEST_LOCK = asyncio.Lock()
_HTML_USER_AGENT = "plan-based-researcher/0.1 (research tool; not a crawler)"
_HTML_TIMEOUT = httpx.Timeout(30.0)


def _parse_arxiv_id_and_version(entry_id: str) -> tuple[str, str] | None:
    if not entry_id:
        return None
    path = urlparse(entry_id).path or entry_id
    match = _ABS_ID_RE.search(path) or _ABS_ID_RE.search(entry_id)
    if match is None:
        return None
    return match.group("arxiv_id"), match.group("version") or "1"


def _as_utc_datetime(value: object) -> datetime | None:
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)
    if isinstance(value, date):
        return datetime(value.year, value.month, value.day, tzinfo=timezone.utc)
    if isinstance(value, str) and value:
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
        if parsed.tzinfo is None:
            return parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)
    return None


def _paper_url(arxiv_id: str, result: arxiv.Result) -> str:
    for link in result.links:
        href = getattr(link, "href", "") or ""
        if "/abs/" in href:
            return href
    if result.entry_id and "/abs/" in result.entry_id:
        return result.entry_id
    return f"https://arxiv.org/abs/{arxiv_id}"


def _hit_from_result(result: arxiv.Result) -> PaperHit | None:
    parsed = _parse_arxiv_id_and_version(result.entry_id)
    if parsed is None:
        return None
    arxiv_id, version = parsed
    published_at = _as_utc_datetime(result.published)
    if published_at is None:
        return None
    return PaperHit(
        arxiv_id=arxiv_id,
        version=version,
        title=str(result.title or ""),
        year=published_at.year,
        url=_paper_url(arxiv_id, result),
        categories=[str(item) for item in (result.categories or [])],
        published_at=published_at,
        abstract=str(result.summary or ""),
    )


def _search_sync(query: str, max_results: int) -> list[PaperHit]:
    search = arxiv.Search(query=query, max_results=max_results)
    hits: list[PaperHit] = []
    for result in _CLIENT.results(search):
        hit = _hit_from_result(result)
        if hit is not None:
            hits.append(hit)
    return hits


def _sanitize_pdf_text(text: str) -> str:
    """Drop NUL bytes; PostgreSQL TEXT / psycopg reject 0x00."""
    return text.replace("\x00", "")


def _load_pdf_text_sync(arxiv_id: str, version: str) -> str:
    loader = ArxivLoader(query=f"{arxiv_id}v{version}", load_max_docs=1)
    docs = loader.load()
    if not docs:
        return ""
    return _sanitize_pdf_text("".join(doc.page_content or "" for doc in docs))


def _load_html_sync(arxiv_id: str, version: str) -> HtmlLoadResult:
    url = Policy.html_url(arxiv_id, version)
    response = httpx.get(
        url,
        headers={"User-Agent": _HTML_USER_AGENT},
        timeout=_HTML_TIMEOUT,
        follow_redirects=True,
    )
    content_type = response.headers.get("content-type", "")
    if response.status_code != 200:
        return HtmlLoadResult(status="missing", content_type=content_type)
    body = response.content
    if not body:
        return HtmlLoadResult(status="empty", content_type=content_type)
    media_type = content_type.split(";", 1)[0].strip().lower()
    if media_type == "application/pdf" or body.startswith(b"%PDF"):
        return HtmlLoadResult(
            status="not_html", body=body, content_type=content_type
        )
    return HtmlLoadResult(status="ok", body=body, content_type=content_type)


class ArxivPaperAdapter:
    """PaperPort backed by a shared arXiv Client and LangChain ArxivLoader."""

    async def search(self, query: str, *, max_results: int) -> list[PaperHit]:
        async with _REQUEST_LOCK:
            return await asyncio.to_thread(_search_sync, query, max_results)

    async def load_html(self, arxiv_id: str, version: str) -> HtmlLoadResult:
        async with _REQUEST_LOCK:
            return await asyncio.to_thread(_load_html_sync, arxiv_id, version)

    async def load_pdf_text(self, arxiv_id: str, version: str) -> str:
        async with _REQUEST_LOCK:
            return await asyncio.to_thread(_load_pdf_text_sync, arxiv_id, version)
