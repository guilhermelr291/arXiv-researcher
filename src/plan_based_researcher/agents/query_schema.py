"""Structured query formulation shared by search and retrieve (SEARCH-01, RETR-01)."""

from __future__ import annotations

from pydantic import BaseModel, Field

__all__ = ["FormulatedQuery", "formulate_human", "step_eval_feedback"]


class FormulatedQuery(BaseModel):
    query: str = Field(description="The search or retrieval query string to execute")


def step_eval_feedback(state: dict, step_index: int) -> str:
    """Return eval feedback for this step; prefer eval_by_step over last_eval (LOOP-02)."""
    by_step = state.get("eval_by_step") or {}
    if isinstance(by_step, dict):
        rec = by_step.get(str(step_index))
        if rec is None:
            rec = by_step.get(step_index)
        if isinstance(rec, dict):
            feedback = str(rec.get("feedback") or "").strip()
            if feedback:
                return feedback
    last_eval = state.get("last_eval") or {}
    if not isinstance(last_eval, dict):
        return ""
    eval_step = last_eval.get("step_index")
    if eval_step is not None:
        try:
            if int(eval_step) != int(step_index):
                return ""
        except (TypeError, ValueError):
            return ""
    return str(last_eval.get("feedback") or "").strip()


def formulate_human(
    *,
    task: str,
    feedback: str = "",
    previous_query: str = "",
    historical: bool | None = None,
    student_query: str = "",
) -> str:
    parts = [f"Task:\n{task}"]
    if student_query.strip():
        parts.append(f"Student query:\n{student_query.strip()}")
    if historical is True:
        parts.append("Constraint: historical=true (do not bias toward recent papers).")
    if previous_query:
        parts.append(f"Previous query:\n{previous_query}")
    if feedback:
        parts.append(f"Evaluator feedback:\n{feedback}")
    return "\n\n".join(parts)
