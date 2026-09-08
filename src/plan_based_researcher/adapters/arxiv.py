"""LangChain arXiv adapter for PaperPort (ARX-01, RUN-01)."""

from __future__ import annotations

import asyncio
import logging
import re
from datetime import date, datetime, timezone
from urllib.parse import urlparse

import arxiv
import httpx

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
logger = logging.getLogger(__name__)

_MOCK_PUBLISHED = datetime(2026, 9, 1, tzinfo=timezone.utc)
_MOCK_HITS: dict[tuple[str, str], PaperHit] = {
    ("2609.01617", "1"): PaperHit(
        arxiv_id="2609.01617",
        version="1",
        title=(
            "Hybrid Retrieval-Augmented Generation with Knowledge Graph "
            "Expansion, RRF Fusion, and Per-Chunk Grounded Evaluation for "
            "Enterprise Document Search"
        ),
        year=2026,
        url="https://arxiv.org/abs/2609.01617v1",
        categories=["cs.AI", "cs.LG"],
        published_at=_MOCK_PUBLISHED,
        abstract=(
            "Getting accurate, grounded answers out of large enterprise "
            "document repositories is a difficult problem. Dense vector "
            "retrieval alone frequently performs poorly on queries that mix "
            "lexical identifiers with conceptual intent. DocuSearch is a "
            "hybrid multi-agent RAG system using knowledge-graph expansion, "
            "Reciprocal Rank Fusion, and per-chunk grounded evaluation."
        ),
    ),
}


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


def _parse_mock_arxiv_id(value: str) -> tuple[str, str] | None:
    match = _ABS_ID_RE.search(value.strip())
    if match is None:
        return None
    return match.group("arxiv_id"), match.group("version") or "1"


def _mock_hit(arxiv_id: str, version: str) -> PaperHit:
    pinned = _MOCK_HITS.get((arxiv_id, version))
    if pinned is not None:
        return pinned
    return PaperHit(
        arxiv_id=arxiv_id,
        version=version,
        title=arxiv_id,
        year=_MOCK_PUBLISHED.year,
        url=f"https://arxiv.org/abs/{arxiv_id}v{version}",
        categories=["cs.AI"],
        published_at=_MOCK_PUBLISHED,
        abstract=f"Pinned mock hit for {arxiv_id}v{version}.",
    )


class ArxivPaperAdapter:
    """PaperPort backed by a shared arXiv Client and HTML GET."""

    def __init__(self, mock_arxiv_id: str | None = None) -> None:
        self._mock = _parse_mock_arxiv_id(mock_arxiv_id or "")

    async def search(self, query: str, *, max_results: int) -> list[PaperHit]:
        if self._mock is not None:
            arxiv_id, version = self._mock
            logger.warning(
                "MOCK_ARXIV_ID=%sv%s; skipping live arXiv search",
                arxiv_id,
                version,
            )
            return [_mock_hit(arxiv_id, version)]
        async with _REQUEST_LOCK:
            return await asyncio.to_thread(_search_sync, query, max_results)

    async def load_html(self, arxiv_id: str, version: str) -> HtmlLoadResult:
        if self._mock is not None:
            logger.warning(
                "MOCK_ARXIV_ID set; skipping live HTML fetch for %sv%s",
                arxiv_id,
                version,
            )
            return HtmlLoadResult(status="missing")
        async with _REQUEST_LOCK:
            return await asyncio.to_thread(_load_html_sync, arxiv_id, version)
