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
    embedding_dimensions: int = 1024
    hybrid_vector_weight: float = 0.7
    hybrid_lexical_weight: float = 0.3
    search_max_results: int = 8
    retrieve_k_per_paper: int = 5
    retrieve_overfetch_factor: int = 3
    retrieve_first_stage_k: int = 40
    retrieve_rerank_top_n: int = 10
    retrieve_retry_add_cap: int = 5
    retrieve_pack_cap_after_retry: int = 15
    retrieve_retry_first_stage_k: int = 10
    retrieve_rerank_margin: float = 0.20
    retrieve_rerank_floor: float | None = 0.30
    retrieve_hop_cap: int = 6
    retrieve_hop_voyage_docs: int = 15
    retrieve_hop_rrf_k: int = 60
    history_window_exchanges: int = 3
    history_token_encoding: str = "o200k_base"
    compaction_trigger_tokens: int = 48000
    compaction_min_prefix_tokens: int = 8000
    compaction_min_suffix_tokens: int = 16000
    compaction_failed_cooldown_seconds: int = 30
    compaction_timeout_seconds: int = 90
    summarizer_reasoning_effort: str = "medium"
    summarizer_max_completion_tokens: int = 2500
    writer_history_exchanges: int = 2
    writer_calculator_rounds: int = 8
    writer_calculator_expression_max: int = 200
    GROUNDING_RULE: str = (
        "every technical claim has a real [n] citation that resolves to a "
        "chunk packed in this thread; a number obtained by arithmetic on "
        "operands that each have a real [n] is a derived result: cite the "
        "operands; do not invent a citation for the result; do not treat "
        "the result as a new source"
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
