"""Writer-pack recall: qrel coverage of graph evidence_chunks (RWR-01–RWR-04)."""

from __future__ import annotations

import asyncio
import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from plan_based_researcher.policy import Policy
from plan_based_researcher.ports.chunks import PaperRecord

__all__ = [
    "DEFAULT_KS",
    "InjectedHit",
    "ItemRun",
    "KScore",
    "QrelAtom",
    "QuestionScore",
    "RecallReport",
    "RetrieveDataset",
    "RetrieveItem",
    "admitted_paper_keys",
    "chunk_ids_from_evidence",
    "extract_retrieve_task",
    "filter_dataset",
    "load_dataset",
    "missing_qrel_ids",
    "paper_ref_from_record",
    "paper_report_key",
    "qrel_atoms_from_chunks",
    "recall_at_k",
    "resolve_dataset_path",
    "report_as_dict",
    "report_from_item_runs",
    "report_markdown",
    "report_output_paths",
    "run_e2e_item",
    "score_question",
    "stop_reason_from_state",
]

_ATOMIC_KINDS = frozenset({"table", "equation"})

DEFAULT_KS: tuple[int, ...] = (5, 10, Policy.retrieve_rerank_top_n)


@dataclass(frozen=True, slots=True)
class RetrieveItem:
    id: str
    query: str
    required_chunk_ids: tuple[str, ...]
    question_type: str = ""
    reference_answer: str = ""


@dataclass(frozen=True, slots=True)
class RetrieveDataset:
    arxiv_id: str
    version: str
    title: str
    items: tuple[RetrieveItem, ...]


@dataclass(frozen=True, slots=True)
class QrelAtom:
    kind: str
    content: str


@dataclass(frozen=True, slots=True)
class InjectedHit:
    chunk_id: str
    host_chunk_id: str
    kind: str


@dataclass(frozen=True, slots=True)
class KScore:
    k: int
    recall: float
    hits: tuple[str, ...]
    misses: tuple[str, ...]
    injected: tuple[InjectedHit, ...] = ()


@dataclass(frozen=True, slots=True)
class QuestionScore:
    id: str
    query: str
    question_type: str
    required_chunk_ids: tuple[str, ...]
    delivered_ids: tuple[str, ...]
    retrieve_query_used: str
    scores: tuple[KScore, ...]
    retrieve_task: str = ""
    admitted_papers: tuple[dict, ...] = ()
    stop_reason: str = ""
    thread_id: str = ""


@dataclass(frozen=True, slots=True)
class RecallReport:
    arxiv_id: str
    version: str
    ks: tuple[int, ...]
    items: tuple[QuestionScore, ...]
    macro: dict[int, float]
    micro: dict[int, float]


@dataclass(frozen=True, slots=True)
class ItemRun:
    query: str
    thread_id: str
    outcome: str
    stop_reason: str
    evidence_chunks: object
    retrieve_query_used: str
    retrieve_task: str
    admitted_papers: tuple[dict, ...]
    plan: list


def recall_at_k(
    relevant: set[str], ranked_ids: Sequence[str], k: int
) -> float:
    if k < 1:
        raise ValueError("k must be >= 1")
    if not relevant:
        raise ValueError("relevant must be non-empty")
    return len(set(ranked_ids[:k]) & relevant) / len(relevant)


def chunk_ids_from_evidence(chunks: object) -> list[str]:
    if not isinstance(chunks, list):
        return []
    ids: list[str] = []
    for item in chunks:
        if not isinstance(item, dict):
            continue
        chunk_id = item.get("chunk_id")
        if isinstance(chunk_id, str) and chunk_id.strip():
            ids.append(chunk_id)
    return ids


def score_question(
    *,
    question_id: str,
    query: str,
    required_chunk_ids: Sequence[str],
    evidence_chunks: object,
    ks: Sequence[int],
    question_type: str = "",
    retrieve_query_used: str = "",
    retrieve_task: str = "",
    admitted_papers: Sequence[Mapping[str, Any]] = (),
    stop_reason: str = "",
    thread_id: str = "",
    qrel_atoms: Mapping[str, QrelAtom] | None = None,
) -> QuestionScore:
    required = _required_order(required_chunk_ids)
    delivered = chunk_ids_from_evidence(evidence_chunks)
    atoms = qrel_atoms or {}
    return QuestionScore(
        id=question_id,
        query=query,
        question_type=question_type,
        required_chunk_ids=required,
        delivered_ids=tuple(delivered),
        retrieve_query_used=retrieve_query_used,
        scores=tuple(
            _k_score(required, evidence_chunks, k, atoms) for k in ks
        ),
        retrieve_task=retrieve_task,
        admitted_papers=tuple(dict(paper) for paper in admitted_papers),
        stop_reason=stop_reason,
        thread_id=thread_id,
    )


def qrel_atoms_from_chunks(chunks: Sequence[Any]) -> dict[str, QrelAtom]:
    atoms: dict[str, QrelAtom] = {}
    for chunk in chunks:
        chunk_id = getattr(chunk, "chunk_id", None)
        kind = getattr(chunk, "kind", None)
        content = getattr(chunk, "content", None)
        if not isinstance(chunk_id, str) or not chunk_id.strip():
            continue
        if not isinstance(kind, str) or not isinstance(content, str):
            continue
        atoms[chunk_id] = QrelAtom(kind=kind, content=content)
    return atoms


def extract_retrieve_task(plan: object, passed_steps: object) -> str:
    if not isinstance(plan, list):
        return ""
    task = ""
    for index in passed_steps if isinstance(passed_steps, Sequence) else ():
        if not isinstance(index, int) or index < 0 or index >= len(plan):
            continue
        step = plan[index]
        if not isinstance(step, dict) or step.get("agent") != "retrieve":
            continue
        text = step.get("task")
        task = text if isinstance(text, str) else ""
    return task


def admitted_paper_keys(papers: object) -> list[dict]:
    if not isinstance(papers, list):
        return []
    keys: list[dict] = []
    for paper in papers:
        if not isinstance(paper, dict):
            continue
        keys.append(
            {"arxiv_id": paper.get("arxiv_id"), "version": paper.get("version")}
        )
    return keys


def stop_reason_from_state(state: object, *, timed_out: bool) -> str:
    if timed_out:
        return "timeout"
    payload = state if isinstance(state, Mapping) else {}
    outcome = payload.get("outcome")
    if outcome == "refused":
        return "refused"
    if outcome == "error":
        return "error"
    if outcome == "insufficient":
        return "insufficient"
    if _writer_in_passed(payload):
        return "writer_ran"
    if outcome == "done":
        return "writer_skipped"
    return ""


def _writer_in_passed(state: Mapping[str, Any]) -> bool:
    plan = state.get("plan")
    passed_steps = state.get("passed_steps")
    if not isinstance(plan, list):
        return False
    for index in passed_steps if isinstance(passed_steps, Sequence) else ():
        if not isinstance(index, int) or index < 0 or index >= len(plan):
            continue
        step = plan[index]
        if isinstance(step, dict) and step.get("agent") == "writer":
            return True
    return False


def _required_order(required_chunk_ids: Sequence[str]) -> tuple[str, ...]:
    seen: set[str] = set()
    ordered: list[str] = []
    for chunk_id in required_chunk_ids:
        if not chunk_id or chunk_id in seen:
            continue
        seen.add(chunk_id)
        ordered.append(chunk_id)
    if not ordered:
        raise ValueError("required_chunk_ids must be non-empty")
    return tuple(ordered)


def _k_score(
    required: Sequence[str],
    evidence_chunks: object,
    k: int,
    qrel_atoms: Mapping[str, QrelAtom],
) -> KScore:
    prefix = _evidence_prefix(evidence_chunks, k)
    prefix_ids = {item[0] for item in prefix}
    hits: list[str] = []
    misses: list[str] = []
    injected: list[InjectedHit] = []
    for chunk_id in required:
        if chunk_id in prefix_ids:
            hits.append(chunk_id)
            continue
        host = _injected_host(chunk_id, prefix, qrel_atoms)
        if host is None:
            misses.append(chunk_id)
            continue
        hits.append(chunk_id)
        injected.append(
            InjectedHit(
                chunk_id=chunk_id,
                host_chunk_id=host,
                kind=qrel_atoms[chunk_id].kind,
            )
        )
    return KScore(
        k=k,
        recall=len(hits) / len(required),
        hits=tuple(hits),
        misses=tuple(misses),
        injected=tuple(injected),
    )


def _evidence_prefix(
    chunks: object, k: int
) -> list[tuple[str, str]]:
    if k < 1:
        raise ValueError("k must be >= 1")
    if not isinstance(chunks, list):
        return []
    prefix: list[tuple[str, str]] = []
    for item in chunks:
        if not isinstance(item, dict):
            continue
        chunk_id = item.get("chunk_id")
        if not isinstance(chunk_id, str) or not chunk_id.strip():
            continue
        excerpt = item.get("excerpt")
        prefix.append(
            (chunk_id, excerpt if isinstance(excerpt, str) else "")
        )
        if len(prefix) == k:
            break
    return prefix


def _injected_host(
    chunk_id: str,
    prefix: Sequence[tuple[str, str]],
    qrel_atoms: Mapping[str, QrelAtom],
) -> str | None:
    atom = qrel_atoms.get(chunk_id)
    if atom is None or atom.kind not in _ATOMIC_KINDS:
        return None
    body = atom.content.strip()
    if not body:
        return None
    for host_id, excerpt in prefix:
        if host_id == chunk_id:
            continue
        if body in excerpt:
            return host_id
    return None


def missing_qrel_ids(
    corpus_ids: set[str], items: Sequence[RetrieveItem]
) -> dict[str, list[str]]:
    missing: dict[str, list[str]] = {}
    for item in items:
        absent = [
            chunk_id
            for chunk_id in item.required_chunk_ids
            if chunk_id not in corpus_ids
        ]
        if absent:
            missing[item.id] = absent
    return missing


def paper_ref_from_record(paper: PaperRecord) -> dict:
    return {
        "arxiv_id": paper.arxiv_id,
        "version": paper.version,
        "title": paper.title,
        "year": paper.year,
        "url": paper.url,
        "categories": list(paper.categories),
    }


def resolve_dataset_path(raw: str, *, repo_root: Path) -> Path:
    path = Path(raw)
    if path.is_file():
        return path
    stem = path.stem if path.suffix.lower() == ".json" else path.name
    candidates = (
        repo_root / "eval" / "retrieve" / stem / f"{stem}.json",
        repo_root / "eval" / "retrieve" / path.name,
        repo_root / "eval" / "retrieve" / f"{stem}.json",
    )
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    return path


def load_dataset(path: Path) -> RetrieveDataset:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("dataset must be a JSON object")
    arxiv_id = _nonempty_str(payload.get("arxiv_id"), "arxiv_id")
    version = _nonempty_str(payload.get("version"), "version")
    title = str(payload.get("title") or "")
    if "questions" in payload and "items" not in payload:
        raise ValueError("items must be a non-empty list")
    raw_items = payload.get("items")
    if not isinstance(raw_items, list) or not raw_items:
        raise ValueError("items must be a non-empty list")
    items = tuple(
        _load_item(item, index, arxiv_id) for index, item in enumerate(raw_items)
    )
    seen_ids: set[str] = set()
    for item in items:
        if item.id in seen_ids:
            raise ValueError(f"duplicate item id: {item.id}")
        seen_ids.add(item.id)
    return RetrieveDataset(
        arxiv_id=arxiv_id,
        version=version,
        title=title,
        items=items,
    )


def filter_dataset(dataset: RetrieveDataset, item_id: str | None) -> RetrieveDataset:
    if item_id is None or not item_id.strip():
        return dataset
    wanted = item_id.strip()
    matched = tuple(item for item in dataset.items if item.id == wanted)
    if not matched:
        known = ", ".join(item.id for item in dataset.items)
        raise ValueError(f"unknown item id: {wanted} (have {known})")
    return RetrieveDataset(
        arxiv_id=dataset.arxiv_id,
        version=dataset.version,
        title=dataset.title,
        items=matched,
    )


def paper_report_key(arxiv_id: str, version: str) -> str:
    return f"{arxiv_id}v{version}"


def report_output_paths(
    out_dir: Path,
    *,
    arxiv_id: str,
    version: str,
    scored_at: str,
    item_id: str = "",
) -> tuple[Path, Path, Path]:
    paper_dir = out_dir / paper_report_key(arxiv_id, version)
    stamp = scored_at.replace(":", "").replace("-", "")
    suffix = f"_{item_id}" if item_id.strip() else ""
    stem = f"{stamp}{suffix}"
    return paper_dir / f"{stem}.json", paper_dir / f"{stem}.md", paper_dir / "index.jsonl"


def _load_item(item: object, index: int, arxiv_id: str) -> RetrieveItem:
    if not isinstance(item, dict):
        raise ValueError(f"items[{index}] must be an object")
    item_id = _nonempty_str(item.get("id"), f"items[{index}].id")
    query = _nonempty_str(item.get("query"), f"items[{index}].query")
    if arxiv_id not in query:
        raise ValueError(f"items[{index}].query must contain arxiv_id")
    raw_ids = item.get("required_chunk_ids")
    if not isinstance(raw_ids, list) or not raw_ids:
        raise ValueError(f"items[{index}].required_chunk_ids must be a non-empty list")
    chunk_ids: list[str] = []
    for raw in raw_ids:
        if not isinstance(raw, str) or not raw.strip():
            raise ValueError(
                f"items[{index}].required_chunk_ids must be non-empty strings"
            )
        chunk_ids.append(raw.strip())
    question_type = str(item.get("question_type") or "")
    reference_answer = str(item.get("reference_answer") or "")
    return RetrieveItem(
        id=item_id,
        query=query,
        required_chunk_ids=tuple(chunk_ids),
        question_type=question_type,
        reference_answer=reference_answer,
    )


def _nonempty_str(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} must be a non-empty string")
    return value.strip()


def _averages(rows: Sequence[QuestionScore], ks: Sequence[int]) -> tuple[dict[int, float], dict[int, float]]:
    macro: dict[int, float] = {}
    micro: dict[int, float] = {}
    n = len(rows)
    for k in ks:
        macro[k] = sum(_score_at(row, k).recall for row in rows) / n
        hits = 0
        total = 0
        for row in rows:
            total += len(row.required_chunk_ids)
            hits += len(_score_at(row, k).hits)
        micro[k] = hits / total if total else 0.0
    return macro, micro


def _score_at(row: QuestionScore, k: int) -> KScore:
    for item in row.scores:
        if item.k == k:
            return item
    raise KeyError(k)


def _timeout_item_run(*, query: str, thread_id: str) -> ItemRun:
    return ItemRun(
        query=query,
        thread_id=thread_id,
        outcome="",
        stop_reason="timeout",
        evidence_chunks=[],
        retrieve_query_used="",
        retrieve_task="",
        admitted_papers=(),
        plan=[],
    )


async def run_e2e_item(
    graph: Any,
    *,
    query: str,
    thread_id: str,
    timeout_seconds: float,
) -> ItemRun:
    try:
        state = await asyncio.wait_for(
            graph.ainvoke(
                graph.initial_graph_state(query),
                config={
                    "configurable": {"thread_id": thread_id},
                    "metadata": {"eval": "retrieve-writer-recall"},
                },
            ),
            timeout=timeout_seconds,
        )
    except (TimeoutError, asyncio.TimeoutError, asyncio.CancelledError):
        return _timeout_item_run(query=query, thread_id=thread_id)
    payload = state if isinstance(state, dict) else {}
    plan = payload.get("plan")
    if not isinstance(plan, list):
        plan = []
    passed_steps = payload.get("passed_steps")
    papers = payload.get("papers")
    outcome = payload.get("outcome")
    query_used = payload.get("retrieve_query_used")
    evidence = payload.get("evidence_chunks")
    if evidence is None:
        evidence = []
    return ItemRun(
        query=query,
        thread_id=thread_id,
        outcome=outcome if isinstance(outcome, str) else "",
        stop_reason=stop_reason_from_state(payload, timed_out=False),
        evidence_chunks=evidence,
        retrieve_query_used=query_used if isinstance(query_used, str) else "",
        retrieve_task=extract_retrieve_task(plan, passed_steps),
        admitted_papers=tuple(admitted_paper_keys(papers)),
        plan=plan,
    )


def report_from_item_runs(
    dataset: RetrieveDataset,
    runs: Sequence[ItemRun],
    *,
    ks: Sequence[int] = DEFAULT_KS,
    qrel_atoms: Mapping[str, QrelAtom] | None = None,
) -> RecallReport:
    if len(runs) != len(dataset.items):
        raise ValueError("runs must match dataset items")
    ks_t = tuple(ks)
    atoms = qrel_atoms or {}
    rows = tuple(
        score_question(
            question_id=item.id,
            query=item.query,
            required_chunk_ids=item.required_chunk_ids,
            evidence_chunks=run.evidence_chunks,
            ks=ks_t,
            question_type=item.question_type,
            retrieve_query_used=run.retrieve_query_used,
            retrieve_task=run.retrieve_task,
            admitted_papers=run.admitted_papers,
            stop_reason=run.stop_reason,
            thread_id=run.thread_id,
            qrel_atoms=atoms,
        )
        for item, run in zip(dataset.items, runs, strict=True)
    )
    macro, micro = _averages(rows, ks_t)
    return RecallReport(
        arxiv_id=dataset.arxiv_id,
        version=dataset.version,
        ks=ks_t,
        items=rows,
        macro=macro,
        micro=micro,
    )


def report_as_dict(report: RecallReport) -> dict:
    return {
        "arxiv_id": report.arxiv_id,
        "version": report.version,
        "ks": list(report.ks),
        "macro": {str(k): v for k, v in report.macro.items()},
        "micro": {str(k): v for k, v in report.micro.items()},
        "items": [
            {
                "id": row.id,
                "query": row.query,
                "question_type": row.question_type,
                "required_chunk_ids": list(row.required_chunk_ids),
                "delivered_ids": list(row.delivered_ids),
                "retrieve_query_used": row.retrieve_query_used,
                "retrieve_task": row.retrieve_task,
                "admitted_papers": list(row.admitted_papers),
                "stop_reason": row.stop_reason,
                "thread_id": row.thread_id,
                "scores": [
                    {
                        "k": item.k,
                        "recall": item.recall,
                        "hits": list(item.hits),
                        "misses": list(item.misses),
                        "injected": [
                            {
                                "chunk_id": hit.chunk_id,
                                "host_chunk_id": hit.host_chunk_id,
                                "kind": hit.kind,
                            }
                            for hit in item.injected
                        ],
                    }
                    for item in row.scores
                ],
            }
            for row in report.items
        ],
    }


def report_markdown(report: RecallReport) -> str:
    lines = [
        f"# Writer-pack recall `{report.arxiv_id}v{report.version}`",
        "",
        "| k | macro | micro |",
        "| --- | ---: | ---: |",
    ]
    for k in report.ks:
        lines.append(
            f"| {k} | {report.macro[k]:.3f} | {report.micro[k]:.3f} |"
        )
    lines.extend(["", "## Items", ""])
    for row in report.items:
        lines.append(f"### {row.id}")
        lines.append("")
        lines.append(row.query)
        lines.append("")
        if row.retrieve_task:
            lines.append(f"Retrieve task: {row.retrieve_task}")
            lines.append("")
        if row.admitted_papers:
            keys = ", ".join(
                f"{paper.get('arxiv_id') or ''}v{paper.get('version') or ''}"
                for paper in row.admitted_papers
            )
            lines.append(f"Admitted: {keys}")
            lines.append("")
        if row.retrieve_query_used:
            lines.append(f"Hybrid query: `{row.retrieve_query_used}`")
            lines.append("")
        lines.append(
            f"Delivered ({len(row.delivered_ids)}): "
            + (", ".join(row.delivered_ids) if row.delivered_ids else "(none)")
        )
        lines.append("")
        for hit in _injected_for_item(row):
            lines.append(
                f"Injected: `{hit.chunk_id}` ({hit.kind}) into "
                f"`{hit.host_chunk_id}`"
            )
            lines.append("")
        for item in row.scores:
            miss = ", ".join(item.misses) if item.misses else "(none)"
            lines.append(
                f"- Recall@{item.k} = {item.recall:.3f}; misses: {miss}"
            )
        lines.append("")
    return "\n".join(lines)


def _injected_for_item(row: QuestionScore) -> tuple[InjectedHit, ...]:
    if not row.scores:
        return ()
    return max(row.scores, key=lambda item: item.k).injected
