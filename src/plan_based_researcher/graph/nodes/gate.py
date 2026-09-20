"""Gate graph node: domain check; refuse uses Writer text events."""

from __future__ import annotations

import uuid

from langgraph.config import get_stream_writer

from plan_based_researcher.agents.factory import AgentFactory
from plan_based_researcher.graph.state import GraphState


def make_gate_node(factory: AgentFactory):
    async def gate(state: GraphState) -> dict:
        writer = get_stream_writer()
        update = await factory.create("gate").run(state)
        data = update.get("gate") or {}
        if data.get("in_domain"):
            return update
        message_id = str(uuid.uuid4())
        writer({"event": "answer_start", "data": {"message_id": message_id}})
        writer(
            {
                "event": "answer_delta",
                "data": {"text": str(data.get("reason") or "")},
            }
        )
        return {**update, "writer_message_id": message_id}

    return gate
