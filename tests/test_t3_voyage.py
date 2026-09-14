"""At most two Voyage rerank-3 calls per retrieve step (ARX9-04)."""

from __future__ import annotations

import unittest
from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from plan_based_researcher.adapters.hybrid import HybridResult
from plan_based_researcher.agents.query_schema import FormulatedQuery
from plan_based_researcher.agents.retrieve import RetrieveRunner
from plan_based_researcher.eval.strategies import install_t3_evaluate_routing
from plan_based_researcher.eval.types import EvalResult
from plan_based_researcher.graph.nodes.evaluate import make_evaluate_node
from plan_based_researcher.policy import Policy
from plan_based_researcher.ports.chunks import ChunkRecord

install_t3_evaluate_routing()

_CHAT = "plan_based_researcher.agents.retrieve.ChatOpenAI"
_SCORE = "plan_based_researcher.agents.retrieve.score_chunks"
_TRACE = "plan_based_researcher.agents.retrieve.trace"
_WRITER = "plan_based_researcher.graph.nodes.evaluate.get_stream_writer"
_PAPER = {
    "arxiv_id": "2609.11929",
    "version": "1",
    "title": "paper",
    "year": 2026,
    "url": "https://arxiv.org/abs/2609.11929",
    "categories": ["cs.LG"],
}
_KEEP_IDS = [f"keep-{i}" for i in range(8)]


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
        ranked = [_chunk(cid) for cid in self.ids[:k]]
        return HybridResult(ranked=ranked, corpus=ranked)


@asynccontextmanager
async def _fake_trace(*args, **kwargs):
    yield SimpleNamespace(end=lambda **k: None)


def _spy_stream_writer(payloads: list[dict]):
    def get_stream_writer():
        def writer(payload: dict) -> None:
            payloads.append(payload)

        return writer

    return get_stream_writer


def _state(*, retry: int = 0, chunks: list[dict] | None = None) -> dict:
    return {
        "last_agent": "retrieve",
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
        "retrieve_ingest": {
            "case": "t3",
            "gap_step_indices": [],
            "gap_tasks": [],
            "walked": False,
        },
        "outcome": "pending",
        "replan_used": False,
        "steps_executed": 2,
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


class _FailSearch:
    async def evaluate_wave(self, state: dict) -> object:
        raise AssertionError("search_eval must not run")


class T3VoyageBoundTest(unittest.IsolatedAsyncioTestCase):
    async def test_yes_retry_rerank_called_twice_not_on_union(self) -> None:
        calls: list[list[str]] = []

        def _score(chunks, query, api_key=""):
            calls.append([c.chunk_id for c in chunks])
            return [0.9] * len(chunks)

        first_hybrid = _Hybrid([f"c{i}" for i in range(12)])
        retry_hybrid = _Hybrid([f"new-{i}" for i in range(10)])
        first_runner = _runner(first_hybrid)
        retry_runner = _runner(retry_hybrid)
        with patch(_SCORE, _score), patch(_TRACE, _fake_trace):
            first = await first_runner.run(_state(retry=0))
            self.assertEqual(len(calls), 1)
            retry_state = _state(retry=1, chunks=first["evidence_chunks"])
            retried = await retry_runner.run(retry_state)
            self.assertEqual(len(calls), 2)
        union_ids = [row["chunk_id"] for row in retried["evidence_chunks"]]
        self.assertGreater(len(union_ids), len(calls[1]))
        self.assertNotEqual(calls[1], union_ids)

    async def test_retry_scores_short_list_not_keep_set(self) -> None:
        scored: list[list[str]] = []
        k_values: list[int] = []

        def _score(chunks, query, api_key=""):
            scored.append([c.chunk_id for c in chunks])
            return [0.9] * len(chunks)

        keep = [_evidence(cid, i + 1) for i, cid in enumerate(_KEEP_IDS)]
        hybrid = _Hybrid([f"new-{i}" for i in range(10)])
        runner = _runner(hybrid)
        with patch(_SCORE, _score), patch(_TRACE, _fake_trace):
            await runner.run(_state(retry=1, chunks=keep))
        self.assertEqual(hybrid.k_values, [Policy.retrieve_retry_first_stage_k])
        self.assertEqual(Policy.retrieve_retry_first_stage_k, 10)
        self.assertEqual(len(scored), 1)
        self.assertEqual(len(scored[0]), 10)
        self.assertNotEqual(len(scored[0]), 40)
        self.assertTrue(set(_KEEP_IDS).isdisjoint(scored[0]))

    async def test_na_no_unknown_rerank_once(self) -> None:
        for lip in ("na", "no", "unknown"):
            with self.subTest(likely_in_paper=lip):
                calls: list[int] = []

                def _score(chunks, query, api_key=""):
                    calls.append(len(chunks))
                    return [0.9] * len(chunks)

                hybrid = _Hybrid([f"c{i}" for i in range(12)])
                runner = _runner(hybrid)
                with patch(_SCORE, _score), patch(_TRACE, _fake_trace):
                    packed = await runner.run(_state(retry=0))
                self.assertEqual(len(calls), 1)
                retrieve_eval = MagicMock()
                retrieve_eval.evaluate = AsyncMock(
                    return_value=EvalResult(
                        status="fail",
                        feedback="absolute corpus N",
                        likely_in_paper=lip,
                    )
                )
                evaluate = make_evaluate_node(_FailSearch(), retrieve_eval)
                eval_state = {
                    **_state(retry=0, chunks=packed["evidence_chunks"]),
                    "passed_steps": [0],
                    "last_agent": "retrieve",
                }
                with patch(_WRITER, _spy_stream_writer([])):
                    update = await evaluate(eval_state)
                self.assertIn(1, update["passed_steps"])
                self.assertNotEqual(update.get("retry_counts", {}).get("1"), 1)
                self.assertEqual(len(calls), 1)


if __name__ == "__main__":
    unittest.main()
