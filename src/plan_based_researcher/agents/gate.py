"""Gate agent: structured domain decision with no paper I/O (GATE-01, GATE-02)."""

from __future__ import annotations

from langchain_openai import ChatOpenAI

from plan_based_researcher.agents.registry import REGISTRY
from plan_based_researcher.api.schemas import GateDecision

_SYSTEM_PROMPT = (
    "You are a domain gate for an AI/ML student researcher. "
    "Allow only AI/ML questions that could be answered from arXiv CS/stat.ML papers "
    "(cs.AI, cs.LG, cs.CL, cs.CV, cs.NE, cs.RO, stat.ML). "
    "Infer query language (BCP-47). Never search papers. "
    "Student-facing reason MUST match the query language."
)


class GateRunner:
    def __init__(self, api_key: str | None = None) -> None:
        kwargs = {"model": REGISTRY["gate"].model}
        if api_key is not None:
            kwargs["api_key"] = api_key
        llm = ChatOpenAI(**kwargs)
        self._structured = llm.with_structured_output(
            GateDecision, method="json_schema"
        )

    async def run(self, state: dict) -> dict:
        decision = await self._structured.ainvoke(
            [
                ("system", _SYSTEM_PROMPT),
                ("human", state["query"]),
            ]
        )
        return {
            "gate": decision.model_dump(),
            "last_agent": "gate",
            "outcome": (
                "refused"
                if not decision.in_domain
                else state.get("outcome") or "pending"
            ),
        }
