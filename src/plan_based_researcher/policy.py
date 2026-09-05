"""Single copy of research policy: allowlist, caps, recency, splitter, grounding."""

from __future__ import annotations

from datetime import date, datetime, timezone


class Policy:
    """Named research rules used by graph, eval, and prompts (PAT-10)."""

    arxiv_categories: frozenset[str] = frozenset(
        {
            "cs.AI",
            "cs.LG",
            "cs.CL",
            "cs.CV",
            "cs.NE",
            "cs.RO",
            "stat.ML",
        }
    )
    max_steps: int = 8
    max_retries_per_step: int = 1
    max_replans: int = 1
    max_papers: int = 8
    recency_years: int = 5
    chunk_size: int = 512
    chunk_overlap: int = 50
    chunk_encoding: str = "cl100k_base"
    hybrid_vector_weight: float = 0.7
    hybrid_lexical_weight: float = 0.3
    search_max_results: int = 8
    retrieve_k_per_paper: int = 5
    retrieve_overfetch_factor: int = 3
    retrieve_first_stage_k: int = 40
    retrieve_rerank_top_n: int = 12
    retrieve_rerank_margin: float = 0.20
    retrieve_rerank_floor: float | None = 0.30
    GROUNDING_RULE: str = (
        "every technical claim has a real [n] citation from the provided chunk list"
    )
    HOLE_RULE: str = (
        'an absence sentence ("no usable paper was found for {topic}") needs no [n]; '
        "technical claims about a topic need chunks from that topic's paper; "
        "do not fill missing topics from parametric knowledge; "
        "do not cite another method's chunks as the missing topic"
    )
    PREAMBLE_SECTION: str = "Preamble"

    @classmethod
    def html_url(cls, arxiv_id: str, version: str) -> str:
        return f"https://arxiv.org/html/{arxiv_id}v{version}"

    @classmethod
    def is_allowlisted(cls, categories: list[str]) -> bool:
        """True iff any category intersects the AI/ML allowlist (GATE-02)."""
        return bool(cls.arxiv_categories.intersection(categories))

    @classmethod
    def within_recency(
        cls,
        published: date | datetime | None,
        *,
        historical: bool,
    ) -> bool:
        """True if historical, or if published is within recency_years (ARX-02)."""
        if historical:
            return True
        if published is None:
            return False

        published_date = cls._as_utc_date(published)
        now = datetime.now(timezone.utc)
        cutoff = cls._years_ago(now.date(), cls.recency_years)
        return published_date >= cutoff

    @staticmethod
    def _as_utc_date(published: date | datetime) -> date:
        if isinstance(published, datetime):
            if published.tzinfo is not None:
                return published.astimezone(timezone.utc).date()
            return published.date()
        return published

    @staticmethod
    def _years_ago(today: date, years: int) -> date:
        try:
            return date(today.year - years, today.month, today.day)
        except ValueError:
            return date(today.year - years, today.month, 28)
