"""Compact node: project a ready summary onto checkpoint messages, or start a job."""

from __future__ import annotations

import asyncio

from langgraph.config import get_config

from plan_based_researcher.agents.factory import AgentFactory
from plan_based_researcher.compaction import plan_compact
from plan_based_researcher.graph.state import GraphState


def make_compact_node(store, factory: AgentFactory):
    pending: list[asyncio.Task] = []

    async def compact(state: GraphState) -> dict:
        if store is None:
            return {}
        config = get_config()
        configurable = config.get("configurable") or {}
        thread_id = str(configurable.get("thread_id") or "")
        result = await plan_compact(
            state,
            store,
            thread_id=thread_id,
            summarizer=factory.create("summarizer"),
        )
        if result.job is not None:
            pending.append(result.job)
        return result.update

    return compact
