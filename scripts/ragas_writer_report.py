"""Score LangSmith Writer traces with RAGAS Faithfulness and AnswerRelevancy."""

from __future__ import annotations

import argparse
import asyncio
import os
import sys

from dotenv import load_dotenv
from langsmith import Client
from openai import AsyncOpenAI

from plan_based_researcher.eval.ragas_map import (
    excerpts_from_evidence_chunks,
    map_execute_run,
    unwrap_node_payload,
)

_DEFAULT_LIMIT = 20
_DEFAULT_PROJECT = "plan-based-researcher"
_EMBEDDING_MODEL = "text-embedding-3-small"
_DEFAULT_MAX_TOKENS = 16384


def main() -> None:
    load_dotenv()
    args = _parse_args()
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(_report(args))


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Print RAGAS Faithfulness and AnswerRelevancy for Writer traces "
            "in a LangSmith project."
        )
    )
    parser.add_argument(
        "--project",
        default=os.environ.get("LANGSMITH_PROJECT") or _DEFAULT_PROJECT,
        help="LangSmith project name.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=_DEFAULT_LIMIT,
        help=f"Max runs to list (default: {_DEFAULT_LIMIT}).",
    )
    parser.add_argument(
        "--run-id",
        default=None,
        help=(
            "Restrict to this run's trace. A LangGraph root id is OK; "
            "Writer execute children in that trace are scored."
        ),
    )
    parser.add_argument(
        "--write-feedback",
        action="store_true",
        help="Write scores to LangSmith feedback (default: off).",
    )
    return parser.parse_args()


def _patch_ragas_community_imports() -> None:
    """ragas 0.4.3 imports a langchain_community Vertex path removed in 0.4.x."""
    import types

    name = "langchain_community.chat_models.vertexai"
    if name not in sys.modules:
        stub = types.ModuleType(name)
        stub.ChatVertexAI = type("ChatVertexAI", (), {})
        sys.modules[name] = stub


def _load_metrics() -> tuple[object, object]:
    _patch_ragas_community_imports()
    try:
        from ragas.embeddings.base import embedding_factory
        from ragas.llms import llm_factory
        from ragas.metrics.collections import AnswerRelevancy, Faithfulness
    except ImportError as exc:
        print(f"Cannot import ragas metrics: {exc}", file=sys.stderr)
        print("If ragas is missing, install with: uv sync --extra ragas", file=sys.stderr)
        sys.exit(1)
    client = AsyncOpenAI()
    max_tokens = int(os.environ.get("RAGAS_MAX_TOKENS") or _DEFAULT_MAX_TOKENS)
    llm = llm_factory(
        os.environ.get("RAGAS_LLM_MODEL", "gpt-4o-mini"),
        client=client,
        max_tokens=max_tokens,
    )
    embeddings = embedding_factory(
        "openai",
        model=_EMBEDDING_MODEL,
        client=client,
    )
    return Faithfulness(llm=llm), AnswerRelevancy(llm=llm, embeddings=embeddings)


def _run_id(run: object) -> str | None:
    value = getattr(run, "id", None)
    if value is None:
        return None
    return str(value)


def _trace_id(run: object) -> str | None:
    value = getattr(run, "trace_id", None)
    if value is None:
        return None
    return str(value)


def _materialize_runs(
    client: Client,
    project: str,
    limit: int,
    run_id: str | None,
) -> list:
    kwargs: dict = {
        "project_name": project,
        "error": False,
        "limit": limit,
    }
    if run_id is None:
        return list(client.list_runs(**kwargs))
    targeted: list = []
    try:
        targeted = list(client.list_runs(**kwargs, run_ids=[run_id]))
    except TypeError:
        targeted = []
    if not targeted:
        targeted = [
            run
            for run in client.list_runs(**kwargs)
            if str(getattr(run, "id", "")) == run_id
        ]
    by_id: dict[str, object] = {}
    for run in targeted:
        rid = _run_id(run)
        if rid:
            by_id[rid] = run
    traces = {_trace_id(run) for run in targeted if _trace_id(run)}
    for trace_id in traces:
        for run in client.list_runs(
            project_name=project,
            error=False,
            trace_id=trace_id,
            limit=limit,
        ):
            rid = _run_id(run)
            if rid:
                by_id[rid] = run
    return list(by_id.values())


def _collect_retrieve_chunks(runs: list) -> dict[str, list[str]]:
    by_trace: dict[str, list[str]] = {}
    for run in runs:
        name = getattr(run, "name", None)
        if isinstance(name, str) and "rerank" in name:
            continue
        trace_id = _trace_id(run)
        if trace_id is None:
            continue
        outputs = unwrap_node_payload(getattr(run, "outputs", None))
        excerpts = excerpts_from_evidence_chunks(outputs.get("evidence_chunks"))
        if not excerpts:
            continue
        if trace_id not in by_trace:
            by_trace[trace_id] = excerpts
    return by_trace


def _write_feedback(client: Client, run_id: str, key: str, score: object) -> None:
    try:
        client.create_feedback(run_id=run_id, key=key, score=score)
    except Exception as exc:
        print(f"warning: create_feedback failed ({key}): {exc}", file=sys.stderr)


async def _report(args: argparse.Namespace) -> None:
    ls = Client()
    runs = _materialize_runs(ls, args.project, args.limit, args.run_id)
    retrieve_chunks = _collect_retrieve_chunks(runs)
    metrics: tuple[object, object] | None = None
    scored = 0
    for run in runs:
        rid = _run_id(run)
        triple = map_execute_run(
            run,
            retrieve_chunks_by_trace=retrieve_chunks,
        )
        if triple is None:
            if args.run_id is None:
                print(
                    f"skip run_id={rid} name={getattr(run, 'name', None)}: "
                    "incomplete triple (missing query, writer-facing chunks, or markdown)"
                )
            continue
        if not os.environ.get("OPENAI_API_KEY"):
            print("OPENAI_API_KEY is not set", file=sys.stderr)
            sys.exit(1)
        if metrics is None:
            metrics = _load_metrics()
        faithfulness, relevancy = metrics
        try:
            f = await faithfulness.ascore(
                user_input=triple["user_input"],
                response=triple["response"],
                retrieved_contexts=triple["retrieved_contexts"],
            )
            a = await relevancy.ascore(
                user_input=triple["user_input"],
                response=triple["response"],
            )
        except ValueError as exc:
            print(f"skip run_id={triple['run_id']}: {exc}")
            continue
        except Exception as exc:
            if exc.__class__.__name__ != "IncompleteOutputException":
                raise
            print(f"skip run_id={triple['run_id']}: {exc}")
            continue
        scored += 1
        print(
            f"run_id={triple['run_id']} "
            f"faithfulness={f.value} answer_relevancy={a.value}"
        )
        if args.write_feedback and triple["run_id"]:
            _write_feedback(ls, triple["run_id"], "faithfulness", f.value)
            _write_feedback(ls, triple["run_id"], "answer_relevancy", a.value)
    if args.run_id is not None and scored == 0:
        print(
            f"skip run_id={args.run_id}: no Writer execute in this trace "
            "with query, writer-facing chunks, and markdown "
            f"(loaded {len(runs)} same-trace runs)"
        )


if __name__ == "__main__":
    main()
