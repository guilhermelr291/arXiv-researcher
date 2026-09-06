"""Search-wave, retrieve, and writer eval strategies (SEARCH-02, RETR-01, WRITE-01, LOOP-02, LOOP-03)."""

from __future__ import annotations

import re
from datetime import date, datetime
from typing import Protocol
from urllib.parse import urlparse

from langchain_openai import ChatOpenAI

from plan_based_researcher.agents.registry import REGISTRY
from plan_based_researcher.agents.writer import living_and_missing
from plan_based_researcher.eval.types import (
    EvalResult,
    SearchStepVerdict,
    SearchWaveJudgement,
)
from plan_based_researcher.graph.state import GraphState
from plan_based_researcher.policy import Policy

__all__ = [
    "EvalStrategy",
    "SearchEvalStrategy",
    "RetrieveEvalStrategy",
    "WriterEvalStrategy",
]

_CITATION_RE = re.compile(r"\[(\d+)\]")
_URL_RE = re.compile(r"https?://[^\s\]\)>\"']+", re.IGNORECASE)


class EvalStrategy(Protocol):
    async def evaluate(self, state: GraphState | dict) -> EvalResult: ...


def _as_state(state: GraphState | dict) -> dict:
    return state if isinstance(state, dict) else dict(state)


def _step_at(plan: object, index: int) -> dict:
    if not isinstance(plan, list) or index < 0 or index >= len(plan):
        return {}
    step = plan[index]
    return step if isinstance(step, dict) else {}


def _current_step(state: dict) -> dict:
    plan = state.get("plan") or []
    try:
        index = int(state.get("step_index") or 0)
    except (TypeError, ValueError):
        index = 0
    return _step_at(plan, index)


def _paper_published(paper: dict) -> date | datetime | None:
    published_at = paper.get("published_at")
    if isinstance(published_at, (date, datetime)):
        return published_at
    year = paper.get("year")
    if not isinstance(year, int) or year < 1:
        return None
    try:
        return date(year, 12, 31)
    except ValueError:
        return None


def _categories(paper: dict) -> list[str]:
    raw = paper.get("categories") or []
    if isinstance(raw, str):
        return [raw]
    if isinstance(raw, list):
        return [str(item) for item in raw]
    return [str(raw)]


def _chunk_ns(chunks: object) -> set[int]:
    numbers: set[int] = set()
    if not isinstance(chunks, list):
        return numbers
    for chunk in chunks:
        if not isinstance(chunk, dict):
            continue
        n = chunk.get("n")
        if isinstance(n, int):
            numbers.add(n)
        elif isinstance(n, str) and n.isdigit():
            numbers.add(int(n))
    return numbers


def _is_arxiv_url(url: str) -> bool:
    host = (urlparse(url).hostname or "").lower()
    return host == "arxiv.org" or host.endswith(".arxiv.org")


def _writer_checklist() -> str:
    categories = ", ".join(sorted(Policy.arxiv_categories))
    return (
        f"Allowed evidence domain: arXiv categories only ({categories}).\n"
        f"Grounding: {Policy.GROUNDING_RULE}.\n"
        "Your feedback field must be English.\n"
        "The student markdown must be in the same language as the student query; "
        "do not fail it for being a different language from the English plan task.\n"
        "Use a didactic, student-friendly tone.\n"
        "Do not introduce sources outside the provided evidence chunks or arxiv.org URLs.\n"
        "Fail if the answer teaches a definition, mechanism, or comparison of a missing "
        "topic (parametric fill).\n"
        "Fail if living [n] citations are used as if they were the missing topic.\n"
        "A sentence that no usable paper was found for a named topic is not a technical "
        "claim and does not need [n].\n"
        "Living topics still need real [n] (ORCH-03 is enforced deterministically).\n"
        "Pass when the student-requested facts are present and cited with living [n].\n"
        "Do not retry to rephrase, add headings, or demand extra caveats when those "
        "facts are already cited. If the evidence contains two conflicting values for "
        "the same fact and the markdown states both with citations, that is a pass; "
        "do not retry to pick one canonical number or to expand the caveat.\n"
        "Retry only when a requested fact is missing, a technical claim lacks [n], "
        "a missing topic is filled from memory, or living [n] are used as the missing "
        "topic."
    )


def _format_living_missing(living: list[dict], missing: list[dict]) -> str:
    if living:
        living_body = "\n".join(
            f"- {item['task']} arXiv:{item['arxiv_id']}v{item['version']} "
            f"{' '.join(f'[{n}]' for n in item['ns'])}"
            for item in living
        )
    else:
        living_body = "(none)"
    if missing:
        missing_body = "\n".join(
            f"- {item['task']} ({item['reason']})" for item in missing
        )
    else:
        missing_body = "(none)"
    return (
        "Living topics (cite only these [n] for those topics):\n"
        f"{living_body}\n\n"
        "Missing topics (announce absence; do not define/compare from memory; "
        "do not cite living [n] as the missing topic):\n"
        f"{missing_body}"
    )


def _search_checklist() -> str:
    categories = ", ".join(sorted(Policy.arxiv_categories))
    return (
        "Return one independent verdict per search step, plus overall reasoning.\n"
        "Write feedback and reasoning in English, even when the student query "
        "is not English.\n"
        "Titles and abstracts must match THIS step's task.\n"
        "For each step, output ranked_hit_indices: an ordered list of 0-based "
        "indexes into THAT step's hits only (the [n] labels in that step). "
        "Do not emit arxiv_id strings. Do not reuse another step's indexes.\n"
        f"Allowed categories: {categories}. "
        f"Recency: within Policy.recency_years={Policy.recency_years} unless the step is historical.\n"
        "Set plan_inadequate if the task cannot succeed (e.g. no suitable papers for a named topic).\n"
        "Deterministic notes are facts: empty hits, none allowlisted, or none in recency "
        "means that step cannot pass."
    )


def _retrieve_checklist() -> str:
    return (
        "Evaluate retrieve evidence against THIS retrieve step task.\n"
        "Write feedback in English, even when the student query is not English.\n"
        "Chunks must be numbered [n] and come only from already-admitted papers.\n"
        "Chunks must match the retrieve task.\n"
        "A T3 query miss is a retrieve query rewrite on the same papers, "
        "not a new HTML walk.\n"
        "Return status pass, retry, or fail with feedback. "
        "Set plan_inadequate if the admitted paper set cannot satisfy this task."
    )


def _passed_set(state: dict) -> set[int]:
    passed: set[int] = set()
    for item in state.get("passed_steps") or []:
        try:
            passed.add(int(item))
        except (TypeError, ValueError):
            continue
    return passed


def _search_wave_indices(state: dict) -> list[int]:
    plan = state.get("plan") or []
    if not isinstance(plan, list):
        return []
    passed = _passed_set(state)
    first_unpassed: int | None = None
    for index in range(len(plan)):
        if index not in passed:
            first_unpassed = index
            break
    if first_unpassed is None:
        return []
    wave: list[int] = []
    for index in range(first_unpassed, len(plan)):
        if index in passed:
            break
        step = _step_at(plan, index)
        if step.get("agent") != "search":
            break
        wave.append(index)
    return wave


def _artifact_hits(artifacts: object, index: int) -> list[dict]:
    if not isinstance(artifacts, dict):
        return []
    artifact = artifacts.get(str(index))
    if not isinstance(artifact, dict):
        return []
    hits = artifact.get("hits") or []
    if not isinstance(hits, list):
        return []
    return [hit for hit in hits if isinstance(hit, dict)]


def _search_deterministic(hits: list[dict], historical: bool) -> tuple[bool, str]:
    empty = not hits
    any_allowlisted = any(Policy.is_allowlisted(_categories(hit)) for hit in hits)
    any_in_recency = any(
        Policy.within_recency(_paper_published(hit), historical=historical)
        for hit in hits
    )
    failed = empty or not any_allowlisted or not any_in_recency
    notes = (
        f"empty_hits={empty}; any_allowlisted={any_allowlisted}; "
        f"any_in_recency={any_in_recency}; historical={historical}"
    )
    return failed, notes


_ABSTRACT_CHARS = 400


def _format_hit(index: int, hit: dict) -> str:
    arxiv_id = hit.get("arxiv_id") or ""
    version = hit.get("version") or ""
    title = hit.get("title") or ""
    year = hit.get("year") or ""
    cats = ", ".join(_categories(hit))
    abstract = " ".join(str(hit.get("abstract") or "").split())
    if len(abstract) > _ABSTRACT_CHARS:
        abstract = abstract[:_ABSTRACT_CHARS].rstrip() + "…"
    return (
        f"[{index}] arxiv_id={arxiv_id} version={version}: {title} ({year}) [{cats}]\n"
        f"  {abstract}"
    )


def _format_search_step(
    index: int,
    step: dict,
    hits: list[dict],
    notes: str,
    query_used: str = "",
) -> str:
    task = str(step.get("task") or "").strip()
    body = (
        "\n".join(_format_hit(n, hit) for n, hit in enumerate(hits))
        if hits
        else "(no hits)"
    )
    query_line = f"query_used: {query_used}\n" if query_used else ""
    return (
        f"Step {index}\n"
        f"task: {task}\n"
        f"{query_line}"
        f"deterministic: {notes}\n"
        f"hits:\n{body}"
    )


def _merge_wave_verdicts(
    wave: list[int],
    det_failed: dict[int, bool],
    det_notes: dict[int, str],
    judged: SearchWaveJudgement | None,
) -> SearchWaveJudgement:
    by_index: dict[int, SearchStepVerdict] = {}
    reasoning = ""
    if judged is not None:
        reasoning = judged.reasoning
        for verdict in judged.verdicts:
            by_index[verdict.step_index] = verdict
    verdicts: list[SearchStepVerdict] = []
    for index in wave:
        existing = by_index.get(index)
        if existing is not None:
            failed = det_failed[index]
            verdicts.append(
                SearchStepVerdict(
                    step_index=index,
                    passed=False if failed else existing.passed,
                    plan_inadequate=existing.plan_inadequate,
                    feedback=existing.feedback,
                    ranked_hit_indices=(
                        [] if failed else list(existing.ranked_hit_indices)
                    ),
                )
            )
            continue
        failed = det_failed[index]
        verdicts.append(
            SearchStepVerdict(
                step_index=index,
                passed=not failed,
                plan_inadequate=False,
                feedback=det_notes[index] if failed else "deterministic coverage only",
                ranked_hit_indices=[],
            )
        )
    return SearchWaveJudgement(
        verdicts=verdicts,
        reasoning=reasoning or "deterministic only",
    )


def _admitted_keys(papers: object) -> set[tuple[str, str]]:
    keys: set[tuple[str, str]] = set()
    if not isinstance(papers, list):
        return keys
    for paper in papers:
        if not isinstance(paper, dict):
            continue
        arxiv_id = paper.get("arxiv_id")
        if not arxiv_id:
            continue
        version = paper.get("version")
        keys.add((str(arxiv_id), str(version if version is not None else "")))
    return keys


def _format_chunks(chunks: object) -> str:
    if not isinstance(chunks, list):
        return ""
    lines: list[str] = []
    for chunk in chunks:
        if not isinstance(chunk, dict):
            continue
        n = chunk.get("n")
        arxiv_id = chunk.get("arxiv_id") or ""
        title = chunk.get("title") or ""
        excerpt = chunk.get("excerpt") or ""
        lines.append(f"[{n}] arXiv:{arxiv_id} — {title}\n{excerpt}")
    return "\n\n".join(lines)


def _format_admitted(papers: object) -> str:
    if not isinstance(papers, list):
        return "(none)"
    lines: list[str] = []
    for paper in papers:
        if not isinstance(paper, dict):
            continue
        arxiv_id = paper.get("arxiv_id") or ""
        version = paper.get("version") or ""
        title = paper.get("title") or ""
        lines.append(f"- {arxiv_id}v{version}: {title}")
    return "\n".join(lines) if lines else "(none)"


class SearchEvalStrategy:
    """SEARCH-02: one structured wave judgement over search artifacts."""

    def __init__(self, api_key: str | None = None) -> None:
        self._api_key = api_key
        self._judge = None
        if api_key is not None:
            self._judge = ChatOpenAI(
                model=REGISTRY["planner"].model, api_key=api_key
            ).with_structured_output(SearchWaveJudgement, method="json_schema")

    async def evaluate_wave(self, state: GraphState | dict) -> SearchWaveJudgement:
        data = _as_state(state)
        wave = _search_wave_indices(data)
        if not wave:
            return SearchWaveJudgement(verdicts=[], reasoning="no search wave")

        plan = data.get("plan") or []
        artifacts = data.get("search_artifacts") or {}
        det_failed: dict[int, bool] = {}
        det_notes: dict[int, str] = {}
        sections: list[str] = []
        for index in wave:
            step = _step_at(plan, index)
            hits = _artifact_hits(artifacts, index)
            historical = bool(step.get("historical", False))
            failed, notes = _search_deterministic(hits, historical)
            det_failed[index] = failed
            det_notes[index] = notes
            art = artifacts.get(str(index)) if isinstance(artifacts, dict) else None
            if art is None and isinstance(artifacts, dict):
                art = artifacts.get(index)
            query_used = ""
            if isinstance(art, dict):
                query_used = str(art.get("query_used") or "")
            sections.append(
                _format_search_step(index, step, hits, notes, query_used=query_used)
            )

        judged = await self._judge_wave(data, sections)
        return _merge_wave_verdicts(wave, det_failed, det_notes, judged)

    async def _judge_wave(
        self, data: dict, sections: list[str]
    ) -> SearchWaveJudgement | None:
        if self._judge is None:
            return None
        query = str(data.get("query") or "")
        try:
            result = await self._judge.ainvoke(
                [
                    (
                        "system",
                        "You evaluate arXiv search results for a wave of search steps. "
                        "Return one verdict per step (passed, feedback, plan_inadequate, "
                        "ranked_hit_indices) and reasoning. Write feedback and reasoning "
                        "in English.\n"
                        f"{_search_checklist()}",
                    ),
                    (
                        "human",
                        f"Student query:\n{query}\n\n" + "\n\n".join(sections),
                    ),
                ]
            )
        except Exception:
            return None
        if isinstance(result, SearchWaveJudgement):
            return result
        try:
            return SearchWaveJudgement.model_validate(result)
        except Exception:
            return None


class RetrieveEvalStrategy:
    """RETR-01: chunks from admitted papers, aligned to this retrieve task."""

    def __init__(self, api_key: str | None = None) -> None:
        self._api_key = api_key
        self._judge = None
        if api_key is not None:
            self._judge = ChatOpenAI(
                model=REGISTRY["planner"].model, api_key=api_key
            ).with_structured_output(EvalResult, method="json_schema")

    async def evaluate(self, state: GraphState | dict) -> EvalResult:
        data = _as_state(state)
        ingest = data.get("retrieve_ingest") or {}
        case = ingest.get("case") if isinstance(ingest, dict) else None
        if case == "t1":
            return EvalResult(
                status="fail",
                plan_inadequate=True,
                feedback=(
                    "T1: no usable papers after ingest. Do not retry the retrieve query."
                ),
            )
        if case == "t2a":
            return EvalResult(
                status="fail",
                plan_inadequate=True,
                feedback=(
                    "T2a: at least one passed ranking ingested no usable HTML; "
                    "hybrid ran on living papers. Do not retry the retrieve query."
                ),
            )
        # t3 / default: existing path
        deterministic = self._deterministic(data)
        if deterministic.status != "pass":
            return deterministic
        judged = await self._judge_task(data)
        return judged if judged is not None else deterministic

    def _deterministic(self, data: dict) -> EvalResult:
        chunks = data.get("evidence_chunks") or []
        if not isinstance(chunks, list) or not chunks:
            return EvalResult(
                status="retry",
                feedback=(
                    "evidence_chunks is empty. Retrieve numbered [n] chunks "
                    "from admitted papers for this retrieve task."
                ),
            )

        admitted = _admitted_keys(data.get("papers"))
        for chunk in chunks:
            if not isinstance(chunk, dict):
                return EvalResult(
                    status="retry",
                    feedback="evidence_chunks must be maps with arxiv_id and version.",
                )
            arxiv_id = chunk.get("arxiv_id")
            if not arxiv_id:
                return EvalResult(
                    status="retry",
                    feedback="A chunk is missing arxiv_id; chunks must come from admitted papers.",
                )
            version = chunk.get("version")
            key = (str(arxiv_id), str(version if version is not None else ""))
            if key not in admitted:
                return EvalResult(
                    status="retry",
                    feedback=(
                        f"Chunk (arxiv_id={key[0]}, version={key[1]}) is not from "
                        "admitted papers."
                    ),
                )

        return EvalResult(
            status="pass",
            feedback="Chunks are from admitted papers.",
        )

    async def _judge_task(self, data: dict) -> EvalResult | None:
        if self._judge is None:
            return None
        step = _current_step(data)
        task = str(step.get("task") or "").strip()
        query = str(data.get("query") or "")
        try:
            result = await self._judge.ainvoke(
                [
                    (
                        "system",
                        "You evaluate retrieved evidence chunks. "
                        "Return status pass, retry, or fail with English feedback.\n"
                        f"{_retrieve_checklist()}",
                    ),
                    (
                        "human",
                        f"Student query:\n{query}\n\n"
                        f"Retrieve task:\n{task}\n\n"
                        f"Admitted papers:\n{_format_admitted(data.get('papers'))}\n\n"
                        f"Evidence chunks:\n{_format_chunks(data.get('evidence_chunks'))}",
                    ),
                ]
            )
        except Exception:
            return None
        if isinstance(result, EvalResult):
            return result
        try:
            return EvalResult.model_validate(result)
        except Exception:
            return None


class WriterEvalStrategy:
    """ORCH-03 + WRITE-02: real [n], language/tone, no extra sources, hole rule."""

    def __init__(self, api_key: str | None = None) -> None:
        self._api_key = api_key
        self._judge = None
        if api_key is not None:
            self._judge = ChatOpenAI(
                model=REGISTRY["planner"].model, api_key=api_key
            ).with_structured_output(EvalResult, method="json_schema")

    async def evaluate(self, state: GraphState | dict) -> EvalResult:
        data = _as_state(state)
        markdown = data.get("writer_markdown") or ""
        if not isinstance(markdown, str):
            markdown = str(markdown)

        deterministic = self._deterministic(markdown, data.get("evidence_chunks"))
        if deterministic.status != "pass":
            return deterministic

        judged = await self._judge_language_and_tone(data, markdown)
        return judged if judged is not None else deterministic

    def _deterministic(self, markdown: str, chunks: object) -> EvalResult:
        if not markdown.strip():
            return EvalResult(
                status="retry",
                feedback="writer_markdown is empty. Write the student answer with real [n] citations.",
            )

        cited = [int(match.group(1)) for match in _CITATION_RE.finditer(markdown)]
        if not cited:
            return EvalResult(
                status="retry",
                feedback=(
                    f"No [n] citations found. {Policy.GROUNDING_RULE}."
                ),
            )

        valid_ns = _chunk_ns(chunks)
        real = [n for n in cited if n in valid_ns]
        if not real:
            return EvalResult(
                status="retry",
                feedback=(
                    "Citations must use [n] values from evidence_chunks. "
                    f"{Policy.GROUNDING_RULE}."
                ),
            )
        unknown = sorted({n for n in cited if n not in valid_ns})
        if unknown:
            return EvalResult(
                status="retry",
                feedback=(
                    f"Citation(s) {unknown} are not in evidence_chunks. "
                    f"{Policy.GROUNDING_RULE}."
                ),
            )

        extra = [
            url for url in _URL_RE.findall(markdown) if not _is_arxiv_url(url)
        ]
        if extra:
            return EvalResult(
                status="retry",
                feedback=(
                    "Extra HTTP sources are not allowed; only arxiv.org URLs. "
                    f"Found: {extra[0]}"
                ),
            )

        return EvalResult(
            status="pass",
            feedback="Deterministic grounding passed: real [n] citations and no extra sources.",
        )

    async def _judge_language_and_tone(
        self, data: dict, markdown: str
    ) -> EvalResult | None:
        if self._judge is None:
            return None
        query = str(data.get("query") or "")
        living, missing = living_and_missing(data)
        coverage = _format_living_missing(living, missing)
        try:
            result = await self._judge.ainvoke(
                [
                    (
                        "system",
                        "You evaluate a student research answer. "
                        "Return status pass, retry, or fail with English feedback.\n"
                        f"{_writer_checklist()}",
                    ),
                    (
                        "human",
                        f"Student query:\n{query}\n\n"
                        f"{coverage}\n\n"
                        f"Writer markdown:\n{markdown}",
                    ),
                ]
            )
        except Exception:
            return None
        if isinstance(result, EvalResult):
            return result
        try:
            return EvalResult.model_validate(result)
        except Exception:
            return None
