"""Agent factory: registry name → runner lookup (PAT-02)."""

from __future__ import annotations

from typing import Protocol

from plan_based_researcher.adapters.hybrid import HybridRetrievePort
from plan_based_researcher.agents.gate import GateRunner
from plan_based_researcher.agents.planner import PlannerRunner
from plan_based_researcher.agents.retrieve import RetrieveRunner
from plan_based_researcher.agents.search import SearchRunner
from plan_based_researcher.agents.writer import WriterRunner
from plan_based_researcher.ports.chunks import ChunkRepository
from plan_based_researcher.ports.embeddings import EmbeddingPort
from plan_based_researcher.ports.papers import PaperPort


class AgentRunner(Protocol):
    async def run(self, state: dict) -> dict: ...


class AgentFactory:
    """Bind runners once; dispatch by registry name, not if/elif."""

    def __init__(
        self,
        papers: PaperPort,
        chunks: ChunkRepository,
        embeddings: EmbeddingPort,
        hybrid: HybridRetrievePort,
        api_key: str | None = None,
        *,
        voyage_api_key: str,
    ) -> None:
        self._runners: dict[str, AgentRunner] = {
            "gate": GateRunner(api_key=api_key),
            "planner": PlannerRunner(api_key=api_key),
            "search": SearchRunner(papers, api_key=api_key),
            "retrieve": RetrieveRunner(
                papers,
                chunks,
                embeddings,
                hybrid,
                api_key=api_key,
                voyage_api_key=voyage_api_key,
            ),
            "writer": WriterRunner(api_key=api_key),
        }

    def create(self, name: str) -> AgentRunner:
        try:
            return self._runners[name]
        except KeyError:
            raise KeyError(f"unknown agent: {name}") from None
