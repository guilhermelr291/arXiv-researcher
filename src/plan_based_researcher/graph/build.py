"""Compile the research StateGraph once (PAT-01, PAT-07)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

from langgraph.graph import END, START, StateGraph

from plan_based_researcher.agents.factory import AgentFactory
from plan_based_researcher.eval.strategies import (
    RetrieveEvalStrategy,
    SearchEvalStrategy,
)
from plan_based_researcher.graph.nodes.dispatch import make_dispatch_node
from plan_based_researcher.graph.nodes.evaluate import make_evaluate_node
from plan_based_researcher.graph.nodes.execute import make_execute_node
from plan_based_researcher.graph.nodes.finalize import make_finalize_node
from plan_based_researcher.graph.nodes.gate import make_gate_node
from plan_based_researcher.graph.nodes.planner import make_planner_node
from plan_based_researcher.graph.nodes.replan import make_replan_node
from plan_based_researcher.graph.nodes.search import make_search_node
from plan_based_researcher.graph.state import GraphState

__all__ = ["GraphDeps", "build_graph"]


@dataclass(frozen=True, slots=True)
class GraphDeps:
    factory: AgentFactory
    search_eval: SearchEvalStrategy
    retrieve_eval: RetrieveEvalStrategy


def _after_gate(state: GraphState) -> Literal["planner", "finalize"]:
    if state.get("outcome") == "refused":
        return "finalize"
    return "planner"


def _after_evaluate(state: GraphState) -> Literal["dispatch", "replan", "finalize"]:
    outcome = state.get("outcome") or "pending"
    if outcome in ("done", "insufficient", "error", "refused"):
        return "finalize"
    next_node = state.get("eval_next")
    if next_node in ("dispatch", "replan", "finalize"):
        return next_node
    return "dispatch"


def build_graph(deps: GraphDeps, checkpointer: Any | None = None):
    """Compile gate → planner → dispatch → search|execute → evaluate → replan|finalize."""
    graph = StateGraph(GraphState)
    graph.add_node("gate", make_gate_node(deps.factory))
    graph.add_node("planner", make_planner_node(deps.factory))
    graph.add_node(
        "dispatch",
        make_dispatch_node(),
        destinations=("search", "execute", "finalize"),
    )
    graph.add_node("search", make_search_node(deps.factory))
    graph.add_node("execute", make_execute_node(deps.factory))
    graph.add_node(
        "evaluate",
        make_evaluate_node(deps.search_eval, deps.retrieve_eval),
    )
    graph.add_node("replan", make_replan_node(deps.factory))
    graph.add_node("finalize", make_finalize_node())

    graph.add_edge(START, "gate")
    graph.add_conditional_edges(
        "gate",
        _after_gate,
        {"planner": "planner", "finalize": "finalize"},
    )
    graph.add_edge("planner", "dispatch")
    graph.add_edge("search", "evaluate")
    graph.add_edge("execute", "evaluate")
    graph.add_conditional_edges(
        "evaluate",
        _after_evaluate,
        {"dispatch": "dispatch", "replan": "replan", "finalize": "finalize"},
    )
    graph.add_edge("replan", "dispatch")
    graph.add_edge("finalize", END)
    return graph.compile(checkpointer=checkpointer)
