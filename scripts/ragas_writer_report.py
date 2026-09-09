"""Score LangSmith Writer traces with RAGAS Faithfulness and AnswerRelevancy."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

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
_REPO_ROOT = Path(__file__).resolve().parents[1]
_DEFAULT_OUT_DIR = _REPO_ROOT / "reports" / "ragas"


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
            "in a LangSmith project, including judge reasoning, and save "
            "JSON/Markdown under reports/ragas/."
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
    parser.add_argument(
        "--no-save",
        action="store_true",
        help="Do not write reports/ragas JSON and Markdown (default: save).",
    )
    parser.add_argument(
        "--out-dir",
        default=None,
        help=f"Directory for JSON/Markdown reports (default: {_DEFAULT_OUT_DIR}).",
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
        from ragas.metrics.result import MetricResult
    except ImportError as exc:
        print(f"Cannot import ragas metrics: {exc}", file=sys.stderr)
        print("If ragas is missing, install with: uv sync --extra ragas", file=sys.stderr)
        sys.exit(1)

    class FaithfulnessLogged(Faithfulness):
        async def ascore(self, user_input, response, retrieved_contexts):
            if not response:
                raise ValueError(
                    "response is missing. Please add response to the test sample."
                )
            if not user_input:
                raise ValueError(
                    "user_input is missing. Please add user_input to the test sample."
                )
            if not retrieved_contexts:
                raise ValueError(
                    "retrieved_contexts is missing. Please add retrieved_contexts "
                    "to the test sample."
                )
            statements = await self._create_statements(user_input, response)
            if not statements:
                return MetricResult(
                    value=float("nan"),
                    reason="no atomic statements generated",
                    traces={"output": {"statements": []}},
                )
            context_str = "\n".join(retrieved_contexts)
            verdicts = await self._create_verdicts(statements, context_str)
            score = self._compute_score(verdicts)
            rows = [item.model_dump() for item in verdicts.statements]
            return MetricResult(
                value=float(score),
                reason=_faithfulness_reason(rows),
                traces={"output": {"statements": rows}},
            )

    class AnswerRelevancyLogged(AnswerRelevancy):
        async def ascore(self, user_input, response):
            import numpy as np

            if not user_input:
                raise ValueError("user_input cannot be empty")
            if not response:
                raise ValueError("response cannot be empty")
            generated_questions = []
            noncommittal_flags = []
            for _ in range(self.strictness):
                input_data = self.prompt.input_model(response=response)
                prompt_string = self.prompt.to_string(input_data)
                result = await self.llm.agenerate(
                    prompt_string,
                    self.prompt.output_model,
                )
                if result.question:
                    generated_questions.append(result.question)
                    noncommittal_flags.append(result.noncommittal)
            if not generated_questions:
                return MetricResult(
                    value=0.0,
                    reason="no questions generated from the response",
                    traces={"output": {"generated_questions": []}},
                )
            all_noncommittal = np.all(noncommittal_flags)
            question_vec = np.asarray(
                await self.embeddings.aembed_text(user_input)
            ).reshape(1, -1)
            gen_question_vec = np.asarray(
                await self.embeddings.aembed_texts(generated_questions)
            ).reshape(len(generated_questions), -1)
            norm = np.linalg.norm(gen_question_vec, axis=1) * np.linalg.norm(
                question_vec, axis=1
            )
            cosine_sim = (
                np.dot(gen_question_vec, question_vec.T).reshape(-1) / norm
            )
            score = cosine_sim.mean() * int(not all_noncommittal)
            similarities = [float(item) for item in cosine_sim]
            flags = [int(item) for item in noncommittal_flags]
            detail = {
                "generated_questions": generated_questions,
                "noncommittal": flags,
                "similarities": similarities,
                "all_noncommittal": bool(all_noncommittal),
            }
            return MetricResult(
                value=float(score),
                reason=_relevancy_reason(detail),
                traces={"output": detail},
            )

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
    return FaithfulnessLogged(llm=llm), AnswerRelevancyLogged(
        llm=llm,
        embeddings=embeddings,
    )


def _faithfulness_reason(rows: list[dict]) -> str:
    if not rows:
        return "no NLI verdicts"
    parts = []
    for row in rows:
        label = "supported" if row.get("verdict") else "unsupported"
        statement = str(row.get("statement") or "").strip()
        why = str(row.get("reason") or "").strip()
        parts.append(f"[{label}] {statement} — {why}")
    return "\n".join(parts)


def _relevancy_reason(detail: dict) -> str:
    questions = detail.get("generated_questions") or []
    similarities = detail.get("similarities") or []
    flags = detail.get("noncommittal") or []
    if detail.get("all_noncommittal"):
        prefix = "All generated questions marked noncommittal; score forced to 0. "
    else:
        prefix = ""
    lines = []
    for question, sim, flag in zip(questions, similarities, flags):
        lines.append(
            f"generated={question!r} similarity={float(sim):.4f} noncommittal={flag}"
        )
    return prefix + "; ".join(lines)


def _output_trace(result: object) -> dict:
    traces = getattr(result, "traces", None)
    if not isinstance(traces, dict):
        return {}
    output = traces.get("output")
    return output if isinstance(output, dict) else {}


def _json_float(value: object) -> float | None:
    try:
        number = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None
    if number != number:
        return None
    return number


def _metric_block(result: object, extra_key: str) -> dict:
    output = _output_trace(result)
    block = {
        "value": _json_float(getattr(result, "value", None)),
        "reason": getattr(result, "reason", None),
    }
    extra = output.get(extra_key)
    if extra is not None:
        block[extra_key] = extra
    for key, value in output.items():
        if key != extra_key:
            block[key] = value
    return block


def _md_cell(text: object) -> str:
    return str(text).replace("|", "\\|").replace("\n", " ").strip()


def _report_payload(
    *,
    scored_at: str,
    project: str,
    triple: dict,
    faithfulness: object,
    relevancy: object,
) -> dict:
    return {
        "scored_at": scored_at,
        "project": project,
        "langsmith_run_id": triple["run_id"],
        "judge_model": os.environ.get("RAGAS_LLM_MODEL", "gpt-4o-mini"),
        "embedding_model": _EMBEDDING_MODEL,
        "user_input": triple["user_input"],
        "retrieved_contexts": triple["retrieved_contexts"],
        "response": triple["response"],
        "metrics": {
            "faithfulness": _metric_block(faithfulness, "statements"),
            "answer_relevancy": _metric_block(relevancy, "generated_questions"),
        },
    }


def _markdown_report(payload: dict) -> str:
    faith = payload["metrics"]["faithfulness"]
    relevancy = payload["metrics"]["answer_relevancy"]
    lines = [
        f"# RAGAS Writer report `{payload['langsmith_run_id']}`",
        "",
        f"- scored_at: `{payload['scored_at']}`",
        f"- project: `{payload['project']}`",
        f"- judge: `{payload['judge_model']}` + `{payload['embedding_model']}`",
        "",
        "## Query",
        "",
        payload["user_input"],
        "",
        f"## Faithfulness: {faith.get('value')}",
        "",
        "| verdict | statement | reason |",
        "| --- | --- | --- |",
    ]
    for row in faith.get("statements") or []:
        lines.append(
            f"| {_md_cell(row.get('verdict'))} | {_md_cell(row.get('statement'))} "
            f"| {_md_cell(row.get('reason'))} |"
        )
    lines.extend(
        [
            "",
            f"## Answer relevancy: {relevancy.get('value')}",
            "",
            "| generated question | similarity | noncommittal |",
            "| --- | --- | --- |",
        ]
    )
    questions = relevancy.get("generated_questions") or []
    similarities = relevancy.get("similarities") or []
    flags = relevancy.get("noncommittal") or []
    for question, sim, flag in zip(questions, similarities, flags):
        lines.append(
            f"| {_md_cell(question)} | {_md_cell(f'{float(sim):.4f}')} | {_md_cell(flag)} |"
        )
    if relevancy.get("all_noncommittal"):
        lines.extend(["", "All generated questions were marked noncommittal."])
    lines.extend(["", "## Retrieved contexts", ""])
    for index, context in enumerate(payload["retrieved_contexts"], start=1):
        lines.append(f"{index}. {_md_cell(context)}")
    lines.extend(["", "## Response", "", payload["response"], ""])
    return "\n".join(lines)


def _write_report(out_dir: Path, payload: dict) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = payload["scored_at"].replace(":", "").replace("-", "")
    stem = f"{stamp}_{payload['langsmith_run_id']}"
    json_path = out_dir / f"{stem}.json"
    md_path = out_dir / f"{stem}.md"
    json_path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    md_path.write_text(_markdown_report(payload), encoding="utf-8")
    index_path = out_dir / "index.jsonl"
    index_line = {
        "scored_at": payload["scored_at"],
        "langsmith_run_id": payload["langsmith_run_id"],
        "project": payload["project"],
        "faithfulness": payload["metrics"]["faithfulness"].get("value"),
        "answer_relevancy": payload["metrics"]["answer_relevancy"].get("value"),
        "file": json_path.name,
    }
    with index_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(index_line, ensure_ascii=False) + "\n")
    return json_path


def _print_reasoning(faithfulness: object, relevancy: object) -> None:
    faith_reason = getattr(faithfulness, "reason", None)
    if faith_reason:
        print("faithfulness reasoning:")
        print(faith_reason)
    relevancy_reason = getattr(relevancy, "reason", None)
    if relevancy_reason:
        print("answer_relevancy reasoning:")
        print(relevancy_reason)


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


def _write_feedback(
    client: Client,
    run_id: str,
    key: str,
    score: object,
    comment: object,
) -> None:
    kwargs: dict = {"run_id": run_id, "key": key, "score": score}
    text = str(comment).strip() if comment else ""
    if text:
        kwargs["comment"] = text[:4000]
    try:
        client.create_feedback(**kwargs)
    except Exception as exc:
        print(f"warning: create_feedback failed ({key}): {exc}", file=sys.stderr)


async def _report(args: argparse.Namespace) -> None:
    ls = Client()
    runs = _materialize_runs(ls, args.project, args.limit, args.run_id)
    retrieve_chunks = _collect_retrieve_chunks(runs)
    metrics: tuple[object, object] | None = None
    scored = 0
    out_dir = Path(args.out_dir) if args.out_dir else _DEFAULT_OUT_DIR
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
        _print_reasoning(f, a)
        if not args.no_save:
            scored_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
            payload = _report_payload(
                scored_at=scored_at,
                project=args.project,
                triple=triple,
                faithfulness=f,
                relevancy=a,
            )
            try:
                path = _write_report(out_dir, payload)
            except OSError as exc:
                print(f"warning: could not save report: {exc}", file=sys.stderr)
            else:
                try:
                    shown = path.relative_to(_REPO_ROOT)
                except ValueError:
                    shown = path
                print(f"wrote {shown}")
        if args.write_feedback and triple["run_id"]:
            _write_feedback(
                ls,
                triple["run_id"],
                "faithfulness",
                f.value,
                getattr(f, "reason", None),
            )
            _write_feedback(
                ls,
                triple["run_id"],
                "answer_relevancy",
                a.value,
                getattr(a, "reason", None),
            )
    if args.run_id is not None and scored == 0:
        print(
            f"skip run_id={args.run_id}: no Writer execute in this trace "
            "with query, writer-facing chunks, and markdown "
            f"(loaded {len(runs)} same-trace runs)"
        )


if __name__ == "__main__":
    main()
