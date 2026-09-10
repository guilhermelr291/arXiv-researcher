"""Evaluate node: wave vs step eval, admit, retry, replan (LOOP-01–05, SEARCH-01–02, CAP-02, WRITE-01, RETR-04)."""

from __future__ import annotations

from typing import Literal

from langgraph.config import get_stream_writer

from plan_based_researcher.eval.admission import finalize_wave_rankings
from plan_based_researcher.eval.strategies import (
    RetrieveEvalStrategy,
    SearchEvalStrategy,
)
from plan_based_researcher.eval.types import EvalResult
from plan_based_researcher.graph.nodes.dispatch import search_wave_indices
from plan_based_researcher.graph.state import GraphState
from plan_based_researcher.policy import Policy

__all__ = ["make_evaluate_node"]

_Status = Literal["pass", "retry", "fail"]


def _step_index(state: GraphState) -> int:
    try:
        return int(state.get("step_index") or 0)
    except (TypeError, ValueError):
        return 0


def _plan_agent(state: GraphState) -> str:
    plan = state.get("plan") or []
    idx = _step_index(state)
    if not isinstance(plan, list) or idx < 0 or idx >= len(plan):
        return ""
    step = plan[idx]
    if not isinstance(step, dict):
        return ""
    return str(step.get("agent") or "")


def _use_search_wave(state: GraphState, last_agent: str) -> bool:
    if last_agent == "search":
        return True
    if last_agent in ("retrieve", "writer"):
        return False
    agent = _plan_agent(state)
    if agent in ("retrieve", "writer"):
        return False
    return agent == "search" or bool(search_wave_indices(state))


def _first_unpassed(plan: object, passed_steps: list[int]) -> int:
    passed = set(passed_steps)
    if not isinstance(plan, list):
        return 0
    for i in range(len(plan)):
        if i not in passed:
            return i
    return len(plan)


def _copy_retry_counts(state: GraphState) -> dict:
    raw = state.get("retry_counts") or {}
    if not isinstance(raw, dict):
        return {}
    return {str(k): v for k, v in raw.items()}


def _writer_passed(plan: object, passed_steps: list[int]) -> bool:
    passed = set(passed_steps)
    if not isinstance(plan, list):
        return False
    for i, step in enumerate(plan):
        if i not in passed or not isinstance(step, dict):
            continue
        if step.get("agent") == "writer":
            return True
    return False


def _emit_eval(
    writer,
    *,
    status: str,
    feedback: str,
    agent: str,
    step_index: int,
    plan_inadequate: bool,
) -> None:
    writer({
        "event": "eval",
        "data": {
            "status": status,
            "feedback": feedback,
            "agent": agent,
            "step_index": step_index,
            "plan_inadequate": plan_inadequate,
        },
    })


def _last_eval(
    status: _Status,
    feedback: str,
    plan_inadequate: bool,
    step_index: int,
) -> dict:
    dump = EvalResult(
        status=status,
        feedback=feedback,
        plan_inadequate=plan_inadequate,
    ).model_dump()
    dump["step_index"] = step_index
    return dump


def _apply_route(
    update: dict,
    *,
    need_replan: bool,
    need_retry: bool,
    replan_used: bool,
    writer_passed: bool,
    has_unpassed: bool,
    writer_just_passed: bool,
) -> None:
    if writer_just_passed:
        update["eval_next"] = "finalize"
        update["outcome"] = "done"
        return
    if need_replan:
        if not replan_used:
            update["eval_next"] = "replan"
        else:
            update["eval_next"] = "finalize"
            update["outcome"] = "insufficient"
        return
    if need_retry:
        update["eval_next"] = "dispatch"
        return
    if not has_unpassed and not writer_passed:
        update["eval_next"] = "finalize"
        update["outcome"] = "insufficient"
        return
    update["eval_next"] = "dispatch"


def _apply_max_steps(state: GraphState, update: dict) -> dict:
    outcome = update.get("outcome") or state.get("outcome") or "pending"
    steps = update.get("steps_executed")
    if steps is None:
        steps = state.get("steps_executed") or 0
    if steps >= Policy.max_steps and outcome == "pending":
        update["outcome"] = "insufficient"
        update["eval_next"] = "finalize"
    return update


def _retry_status(retry_counts: dict, index: int) -> tuple[_Status, bool, bool]:
    """Increment-then-`>` cap. Returns status, need_replan, need_retry."""
    key = str(index)
    new_count = int(retry_counts.get(key, 0) or 0) + 1
    retry_counts[key] = new_count
    if new_count > Policy.max_retries_per_step:
        return "fail", True, False
    return "retry", False, True


def _retrieve_case(state: GraphState) -> str:
    ingest = state.get("retrieve_ingest") or {}
    if not isinstance(ingest, dict):
        return ""
    return str(ingest.get("case") or "")


def _chunk_key(chunk: dict) -> tuple[str, str] | None:
    aid = chunk.get("arxiv_id")
    if not aid:
        return None
    version = chunk.get("version")
    return (str(aid), str(version if version is not None else ""))


def _t3_query_miss(state: GraphState, result: EvalResult) -> bool:
    """Empty chunks, foreign chunk, or off-task (not paper-set inadequate)."""
    chunks = state.get("evidence_chunks") or []
    if not isinstance(chunks, list) or not chunks:
        return True
    admitted: set[tuple[str, str]] = set()
    papers = state.get("papers") or []
    if isinstance(papers, list):
        for paper in papers:
            if isinstance(paper, dict) and paper.get("arxiv_id"):
                version = paper.get("version")
                admitted.add(
                    (str(paper["arxiv_id"]), str(version if version is not None else ""))
                )
    for chunk in chunks:
        if not isinstance(chunk, dict):
            return True
        key = _chunk_key(chunk)
        if key is None or key not in admitted:
            return True
    if result.plan_inadequate:
        return False
    return True


def make_evaluate_node(
    search_eval: SearchEvalStrategy,
    retrieve_eval: RetrieveEvalStrategy,
):
    async def evaluate(state: GraphState) -> dict:
        last_agent = state.get("last_agent") or ""
        if _use_search_wave(state, last_agent):
            writer = get_stream_writer()
            return await _evaluate_wave(state, search_eval, writer)
        agent = last_agent if last_agent in ("retrieve", "writer") else _plan_agent(state)
        if agent == "writer":
            idx = _step_index(state)
            passed_steps = list(state.get("passed_steps") or [])
            if idx not in passed_steps:
                passed_steps.append(idx)
            plan = state.get("plan") or []
            step_index = _first_unpassed(plan, passed_steps)
            update: dict = {
                "passed_steps": passed_steps,
                "step_index": step_index,
            }
            _apply_route(
                update,
                need_replan=False,
                need_retry=False,
                replan_used=bool(state.get("replan_used") or False),
                writer_passed=_writer_passed(plan, passed_steps),
                has_unpassed=step_index < len(plan),
                writer_just_passed=True,
            )
            return _apply_max_steps(state, update)
        writer = get_stream_writer()
        result = await retrieve_eval.evaluate(state)
        return _evaluate_step(state, result, agent or "retrieve", writer)

    return evaluate


async def _evaluate_wave(state: GraphState, search_eval: SearchEvalStrategy, writer) -> dict:
    wave = search_wave_indices(state)
    judgement = await search_eval.evaluate_wave(state)
    plan = state.get("plan") or []
    passed_steps = list(state.get("passed_steps") or [])
    retry_counts = _copy_retry_counts(state)
    artifacts = state.get("search_artifacts") or {}
    if not isinstance(artifacts, dict):
        artifacts = {}

    finals = finalize_wave_rankings(
        wave, plan, artifacts, passed_steps, judgement
    )

    need_replan = False
    need_retry = False
    eval_by_step: dict[str, dict] = {}
    artifacts_patch: dict[str, dict] = {}

    for verdict in finals:
        i = verdict.step_index
        ranked = [
            {"arxiv_id": k.arxiv_id, "version": k.version}
            for k in verdict.ranked_keys
        ]
        if verdict.passed:
            status: _Status = "pass"
            if i not in passed_steps:
                passed_steps.append(i)
            existing = artifacts.get(str(i))
            if not isinstance(existing, dict):
                existing = {}
            artifacts_patch[str(i)] = {
                **existing,
                "ranked_keys": ranked,
            }
        else:
            status, cap_replan, cap_retry = _retry_status(retry_counts, i)
            need_replan = need_replan or cap_replan
            need_retry = need_retry or cap_retry

        _emit_eval(
            writer,
            status=status,
            feedback=verdict.feedback,
            agent="search",
            step_index=i,
            plan_inadequate=verdict.plan_inadequate,
        )
        eval_by_step[str(i)] = _last_eval(
            status, verdict.feedback, verdict.plan_inadequate, i
        )

    step_index = _first_unpassed(plan, passed_steps)
    retry_count = (
        int(retry_counts.get(str(step_index), 0) or 0)
        if step_index < len(plan)
        else 0
    )
    last_eval = eval_by_step.get(str(step_index)) or (
        eval_by_step[str(finals[-1].step_index)] if finals else dict(state.get("last_eval") or {})
    )

    update: dict = {
        "last_eval": last_eval,
        "eval_by_step": eval_by_step,
        "passed_steps": passed_steps,
        "retry_counts": retry_counts,
        "retry_count": retry_count,
        "step_index": step_index,
        "steps_executed": (state.get("steps_executed") or 0) + len(wave),
    }
    if artifacts_patch:
        update["search_artifacts"] = artifacts_patch
    _apply_route(
        update,
        need_replan=need_replan,
        need_retry=need_retry,
        replan_used=bool(state.get("replan_used") or False),
        writer_passed=_writer_passed(plan, passed_steps),
        has_unpassed=step_index < len(plan),
        writer_just_passed=False,
    )
    return _apply_max_steps(state, update)


def _evaluate_step(
    state: GraphState,
    result: EvalResult,
    agent: str,
    writer,
) -> dict:
    idx = _step_index(state)
    passed_steps = list(state.get("passed_steps") or [])
    retry_counts = _copy_retry_counts(state)
    need_replan = False
    need_retry = False
    writer_just_passed = False

    if result.status == "pass":
        status: _Status = "pass"
        if idx not in passed_steps:
            passed_steps.append(idx)
        if agent == "writer":
            writer_just_passed = True
    elif agent == "retrieve" and _retrieve_case(state) == "t3":
        if _t3_query_miss(state, result):
            status, need_replan, need_retry = _retry_status(retry_counts, idx)
        else:
            status = "fail"
            need_replan = True
    elif result.plan_inadequate:
        status = "fail"
        need_replan = True
    else:
        status, need_replan, need_retry = _retry_status(retry_counts, idx)

    _emit_eval(
        writer,
        status=status,
        feedback=result.feedback,
        agent=agent,
        step_index=idx,
        plan_inadequate=result.plan_inadequate,
    )

    plan = state.get("plan") or []
    step_index = _first_unpassed(plan, passed_steps)
    retry_count = 0 if result.status == "pass" else int(
        retry_counts.get(str(step_index), 0) or 0
    )

    record = _last_eval(
        status, result.feedback, result.plan_inadequate, idx
    )
    update: dict = {
        "last_eval": record,
        "eval_by_step": {str(idx): record},
        "passed_steps": passed_steps,
        "retry_counts": retry_counts,
        "retry_count": retry_count,
        "step_index": step_index,
    }
    _apply_route(
        update,
        need_replan=need_replan,
        need_retry=need_retry,
        replan_used=bool(state.get("replan_used") or False),
        writer_passed=_writer_passed(plan, passed_steps),
        has_unpassed=step_index < len(plan),
        writer_just_passed=writer_just_passed,
    )
    return _apply_max_steps(state, update)
