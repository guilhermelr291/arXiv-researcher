"""Compile-once wrapper around the research StateGraph (STRM-06, STRM-08)."""

from __future__ import annotations

from typing import Any

from plan_based_researcher.graph.build import GraphDeps, build_graph


class ResearchGraph:
    def __init__(self, deps: GraphDeps, checkpointer: Any | None = None):
        self._compiled = build_graph(deps, checkpointer=checkpointer)

    def astream_events(self, input, config=None, **kwargs):
        return self._compiled.astream_events(input, config, **kwargs)

    def initial_graph_state(self, query: str) -> dict[str, Any]:
        return {
            "query": query,
            "messages": [{"role": "user", "content": query}],
            "papers": [],
            "plan": [],
            "step_index": 0,
            "passed_steps": [],
            "retry_counts": {},
            "retry_count": 0,
            "replan_used": False,
            "steps_executed": 0,
            "search_artifacts": {},
            "last_agent": "",
            "last_eval": {},
            "eval_by_step": {},
            "retrieve_query_used": "",
            "retrieve_ingest": {
                "case": "t3",
                "gap_step_indices": [],
                "gap_tasks": [],
                "walked": False,
            },
            "hole_tasks": [],
            "evidence_chunks": [],
            "writer_markdown": "",
            "citations": [],
            "outcome": "pending",
            "eval_next": "dispatch",
            "gate": {},
            "error_message": "",
            "reuse_existing_papers": False,
        }
