"""T3 retrieve retry query is the gap only (ARX9-02)."""

from __future__ import annotations

import unittest
from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from plan_based_researcher.adapters.hybrid import HybridResult
from plan_based_researcher.agents.query_schema import FormulatedQuery
from plan_based_researcher.agents.retrieve import RetrieveRunner
from plan_based_researcher.eval.types import RetrieveJudgeVerdict
from plan_based_researcher.policy import Policy
from plan_based_researcher.ports.chunks import ChunkRecord

_TASK = "Retrieve generation, editing, and interleaved corpus sizes and composition"
_FEEDBACK = "total corpus size of generation editing interleaved mix"
_PREV = "generation editing interleaved percentages"
_STUDENT = "Quais tamanhos do corpus de geração, edição e interleaved?"
_PAPER = {
    "arxiv_id": "2609.11929",
    "version": "1",
    "title": "paper",
    "year": 2026,
    "url": "https://arxiv.org/abs/2609.11929",
    "categories": ["cs.LG"],
}

_CHAT = "plan_based_researcher.agents.retrieve.ChatOpenAI"
_SCORE = "plan_based_researcher.agents.retrieve.score_chunks"
_TRACE = "plan_based_researcher.agents.retrieve.trace"


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


class _Hybrid:
    def __init__(self) -> None:
        self.calls: list[tuple[str, list, int]] = []

    async def retrieve(self, query: str, paper_keys: list, k: int) -> HybridResult:
        self.calls.append((query, paper_keys, k))
        ranked = [_chunk(f"r{i}") for i in range(k)]
        return HybridResult(ranked=ranked, corpus=ranked)


@asynccontextmanager
async def _fake_trace(*args, **kwargs):
    yield SimpleNamespace(end=lambda **k: None)


def _retry_state() -> dict:
    first = [
        {
            "chunk_id": f"keep-{i}",
            "n": i + 1,
            "arxiv_id": "2609.11929",
            "version": "1",
            "title": "paper",
            "year": 2026,
            "url": "https://arxiv.org/abs/2609.11929",
            "excerpt": f"keep {i}",
        }
        for i in range(3)
    ]
    return {
        "step_index": 1,
        "plan": [
            {"agent": "search", "task": "find papers"},
            {"agent": "retrieve", "task": _TASK},
            {"agent": "writer", "task": "write"},
        ],
        "passed_steps": [0],
        "retry_counts": {"1": 1},
        "papers": [_PAPER],
        "evidence_chunks": first,
        "retrieve_query_used": _PREV,
        "eval_by_step": {"1": {"feedback": _FEEDBACK, "step_index": 1}},
        "hole_tasks": [],
        "search_artifacts": {},
        "query": _STUDENT,
    }


def _runner(hybrid: _Hybrid) -> tuple[RetrieveRunner, MagicMock]:
    formulate = MagicMock()
    formulate.ainvoke = AsyncMock(
        return_value=FormulatedQuery(query="formulated-should-not-be-hybrid")
    )
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
    return runner, formulate


class T3QueryTest(unittest.IsolatedAsyncioTestCase):
    def test_retrieve_eval_schema_field_order(self) -> None:
        names = list(RetrieveJudgeVerdict.model_fields)
        self.assertEqual(names, ["reasoning", "likely_in_paper", "feedback"])
        lip = RetrieveJudgeVerdict.model_fields["likely_in_paper"]
        self.assertIn("na", str(lip.annotation))
        self.assertIn("yes", str(lip.annotation))
        self.assertIn("no", str(lip.annotation))
        self.assertIn("unknown", str(lip.annotation))
        self.assertNotIn("gap_query", names)
        for value in ("na", "yes", "no", "unknown"):
            RetrieveJudgeVerdict(
                reasoning="English reason",
                likely_in_paper=value,
                feedback="English feedback",
            )

    async def test_retry_hybrid_and_voyage_query_is_feedback_only(self) -> None:
        hybrid = _Hybrid()
        runner, _formulate = _runner(hybrid)
        voyage_queries: list[str] = []

        def _score(chunks, query, api_key=""):
            voyage_queries.append(query)
            return [0.9] * len(chunks)

        with patch(_SCORE, _score), patch(_TRACE, _fake_trace):
            await runner.run(_retry_state())
        self.assertEqual(len(hybrid.calls), 1)
        hybrid_query = hybrid.calls[0][0]
        self.assertEqual(hybrid_query, _FEEDBACK)
        self.assertNotIn(_TASK, hybrid_query)
        self.assertEqual(voyage_queries, [_FEEDBACK])
        self.assertNotIn(_TASK, voyage_queries[0])

    async def test_retry_hybrid_and_voyage_use_feedback_only(self) -> None:
        hybrid = _Hybrid()
        runner, _formulate = _runner(hybrid)
        voyage_queries: list[str] = []

        def _score(chunks, query, api_key=""):
            voyage_queries.append(query)
            return [0.9] * len(chunks)

        with patch(_SCORE, _score), patch(_TRACE, _fake_trace):
            out = await runner.run(_retry_state())
        self.assertEqual(hybrid.calls[0][0], _FEEDBACK)
        self.assertEqual(hybrid.calls[0][2], Policy.retrieve_retry_first_stage_k)
        self.assertEqual(voyage_queries, [_FEEDBACK])
        self.assertEqual(Policy.retrieve_retry_add_cap, 5)
        self.assertEqual(Policy.retrieve_pack_cap_after_retry, 15)
        self.assertLessEqual(len(out["evidence_chunks"]), 15)
        keep_ids = {row["chunk_id"] for row in _retry_state()["evidence_chunks"]}
        packed_ids = {row["chunk_id"] for row in out["evidence_chunks"]}
        self.assertTrue(keep_ids.issubset(packed_ids))

    async def test_retry_formulate_omits_full_task(self) -> None:
        hybrid = _Hybrid()
        runner, formulate = _runner(hybrid)

        def _score(chunks, query, api_key=""):
            return [0.9] * len(chunks)

        with patch(_SCORE, _score), patch(_TRACE, _fake_trace):
            await runner.run(_retry_state())
        formulate.ainvoke.assert_awaited()
        messages = formulate.ainvoke.call_args.args[0]
        human = messages[1][1]
        self.assertIn(_FEEDBACK, human)
        self.assertIn(_PREV, human)
        self.assertNotIn(f"Task:\n{_TASK}", human)
        self.assertNotIn(_STUDENT, human)

    async def test_first_pass_formulate_includes_student_query(self) -> None:
        hybrid = _Hybrid()
        runner, formulate = _runner(hybrid)
        state = _retry_state()
        state["retry_counts"] = {}
        state["eval_by_step"] = {}
        state["passed_steps"] = []

        def _score(chunks, query, api_key=""):
            return [0.9] * len(chunks)

        with patch(_SCORE, _score), patch(_TRACE, _fake_trace):
            await runner.run(state)
        formulate.ainvoke.assert_awaited()
        human = formulate.ainvoke.call_args.args[0][1][1]
        self.assertIn(f"Task:\n{_TASK}", human)
        self.assertIn(f"Student query:\n{_STUDENT}", human)


if __name__ == "__main__":
    unittest.main()
