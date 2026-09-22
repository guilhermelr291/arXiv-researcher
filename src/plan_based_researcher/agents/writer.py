"""Writer runner: grounded markdown from numbered chunks (GROUND-01–03)."""

from __future__ import annotations

import re
import uuid
from contextvars import ContextVar

from langchain_core.messages import (
    AIMessage,
    AIMessageChunk,
    HumanMessage,
    SystemMessage,
    ToolMessage,
)
from plan_based_researcher.llm import openai_chat as ChatOpenAI
from langgraph.config import get_stream_writer
from langgraph.graph import START, MessagesState, StateGraph
from langgraph.prebuilt import ToolNode, tools_condition

from plan_based_researcher.agents.calculator import calculator
from plan_based_researcher.agents.history import (
    format_transcript,
    last_exchanges,
    prior_citation_chunks,
)
from plan_based_researcher.agents.query_schema import step_eval_feedback
from plan_based_researcher.agents.registry import REGISTRY
from plan_based_researcher.api.schemas import Citation
from plan_based_researcher.graph.state import EvidenceChunk, GraphState
from plan_based_researcher.policy import Policy

__all__ = ["WriterRunner", "living_and_missing"]

_CITATION_RE = re.compile(r"\[(\d+)\]")
# The inner writer graph replaces get_stream_writer() with a no-op. run()
# captures the execute-node writer here so answer_delta still reaches POST /agent.
_parent_stream: ContextVar[object | None] = ContextVar("writer_parent_stream", default=None)


def _visible_text(chunk: object) -> str:
    content = getattr(chunk, "content", None)
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for block in content:
            if isinstance(block, dict) and block.get("type") == "text":
                text = block.get("text")
                if text is None:
                    text = block.get("content")
                if isinstance(text, str) and text:
                    parts.append(text)
            elif isinstance(block, str) and block:
                parts.append(block)
        return "".join(parts)
    return ""


def _has_tool_call(message: object | None) -> bool:
    if message is None:
        return False
    if list(getattr(message, "tool_calls", None) or []):
        return True
    return bool(list(getattr(message, "tool_call_chunks", None) or []))


def _emit_custom(event: str, data: object) -> None:
    payload = {"event": event, "data": data}
    parent = _parent_stream.get()
    if parent is None:
        try:
            parent = get_stream_writer()
        except RuntimeError:
            return
    try:
        parent(payload)
    except RuntimeError:
        return


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
        "do not pick a silent winner. State both sides with their [n] citations. "
        "For exact arithmetic on packed numbers, call calculator with expression "
        "(numeric literals only); cite operand [n], not the result."
    )


def _user_prompt(state: GraphState, formatted_chunks: str) -> str:
    language = _language(state)
    task = _current_task(state)
    feedback = _eval_feedback(state)
    history = format_transcript(
        last_exchanges(state.get("messages"), Policy.writer_history_exchanges)
    )
    parts = [
        f"Student query:\n{state.get('query') or ''}",
    ]
    if history:
        parts.append(f"Recent conversation:\n{history}")
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
        self._llm = ChatOpenAI(**kwargs)
        self._tools_node = ToolNode([calculator], handle_tool_errors=True)
        graph = StateGraph(MessagesState)
        graph.add_node("writer", self._call_model)
        graph.add_edge(START, "writer")
        graph.add_conditional_edges("writer", tools_condition)
        graph.add_node("tools", self._tools_node)
        graph.add_edge("tools", "writer")
        self._inner = graph.compile(checkpointer=None)

    async def _call_model(self, state: MessagesState) -> dict:
        messages = state["messages"]
        used = sum(
            isinstance(m, ToolMessage) and m.name == "calculator" for m in messages
        )
        llm = (
            self._llm.bind_tools([calculator])
            if used < Policy.writer_calculator_rounds
            else self._llm
        )
        parts: list[str] = []
        last: object | None = None
        async for chunk in llm.astream(messages):
            last = last + chunk if isinstance(last, AIMessageChunk) else chunk
            text = _visible_text(chunk)
            if text:
                parts.append(text)
            if text and not _has_tool_call(last):
                _emit_custom("answer_delta", {"text": text})
        tool_calls = list(getattr(last, "tool_calls", None) or [])
        content = last.content if isinstance(last, AIMessageChunk) else "".join(parts)
        return {
            "messages": [
                AIMessage(
                    content=content,
                    tool_calls=tool_calls,
                )
            ]
        }

    async def run(self, state: GraphState) -> dict:
        try:
            parent = get_stream_writer()
        except RuntimeError:
            parent = None
        token = _parent_stream.set(parent)
        try:
            return await self._run(state)
        finally:
            _parent_stream.reset(token)

    async def _run(self, state: GraphState) -> dict:
        chunks: list[EvidenceChunk] = list(state.get("evidence_chunks") or [])
        if not chunks:
            chunks = prior_citation_chunks(state)
            if not chunks:
                return {
                    "outcome": "insufficient",
                    "last_eval": {"feedback": "no evidence on this thread"},
                }
        message_id = str(uuid.uuid4())
        _emit_custom("answer_start", {"message_id": message_id})
        out = await self._inner.ainvoke(
            {
                "messages": [
                    SystemMessage(content=_system_prompt()),
                    HumanMessage(content=_user_prompt(state, _format_chunks(chunks))),
                ]
            }
        )
        final = next(
            (
                m
                for m in reversed(out["messages"])
                if isinstance(m, AIMessage) and not m.tool_calls
            ),
            None,
        )
        markdown = _visible_text(final) if final else ""
        citations = _citations_from_chunks(chunks, _used_citation_ns(markdown, chunks))
        _emit_custom("citations", {"citations": citations})
        return {
            "writer_markdown": markdown,
            "citations": citations,
            "writer_message_id": message_id,
            "last_agent": "writer",
        }
