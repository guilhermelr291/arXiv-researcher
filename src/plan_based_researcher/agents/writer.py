"""Writer runner: grounded markdown from numbered chunks (GROUND-01–03)."""

from __future__ import annotations

import re

from langchain_openai import ChatOpenAI
from pydantic import BaseModel, Field

from plan_based_researcher.agents.query_schema import step_eval_feedback
from plan_based_researcher.agents.registry import REGISTRY
from plan_based_researcher.api.schemas import Citation
from plan_based_researcher.graph.state import EvidenceChunk, GraphState
from plan_based_researcher.policy import Policy

__all__ = ["WriterOutput", "WriterRunner", "living_and_missing"]

_CITATION_RE = re.compile(r"\[(\d+)\]")


class WriterOutput(BaseModel):
    markdown: str = Field(description="Student-facing markdown that cites evidence as [n]")
    citation_ns: list[int] = Field(
        default_factory=list,
        description="The [n] indices actually used in markdown",
    )


def _format_chunks(chunks: list[EvidenceChunk]) -> str:
    """Format chunks as ``[n] arXiv:{id} — {title} ({year})\\n{excerpt}`` (GROUND-01)."""
    if not chunks:
        return "(no evidence chunks provided)"
    blocks: list[str] = []
    for chunk in chunks:
        n = chunk["n"]
        arxiv_id = chunk["arxiv_id"]
        title = chunk["title"]
        year = chunk["year"]
        excerpt = chunk["excerpt"]
        blocks.append(f"[{n}] arXiv:{arxiv_id} — {title} ({year})\n{excerpt}")
    return "\n\n".join(blocks)


def _used_citation_ns(markdown: str, chunks: list[EvidenceChunk]) -> list[int]:
    valid = {int(chunk["n"]) for chunk in chunks}
    seen: set[int] = set()
    ordered: list[int] = []
    for match in _CITATION_RE.finditer(markdown):
        n = int(match.group(1))
        if n in valid and n not in seen:
            seen.add(n)
            ordered.append(n)
    return ordered


def _citations_from_chunks(chunks: list[EvidenceChunk], ns: list[int]) -> list[dict]:
    by_n = {int(chunk["n"]): chunk for chunk in chunks}
    citations: list[dict] = []
    for n in ns:
        chunk = by_n.get(n)
        if chunk is None:
            continue
        citations.append(
            Citation(
                n=chunk["n"],
                arxiv_id=chunk["arxiv_id"],
                title=chunk["title"],
                year=chunk["year"],
                url=chunk["url"],
                excerpt=chunk["excerpt"],
                chunk_id=chunk["chunk_id"],
            ).model_dump()
        )
    return citations


def _paper_key(item: object) -> tuple[str, str] | None:
    if isinstance(item, dict):
        arxiv_id = item.get("arxiv_id")
        if not arxiv_id:
            return None
        return str(arxiv_id), str(item.get("version") or "")
    arxiv_id = getattr(item, "arxiv_id", None)
    if not arxiv_id:
        return None
    return str(arxiv_id), str(getattr(item, "version", None) or "")


def _paper_key_set(papers: object) -> set[tuple[str, str]]:
    keys: set[tuple[str, str]] = set()
    if not isinstance(papers, list):
        return keys
    for paper in papers:
        key = _paper_key(paper)
        if key is not None:
            keys.add(key)
    return keys


def _passed_indices(state: dict) -> set[int]:
    passed: set[int] = set()
    for item in state.get("passed_steps") or []:
        try:
            passed.add(int(item))
        except (TypeError, ValueError):
            continue
    return passed


def _step_artifact(artifacts: object, index: int) -> dict:
    if not isinstance(artifacts, dict):
        return {}
    artifact = artifacts.get(str(index))
    if artifact is None:
        artifact = artifacts.get(index)
    return artifact if isinstance(artifact, dict) else {}


def _ingested_key(
    artifacts: object, index: int, papers: set[tuple[str, str]]
) -> tuple[str, str] | None:
    ranked = _step_artifact(artifacts, index).get("ranked_keys") or []
    if not isinstance(ranked, list):
        return None
    for item in ranked:
        key = _paper_key(item)
        if key is not None and key in papers:
            return key
    return None


def _ns_for_key(chunks: object, key: tuple[str, str]) -> list[int]:
    ns: list[int] = []
    seen: set[int] = set()
    if not isinstance(chunks, list):
        return ns
    for chunk in chunks:
        if not isinstance(chunk, dict):
            continue
        if _paper_key(chunk) != key:
            continue
        try:
            n = int(chunk["n"])
        except (KeyError, TypeError, ValueError):
            continue
        if n not in seen:
            seen.add(n)
            ns.append(n)
    return ns


def living_and_missing(state: dict) -> tuple[list[dict], list[dict]]:
    """Return (living, missing).
    living item: {"task": str, "arxiv_id": str, "version": str, "ns": list[int]}
    missing item: {"task": str, "reason": "unpassed" | "gap"}
    """
    plan = state.get("plan") or []
    if not isinstance(plan, list):
        plan = []
    passed = _passed_indices(state)
    papers = _paper_key_set(state.get("papers"))
    artifacts = state.get("search_artifacts") or {}
    chunks = state.get("evidence_chunks") or []

    missing: list[dict] = []
    missing_tasks: set[str] = set()

    def add_missing(task: str, reason: str) -> None:
        task = task.strip()
        if not task or task in missing_tasks:
            return
        missing.append({"task": task, "reason": reason})
        missing_tasks.add(task)

    for index, step in enumerate(plan):
        if not isinstance(step, dict) or step.get("agent") != "search":
            continue
        if index not in passed:
            add_missing(str(step.get("task") or ""), "unpassed")

    for item in state.get("hole_tasks") or []:
        if not isinstance(item, dict):
            continue
        reason = str(item.get("reason") or "gap")
        if reason not in ("unpassed", "gap"):
            reason = "gap"
        add_missing(str(item.get("task") or ""), reason)

    ingest = state.get("retrieve_ingest") or {}
    if not isinstance(ingest, dict):
        ingest = {}
    for raw_task in ingest.get("gap_tasks") or []:
        add_missing(str(raw_task), "gap")
    for raw in ingest.get("gap_step_indices") or []:
        try:
            index = int(raw)
        except (TypeError, ValueError):
            continue
        if index < 0 or index >= len(plan):
            continue
        step = plan[index]
        if not isinstance(step, dict) or step.get("agent") != "search":
            continue
        add_missing(str(step.get("task") or ""), "gap")

    living: list[dict] = []
    for index, step in enumerate(plan):
        if not isinstance(step, dict) or step.get("agent") != "search":
            continue
        if index not in passed:
            continue
        task = str(step.get("task") or "")
        if task.strip() in missing_tasks:
            continue
        ingested = _ingested_key(artifacts, index, papers)
        if ingested is None:
            continue
        ns = _ns_for_key(chunks, ingested)
        if len(ns) < 1:
            continue
        living.append(
            {
                "task": task,
                "arxiv_id": ingested[0],
                "version": ingested[1],
                "ns": ns,
            }
        )

    return living, missing


def _format_coverage(living: list[dict], missing: list[dict]) -> str:
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
        "Living topics (cite these [n] only for those topics):\n"
        f"{living_body}\n\n"
        "Missing topics (announce no usable paper; do not define/compare from memory; "
        "do not cite living [n] as the missing topic):\n"
        f"{missing_body}"
    )


def _language(state: GraphState) -> str:
    gate = state.get("gate") or {}
    return str(gate.get("language") or "")


def _current_task(state: GraphState) -> str:
    plan = state.get("plan") or []
    index = state.get("step_index") or 0
    if not plan or index < 0 or index >= len(plan):
        return ""
    step = plan[index]
    if isinstance(step, dict):
        return str(step.get("task") or "")
    return ""


def _eval_feedback(state: GraphState) -> str:
    index = state.get("step_index") or 0
    try:
        return step_eval_feedback(state, int(index))
    except (TypeError, ValueError):
        return str((state.get("last_eval") or {}).get("feedback") or "")


def _system_prompt() -> str:
    return (
        f"{REGISTRY['writer'].abilities}\n\n"
        f"Grounding rule: {Policy.GROUNDING_RULE}.\n\n"
        f"Hole rule: {Policy.HOLE_RULE}.\n\n"
        "You are given a numbered list of arXiv evidence chunks formatted as [n] blocks. "
        "Cite only those [n] values; never invent indices or non-arXiv sources. "
        "Every technical claim needs a real [n]. "
        "Write the answer markdown in the student query language and a student "
        "didactic register. Plan tasks and evaluator feedback are English; do "
        "not switch the answer to English because of them. "
        "If chunks disagree or conflict, include a limitations/contradictions section; "
        "do not pick a silent winner. State both sides with their [n] citations."
    )


def _user_prompt(state: GraphState, formatted_chunks: str) -> str:
    language = _language(state)
    task = _current_task(state)
    feedback = _eval_feedback(state)
    parts = [
        f"Student query:\n{state.get('query') or ''}",
    ]
    if language:
        parts.append(
            f"Answer language: {language}\n"
            "Write the markdown in that language. The writing task and evaluator "
            "feedback may be English; do not follow them for answer language."
        )
    if task:
        parts.append(f"Current writing task (English; execute it in Answer language):\n{task}")
    if feedback:
        parts.append(f"Evaluator feedback (honor this on retry):\n{feedback}")
    living, missing = living_and_missing(state)
    parts.append(_format_coverage(living, missing))
    parts.append(f"Evidence chunks:\n{formatted_chunks}")
    return "\n\n".join(parts)


class WriterRunner:
    def __init__(self, api_key: str | None = None) -> None:
        kwargs: dict = {"model": REGISTRY["writer"].model}
        if api_key is not None:
            kwargs["api_key"] = api_key
        self._llm = ChatOpenAI(**kwargs).with_structured_output(WriterOutput)

    async def run(self, state: GraphState) -> dict:
        chunks: list[EvidenceChunk] = list(state.get("evidence_chunks") or [])
        formatted = _format_chunks(chunks)
        output = await self._llm.ainvoke(
            [
                {"role": "system", "content": _system_prompt()},
                {"role": "user", "content": _user_prompt(state, formatted)},
            ]
        )
        markdown = output.markdown if isinstance(output, WriterOutput) else str(output)
        used_ns = _used_citation_ns(markdown, chunks)
        return {
            "writer_markdown": markdown,
            "citations": _citations_from_chunks(chunks, used_ns),
            "last_agent": "writer",
        }
