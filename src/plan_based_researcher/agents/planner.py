"""Planner runner: structured ResearchPlan, PLAN_AGENTS-validated steps (PLAN-02, REPLAN-01, REPLAN-02)."""

from __future__ import annotations

import json

from langchain_openai import ChatOpenAI

from plan_based_researcher.agents.registry import PLAN_AGENTS, REGISTRY, planner_prompt_abilities
from plan_based_researcher.api.schemas import ResearchPlan

__all__ = ["PlannerRunner"]


def _papers_blob(papers: object) -> str:
    if not papers:
        return "(none)"
    return json.dumps(papers, default=str)


def _plan_steps(state: dict) -> list:
    plan = state.get("plan") or []
    return plan if isinstance(plan, list) else []


def _passed_indices(state: dict) -> list[int]:
    indices: list[int] = []
    for i in state.get("passed_steps") or []:
        try:
            indices.append(int(i))
        except (TypeError, ValueError):
            continue
    return indices


def _search_artifact(artifacts: object, step_index: int) -> dict | None:
    if not isinstance(artifacts, dict):
        return None
    art = artifacts.get(str(step_index))
    if art is None:
        art = artifacts.get(step_index)
    return art if isinstance(art, dict) else None


def _champion_title(artifacts: object, step_index: int) -> str | None:
    art = _search_artifact(artifacts, step_index)
    if art is None:
        return None
    ranked = art.get("ranked_keys") or []
    if not ranked:
        return None
    head = ranked[0]
    if not isinstance(head, dict):
        return None
    arxiv_id = str(head.get("arxiv_id") or "")
    version = str(head.get("version") or "")
    for hit in art.get("hits") or []:
        if not isinstance(hit, dict):
            continue
        if str(hit.get("arxiv_id") or "") != arxiv_id:
            continue
        if str(hit.get("version") or "") != version:
            continue
        title = hit.get("title")
        if title:
            return str(title)
        return None
    return None


def _prefix_summary(state: dict) -> str:
    steps = _plan_steps(state)
    artifacts = state.get("search_artifacts") or {}
    lines: list[str] = []
    for idx in _passed_indices(state):
        if not (0 <= idx < len(steps) and isinstance(steps[idx], dict)):
            lines.append(f"[{idx}]")
            continue
        step = steps[idx]
        task = step.get("task")
        agent = step.get("agent")
        title = _champion_title(artifacts, idx)
        if title:
            lines.append(f"[{idx}] {agent}: {task} | champion: {title}")
        else:
            lines.append(f"[{idx}] {agent}: {task}")
    return "\n".join(lines) if lines else "(none)"


def _leftover_indexed(state: dict) -> list[tuple[int, dict]]:
    steps = _plan_steps(state)
    passed = set(_passed_indices(state))
    leftover: list[tuple[int, dict]] = []
    for idx, step in enumerate(steps):
        if idx in passed:
            continue
        leftover.append((idx, step if isinstance(step, dict) else {}))
    return leftover


def _leftover_steps(state: dict) -> str:
    leftover: list[dict] = []
    for idx, step in _leftover_indexed(state):
        leftover.append({"index": idx, **step})
    return json.dumps(leftover, default=str) if leftover else "(none)"


def _eval_by_step_record(state: dict, index: int) -> dict:
    by_step = state.get("eval_by_step") or {}
    if not isinstance(by_step, dict):
        return {}
    rec = by_step.get(str(index))
    if rec is None:
        rec = by_step.get(index)
    return rec if isinstance(rec, dict) else {}


def _step_agent(state: dict, index: int) -> str | None:
    steps = _plan_steps(state)
    if not (0 <= index < len(steps) and isinstance(steps[index], dict)):
        return None
    agent = steps[index].get("agent")
    return str(agent) if agent is not None else None


def _replan_constraints(state: dict) -> str:
    lines: list[str] = []
    for idx, step in _leftover_indexed(state):
        if step.get("agent") != "search":
            continue
        task = step.get("task") or ""
        rec = _eval_by_step_record(state, idx)
        if rec.get("plan_inadequate"):
            lines.append(
                f"S8a: leftover search index {idx} (task: {task}) has "
                "plan_inadequate=true → MUST NOT emit a new search for this topic. "
                "Typical suffix: retrieve + writer comparing evidenced topics and "
                "stating the hole; no parametric fill."
            )
        else:
            lines.append(
                f"S8a: leftover search index {idx} (task: {task}) has "
                "plan_inadequate=false → MUST emit one corrected search for this "
                "topic (angle / alias / historical) then retrieve + writer."
            )

    ingest = state.get("retrieve_ingest") or {}
    case = ingest.get("case") if isinstance(ingest, dict) else None
    if case == "t2a":
        lines.append(
            "Retrieve T2a: prefer writer-only suffix when evidence_chunks is "
            "non-empty. Writer task: living topics with [n]; state that no usable "
            "paper HTML was found for each gapped search task; forbid filling "
            "from memory. Dead search stays in prefix passed_steps."
        )
    elif case == "t1":
        lines.append(
            "Retrieve T1: MUST NOT emit a new search (searches already passed; "
            "failure is HTML ingest). Suffix still needs a writer."
        )
    elif case == "t3":
        try:
            failed_index = int(state.get("step_index") or 0)
        except (TypeError, ValueError):
            failed_index = 0
        if _step_agent(state, failed_index) == "retrieve":
            lines.append(
                "Retrieve T3 exhausted: rewrite remaining, usually Writer task "
                "(same papers already ingested)."
            )

    return "\n".join(lines) if lines else "(none)"


def _failed_blob(state: dict) -> str:
    steps = _plan_steps(state)
    last_eval = state.get("last_eval") or {}
    try:
        step_index = int(state.get("step_index") or 0)
    except (TypeError, ValueError):
        step_index = 0
    head: object = "(none)"
    if 0 <= step_index < len(steps) and isinstance(steps[step_index], dict):
        step = steps[step_index]
        head = {"index": step_index, "agent": step.get("agent"), "task": step.get("task")}
    return json.dumps({"failed_head": head, "last_eval": last_eval}, default=str)


class PlannerRunner:
    def __init__(self, api_key: str | None = None) -> None:
        kwargs: dict = {"model": REGISTRY["planner"].model}
        if api_key is not None:
            kwargs["api_key"] = api_key
        self._llm = ChatOpenAI(**kwargs).with_structured_output(ResearchPlan)

    async def _complete(self, prompt: str) -> dict:
        plan = await self._llm.ainvoke(prompt)
        if not isinstance(plan, ResearchPlan):
            plan = ResearchPlan.model_validate(plan)
        for step in plan.steps:
            if step.agent not in PLAN_AGENTS:
                raise ValueError(f"invalid agent name: {step.agent}")
        return {
            "plan": [step.model_dump() for step in plan.steps],
            "last_agent": "planner",
        }

    async def run(self, state: dict) -> dict:
        query = state.get("query") or ""
        papers = state.get("papers") or []
        prompt = (
            "Produce an ordered executable plan. Each step is "
            "{agent, task, reasoning, historical}.\n"
            "Write every task and reasoning in English, even when the student "
            "query is not English. The writer, not the planner, matches the "
            "student's language.\n"
            "Write each task as a natural-language research or writing goal. "
            "Do not put arXiv search syntax in task; search and retrieve agents "
            "formulate their own queries.\n"
            "Each search is one named topic (one ranking, at most one paper). "
            "On compare, use distinct task texts — never one search covering "
            "several named methods.\n"
            "Typical shapes:\n"
            "- explain: search → retrieve → writer (one search task for that topic).\n"
            "- compare: one search per distinct topic (distinct task texts) → retrieve → writer.\n"
            "- same-thread follow-up with papers already on this thread: "
            "retrieve → writer (omit search).\n"
            "Do not add extra searches for variants unless the student named them.\n"
            "Set historical=True when a step needs a foundational/original paper "
            "(original Transformer, original LoRA) so the 5-year filter is off. "
            "Do not write 'recent' into a task that requires that original paper. "
            "If the student asked only for recent work on one method, one non-historical "
            "search for that method is enough; do not demand the original paper.\n\n"
            "Available agents:\n"
            f"{planner_prompt_abilities()}\n\n"
            f"Query:\n{query}\n\n"
            f"Papers already on this thread:\n{_papers_blob(papers)}"
        )
        return await self._complete(prompt)

    async def replan_remaining(self, state: dict) -> dict:
        query = state.get("query") or ""
        papers = state.get("papers") or []
        prompt = (
            "Rewrite ONLY the remaining suffix of the plan. Do not repeat passed prefix steps. "
            "Output steps are the suffix only; the graph concatenates prefix + suffix. "
            "Empty steps is allowed.\n"
            "Example: if a compare plan's later search (e.g. DoRA) failed after LoRA and QLoRA "
            "searches passed, remaining should be retrieve + writer tasked to compare topics "
            "that HAVE evidence and state the missing topic WITHOUT evidence. "
            "Do not keep a Writer still asked to compare three topics as evidenced.\n"
            "Write every remaining task and reasoning in English, even when the "
            "student query is not English.\n"
            "Write each remaining task as a natural-language goal, not arXiv syntax.\n"
            "Set historical=True on a step when older papers are needed.\n\n"
            "Available agents:\n"
            f"{planner_prompt_abilities()}\n\n"
            f"Student query:\n{query}\n\n"
            f"Committed prefix (passed steps):\n{_prefix_summary(state)}\n\n"
            f"Admitted papers:\n{_papers_blob(papers)}\n\n"
            f"Failed step(s) + feedback:\n{_failed_blob(state)}\n\n"
            f"Leftover unpassed steps:\n{_leftover_steps(state)}\n\n"
            f"Replan constraints:\n{_replan_constraints(state)}"
        )
        return await self._complete(prompt)
