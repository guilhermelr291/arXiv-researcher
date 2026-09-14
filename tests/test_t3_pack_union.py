"""First pack is pinned; union by chunk_id (ARX9-03)."""

from __future__ import annotations

import unittest
from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from plan_based_researcher.adapters.hybrid import HybridResult
from plan_based_researcher.agents.query_schema import FormulatedQuery
from plan_based_researcher.agents.retrieve import RetrieveRunner
from plan_based_researcher.policy import Policy
from plan_based_researcher.ports.chunks import ChunkRecord

_CHAT = "plan_based_researcher.agents.retrieve.ChatOpenAI"
_SCORE = "plan_based_researcher.agents.retrieve.score_chunks"
_TRACE = "plan_based_researcher.agents.retrieve.trace"
_PAPER = {
    "arxiv_id": "2609.11929",
    "version": "1",
    "title": "paper",
    "year": 2026,
    "url": "https://arxiv.org/abs/2609.11929",
    "categories": ["cs.LG"],
}


def _chunk(chunk_id: str) -> ChunkRecord:
    return ChunkRecord(
        chunk_id=chunk_id,
        arxiv_id="2609.11929",
        version="1",
        title="paper",
        year=2026,
        url="https://arxiv.org/abs/2609.11929",
        kind="prose",
        unit_id=None,
        content=f"body {chunk_id}",
        metadata={"section": "4.3", "caption": "", "unit_ids": []},
    )


def _evidence(chunk_id: str, n: int) -> dict:
    return {
        "chunk_id": chunk_id,
        "n": n,
        "arxiv_id": "2609.11929",
        "version": "1",
        "title": "paper",
        "year": 2026,
        "url": "https://arxiv.org/abs/2609.11929",
        "excerpt": f"keep {chunk_id}",
    }


class _Hybrid:
    def __init__(self, ids: list[str]) -> None:
        self.ids = ids
        self.k_values: list[int] = []

    async def retrieve(self, query: str, paper_keys: list, k: int) -> HybridResult:
        self.k_values.append(k)
        ranked = [_chunk(cid) for cid in self.ids]
        return HybridResult(ranked=ranked, corpus=ranked)


@asynccontextmanager
async def _fake_trace(*args, **kwargs):
    yield SimpleNamespace(end=lambda **k: None)


def _base_state(*, retry: int = 0, chunks: list[dict] | None = None) -> dict:
    return {
        "step_index": 1,
        "plan": [
            {"agent": "search", "task": "find papers"},
            {"agent": "retrieve", "task": "retrieve corpus sizes"},
            {"agent": "writer", "task": "write"},
        ],
        "passed_steps": [],
        "retry_counts": {"1": retry} if retry else {},
        "papers": [_PAPER],
        "evidence_chunks": chunks or [],
        "retrieve_query_used": "previous",
        "eval_by_step": {
            "1": {"feedback": "total corpus size", "step_index": 1}
        }
        if retry
        else {},
        "hole_tasks": [],
        "search_artifacts": {},
    }


def _runner(hybrid: _Hybrid) -> RetrieveRunner:
    formulate = MagicMock()
    formulate.ainvoke = AsyncMock(return_value=FormulatedQuery(query="formulated"))
    with patch(_CHAT) as chat:
        chat.return_value.with_structured_output.return_value = formulate
        runner = RetrieveRunner(
            papers=MagicMock(),
            chunks=MagicMock(),
            embeddings=MagicMock(),
            hybrid=hybrid,
            api_key="sk-test",
            voyage_api_key="v-test",
        )
    runner._formulate = formulate
    return runner


class T3PackUnionTest(unittest.IsolatedAsyncioTestCase):
    def test_policy_first_pass_cut_knobs(self) -> None:
        self.assertEqual(Policy.retrieve_rerank_top_n, 10)
        self.assertEqual(Policy.retrieve_rerank_margin, 0.20)
        self.assertEqual(Policy.retrieve_rerank_floor, 0.30)
        self.assertEqual(Policy.retrieve_retry_add_cap, 5)
        self.assertEqual(Policy.retrieve_pack_cap_after_retry, 15)

    async def test_retry_pins_first_pack_and_appends_n(self) -> None:
        first = [_evidence("keep-a", 1), _evidence("keep-b", 2), _evidence("keep-c", 3)]
        hybrid = _Hybrid(["new-d", "new-e"])
        runner = _runner(hybrid)

        def _score(chunks, query, api_key=""):
            return [0.9] * len(chunks)

        with patch(_SCORE, _score), patch(_TRACE, _fake_trace):
            out = await runner.run(_base_state(retry=1, chunks=first))
        ids = [row["chunk_id"] for row in out["evidence_chunks"]]
        ns = [row["n"] for row in out["evidence_chunks"]]
        self.assertEqual(ids[:3], ["keep-a", "keep-b", "keep-c"])
        self.assertEqual(ids[3:], ["new-d", "new-e"])
        self.assertEqual(ns, [1, 2, 3, 4, 5])

    async def test_retry_adds_at_most_five_new_ids(self) -> None:
        first = [_evidence(f"keep-{i}", i + 1) for i in range(8)]
        hybrid = _Hybrid([f"new-{i}" for i in range(10)])
        runner = _runner(hybrid)

        def _score(chunks, query, api_key=""):
            return [0.9] * len(chunks)

        with patch(_SCORE, _score), patch(_TRACE, _fake_trace):
            out = await runner.run(_base_state(retry=1, chunks=first))
        first_ids = {row["chunk_id"] for row in first}
        new_ids = [
            row["chunk_id"]
            for row in out["evidence_chunks"]
            if row["chunk_id"] not in first_ids
        ]
        self.assertEqual(Policy.retrieve_retry_add_cap, 5)
        self.assertLessEqual(len(new_ids), 5)
        self.assertEqual(len(new_ids), 5)

    async def test_retry_union_caps_at_fifteen(self) -> None:
        first = [_evidence(f"keep-{i}", i + 1) for i in range(10)]
        hybrid = _Hybrid([f"new-{i}" for i in range(10)])
        runner = _runner(hybrid)

        def _score(chunks, query, api_key=""):
            return [0.9] * len(chunks)

        with patch(_SCORE, _score), patch(_TRACE, _fake_trace):
            out = await runner.run(_base_state(retry=1, chunks=first))
        self.assertEqual(Policy.retrieve_pack_cap_after_retry, 15)
        self.assertLessEqual(len(out["evidence_chunks"]), 15)
        self.assertEqual(len(out["evidence_chunks"]), 15)

    async def test_first_pass_pack_at_most_ten(self) -> None:
        hybrid = _Hybrid([f"c{i}" for i in range(15)])
        runner = _runner(hybrid)

        def _score(chunks, query, api_key=""):
            return [0.9] * len(chunks)

        with patch(_SCORE, _score), patch(_TRACE, _fake_trace):
            out = await runner.run(_base_state(retry=0))
        self.assertLessEqual(len(out["evidence_chunks"]), 10)
        self.assertEqual(len(out["evidence_chunks"]), 10)

    async def test_retry_floor_miss_keeps_first_pack(self) -> None:
        first = [_evidence("keep-a", 1), _evidence("keep-b", 2)]
        hybrid = _Hybrid(["weak-1", "weak-2"])
        runner = _runner(hybrid)

        def _score(chunks, query, api_key=""):
            return [0.10] * len(chunks)

        with patch(_SCORE, _score), patch(_TRACE, _fake_trace):
            out = await runner.run(_base_state(retry=1, chunks=first))
        self.assertEqual(
            [row["chunk_id"] for row in out["evidence_chunks"]],
            ["keep-a", "keep-b"],
        )
        self.assertEqual([row["n"] for row in out["evidence_chunks"]], [1, 2])


if __name__ == "__main__":
    unittest.main()
