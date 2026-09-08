"""Search runner: arXiv titles and abstracts for this step's task (SEARCH-01)."""

from __future__ import annotations

from langchain_openai import ChatOpenAI

from plan_based_researcher.agents.query_schema import (
    FormulatedQuery,
    formulate_human,
    step_eval_feedback,
)
from plan_based_researcher.agents.registry import REGISTRY
from plan_based_researcher.policy import Policy
from plan_based_researcher.ports.papers import PaperHit, PaperPort

__all__ = ["SearchRunner"]

_FORMULATE_SYSTEM = """\
You write an arXiv API search_query string. The runtime sends your query field \
verbatim to LangChain ArxivRetriever, which forwards it as the arXiv API \
search_query. This is keyword search, not natural language.

Rules:
- Put the query in the structured `query` field. Do not narrate.
- Use English keywords even when the task is in another language.
- Do not copy the task prose or a student question as the query.
- Field prefixes: ti: (title), abs: (abstract), all: (all fields), id: (arXiv id). \
Use au: only if the task names an author.
- If the task or student query contains an arXiv id (new-style NNNN.NNNNN, \
optional vN), the query MUST be exactly id: plus that id, with no AND of title \
or abstract phrases. Strip a trailing vN if present; use the id the student \
gave, not a different paper.
- Boolean operators must be uppercase: AND, OR, ANDNOT. Use parentheses for grouping.
- Quote multi-word phrases: ti:"low-rank adaptation".
- When no arXiv id is given, prefer (ti:"phrase" OR abs:"phrase") plus related terms.
- Do not AND retrieve-only body terms into ti: or abs:. Equation names, table \
numbers, BLEU scores, section titles, and architecture nicknames such as \
Transformer-big are for retrieve, not search. Search matches titles and abstracts.
- Do not use cat: to enforce the AI/ML allowlist. A later filter keeps only \
cs.AI, cs.LG, cs.CL, cs.CV, cs.NE, cs.RO, stat.ML. A cat: outside that list \
yields empty usable hits.
- Do not use submittedDate. Recency is applied after search unless historical=true.
- Keep the query under 300 characters.
- When Previous query or Evaluator feedback is present, honor the feedback and \
emit a different query from Previous query. An id: query that returned hits \
must not be rewritten into a title/abstract AND.

Examples:
- Task: Find papers on LoRA for adapting LLMs
  query: (ti:"LoRA" OR ti:"low-rank adaptation") AND (abs:"large language model" OR abs:LLM)
- Task: Find papers on QLoRA quantization
  query: (ti:QLoRA OR ti:"quantized LoRA") AND abs:quantization
- Task (not English): Buscar papers que expliquem attention no transformer
  query: (ti:attention AND ti:transformer) OR (abs:"self-attention" AND abs:transformer)
- Evaluator feedback: hits were LoRa radio, not adapters
  query: (ti:"LoRA" OR ti:"low-rank adaptation") AND abs:"parameter-efficient" ANDNOT abs:LoRaWAN ANDNOT abs:radio
"""


def _step_index(state: dict) -> int:
    try:
        return int(state.get("step_index") or 0)
    except (TypeError, ValueError):
        return 0


def _current_step(state: dict) -> dict:
    plan = state.get("plan") or []
    index = _step_index(state)
    if not isinstance(plan, list) or index < 0 or index >= len(plan):
        return {}
    step = plan[index]
    return step if isinstance(step, dict) else {}


def _previous_query(state: dict, step_index: int) -> str:
    artifacts = state.get("search_artifacts") or {}
    if not isinstance(artifacts, dict):
        return ""
    art = artifacts.get(str(step_index))
    if art is None:
        art = artifacts.get(step_index)
    if not isinstance(art, dict):
        return ""
    return str(art.get("query_used") or "").strip()


def _search_hit(hit: PaperHit) -> dict:
    return {
        "arxiv_id": hit.arxiv_id,
        "version": hit.version,
        "title": hit.title,
        "year": hit.year,
        "url": hit.url,
        "categories": list(hit.categories),
        "abstract": hit.abstract,
    }


class SearchRunner:
    def __init__(self, papers: PaperPort, api_key: str | None = None) -> None:
        self._papers = papers
        kwargs: dict = {"model": REGISTRY["search"].model}
        if api_key is not None:
            kwargs["api_key"] = api_key
        self._formulate = ChatOpenAI(**kwargs).with_structured_output(
            FormulatedQuery, method="json_schema"
        )

    async def run(self, state: dict) -> dict:
        step_index = _step_index(state)
        step = _current_step(state)
        task = str(step.get("task") or "")
        historical = bool(step.get("historical", False))
        feedback = step_eval_feedback(state, step_index)
        previous_query = _previous_query(state, step_index)
        query = await self._formulate_query(
            task,
            feedback=feedback,
            previous_query=previous_query,
            historical=historical,
            student_query=str(state.get("query") or ""),
        )

        hits = await self._papers.search(query, max_results=Policy.search_max_results)
        selected: list[dict] = []
        seen: set[tuple[str, str]] = set()
        for hit in hits:
            if not Policy.is_allowlisted(hit.categories):
                continue
            if not Policy.within_recency(hit.published_at, historical=historical):
                continue
            key = (hit.arxiv_id, hit.version)
            if key in seen:
                continue
            seen.add(key)
            selected.append(_search_hit(hit))

        return {
            "search_artifacts": {
                str(step_index): {
                    "step_index": step_index,
                    "query_used": query,
                    "hits": selected,
                }
            },
            "last_agent": "search",
        }

    async def _formulate_query(
        self,
        task: str,
        *,
        feedback: str,
        previous_query: str,
        historical: bool,
        student_query: str,
    ) -> str:
        formulated = await self._formulate.ainvoke(
            [
                ("system", _FORMULATE_SYSTEM),
                (
                    "human",
                    formulate_human(
                        task=task,
                        feedback=feedback,
                        previous_query=previous_query,
                        historical=historical,
                        student_query=student_query,
                    ),
                ),
            ]
        )
        if not isinstance(formulated, FormulatedQuery):
            formulated = FormulatedQuery.model_validate(formulated)
        query = formulated.query.strip()
        return query or task
