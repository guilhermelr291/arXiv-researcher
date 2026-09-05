"""Agent name → abilities, model, and tools (PAT-02). Planner prompt is built from this map."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

Role = Literal["gate", "planner", "search", "retrieve", "writer"]

_PLANNER_WRITER_MODEL = "gpt-5.6-luna"
_MINI_MODEL = "gpt-5.6-luna"

_PLAN_AGENT_ORDER = ("search", "retrieve", "writer")


@dataclass(frozen=True, slots=True)
class AgentSpec:
    name: str
    abilities: str
    model: str
    tools: tuple[str, ...]
    role: Role


REGISTRY: dict[str, AgentSpec] = {
    "gate": AgentSpec(
        name="gate",
        abilities=(
            "Decide if the student query is AI/ML in-domain. Never search arXiv."
        ),
        model=_MINI_MODEL,
        tools=(),
        role="gate",
    ),
    "planner": AgentSpec(
        name="planner",
        abilities=(
            "Produce an ordered plan of {agent, task, reasoning}. "
            "Each search is one named topic; on compare use distinct task texts. "
            "May mark historical steps. For same-thread follow-ups that already "
            "have papers, omit search (retrieve then writer)."
        ),
        model=_PLANNER_WRITER_MODEL,
        tools=(),
        role="planner",
    ),
    "search": AgentSpec(
        name="search",
        abilities=(
            "Search arXiv titles and abstracts for this step's research goal. "
            "Each search is one named topic. Ranking happens at eval, not in the "
            "runner; the runner does not pick a paper. "
            "Write the task as a natural-language goal, not an arXiv query; "
            "the search agent formulates the query. "
            "Apply allowlist and recency (or historical). Do not fetch HTML."
        ),
        model=_MINI_MODEL,
        tools=("arxiv_search",),
        role="search",
    ),
    "retrieve": AgentSpec(
        name="retrieve",
        abilities=(
            "Walk ranked_keys and ingest one usable HTML paper per ranking on cache miss; "
            "hybrid first-stage overfetch per paper, rerank against the "
            "evidence task, adaptive packed [n] cut, then expand. Write the task as "
            "what to evidence, not the retrieval query; the retrieve agent formulates "
            "the hybrid query. Do not search arXiv."
        ),
        model=_MINI_MODEL,
        tools=("arxiv_load",),
        role="retrieve",
    ),
    "writer": AgentSpec(
        name="writer",
        abilities=(
            "Write a didactic student answer citing only provided [n] chunks. "
            "State contradictions. No extra sources. Hole rule: no parametric "
            "fill; announce missing topics; do not teach missing methods from "
            "model weights."
        ),
        model=_PLANNER_WRITER_MODEL,
        tools=(),
        role="writer",
    ),
}

PLAN_AGENTS: frozenset[str] = frozenset({"search", "retrieve", "writer"})


def planner_prompt_abilities() -> str:
    """Concatenate plan-agent names and abilities for the planner prompt (PLAN-02)."""
    return "\n".join(
        f"{REGISTRY[name].name}: {REGISTRY[name].abilities}"
        for name in _PLAN_AGENT_ORDER
        if name in PLAN_AGENTS
    )
