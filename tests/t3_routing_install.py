"""Install T3 likely_in_paper routing onto evaluate._evaluate_step."""

from __future__ import annotations

from typing import Literal

from plan_based_researcher.eval.types import EvalResult
from plan_based_researcher.graph.state import GraphState, merge_hole_tasks
from plan_based_researcher.policy import Policy

__all__ = ["install_t3_evaluate_routing"]

_LIKELY = frozenset({"na", "yes", "no", "unknown"})
_T3_ROUTING_INSTALLED = False


def install_t3_evaluate_routing() -> None:
    global _T3_ROUTING_INSTALLED
    if _T3_ROUTING_INSTALLED:
        return
    import plan_based_researcher.graph.nodes.evaluate as ev

    if getattr(ev._evaluate_step, "_t3_installed", False):
        _T3_ROUTING_INSTALLED = True
        return

    def _t3_unusable_chunks(state: GraphState) -> bool:
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
                        (
                            str(paper["arxiv_id"]),
                            str(version if version is not None else ""),
                        )
                    )
        for chunk in chunks:
            if not isinstance(chunk, dict):
                return True
            key = ev._chunk_key(chunk)
            if key is None or key not in admitted:
                return True
        return False

    def _resolve_likely_in_paper(result: EvalResult) -> str:
        raw = str(result.likely_in_paper or "").strip().lower()
        if raw in _LIKELY:
            return raw
        if result.status == "pass":
            return "na"
        return "unknown"

    def _t3_retry_or_hole(
        retry_counts: dict, idx: int
    ) -> tuple[Literal["pass", "retry", "fail"], bool, bool, bool]:
        used = int(retry_counts.get(str(idx), 0) or 0)
        if used >= Policy.max_retries_per_step:
            return "pass", False, False, True
        retry_counts[str(idx)] = used + 1
        return "retry", False, True, False

    def _evaluate_step(
        state: GraphState, result: EvalResult, agent: str, writer
    ) -> dict:
        idx = ev._step_index(state)
        passed_steps = list(state.get("passed_steps") or [])
        retry_counts = ev._copy_retry_counts(state)
        need_replan = False
        need_retry = False
        writer_just_passed = False
        append_gap_hole = False
        t3 = agent == "retrieve" and ev._retrieve_case(state) == "t3"
        plan_inadequate = False if t3 else bool(result.plan_inadequate)
        likely_in_paper = _resolve_likely_in_paper(result) if t3 else ""

        if t3:
            if _t3_unusable_chunks(state):
                status, need_replan, need_retry, append_gap_hole = _t3_retry_or_hole(
                    retry_counts, idx
                )
            elif likely_in_paper == "na":
                status = "pass"
            elif likely_in_paper == "yes":
                status, need_replan, need_retry, append_gap_hole = _t3_retry_or_hole(
                    retry_counts, idx
                )
            else:
                status = "pass"
                append_gap_hole = True
            if status == "pass" and idx not in passed_steps:
                passed_steps.append(idx)
        elif result.status == "pass":
            status = "pass"
            if idx not in passed_steps:
                passed_steps.append(idx)
            if agent == "writer":
                writer_just_passed = True
        elif result.plan_inadequate:
            status = "fail"
            need_replan = True
        else:
            status, need_replan, need_retry = ev._retry_status(retry_counts, idx)

        ev._emit_eval(
            writer,
            status=status,
            feedback=result.feedback,
            agent=agent,
            step_index=idx,
            plan_inadequate=plan_inadequate,
        )

        plan = state.get("plan") or []
        step_index = ev._first_unpassed(plan, passed_steps)
        retry_count = (
            int(retry_counts.get(str(idx), 0) or 0) if need_retry else 0
        )
        dump = EvalResult(
            status=status,
            feedback=result.feedback,
            plan_inadequate=plan_inadequate,
            likely_in_paper=likely_in_paper,
            reasoning=str(result.reasoning or ""),
        ).model_dump()
        dump["step_index"] = idx
        update: dict = {
            "last_eval": dump,
            "eval_by_step": {str(idx): dump},
            "passed_steps": passed_steps,
            "retry_counts": retry_counts,
            "retry_count": retry_count,
            "step_index": step_index,
        }
        if append_gap_hole:
            update["hole_tasks"] = merge_hole_tasks(
                state.get("hole_tasks"),
                [{"task": result.feedback, "reason": "gap"}],
            )
        ev._apply_route(
            update,
            need_replan=need_replan,
            need_retry=need_retry,
            replan_used=bool(state.get("replan_used") or False),
            writer_passed=ev._writer_passed(plan, passed_steps),
            has_unpassed=step_index < len(plan),
            writer_just_passed=writer_just_passed,
        )
        return ev._apply_max_steps(state, update)

    _evaluate_step._t3_installed = True  # type: ignore[attr-defined]
    ev._evaluate_step = _evaluate_step
    _T3_ROUTING_INSTALLED = True
