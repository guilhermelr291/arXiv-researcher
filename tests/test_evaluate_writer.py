"""WSTR-03: evaluate auto-passes Writer without Strategy or eval SSE."""

from __future__ import annotations

import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from plan_based_researcher.eval.types import EvalResult
from plan_based_researcher.graph.nodes.evaluate import make_evaluate_node

_WRITER_MODULE = "plan_based_researcher.graph.nodes.evaluate.get_stream_writer"


def _writer_state() -> dict:
    return {
        "last_agent": "writer",
        "step_index": 2,
        "plan": [
            {"agent": "search", "task": "find papers on the topic"},
            {"agent": "retrieve", "task": "retrieve evidence chunks"},
            {"agent": "writer", "task": "write the grounded answer"},
        ],
        "passed_steps": [0, 1],
        "outcome": "pending",
        "replan_used": False,
        "steps_executed": 3,
        "retry_counts": {},
    }


def _retrieve_state() -> dict:
    return {
        "last_agent": "retrieve",
        "step_index": 1,
        "plan": [
            {"agent": "search", "task": "find papers on the topic"},
            {"agent": "retrieve", "task": "retrieve evidence chunks"},
            {"agent": "writer", "task": "write the grounded answer"},
        ],
        "passed_steps": [0],
        "outcome": "pending",
        "replan_used": False,
        "steps_executed": 2,
        "retry_counts": {},
    }


class _FailIfCalled:
    async def evaluate(self, state: dict) -> EvalResult:
        raise AssertionError("eval strategy must not run for Writer")

    async def evaluate_wave(self, state: dict) -> object:
        raise AssertionError("search_eval.evaluate_wave must not run for Writer")


def _spy_stream_writer(payloads: list[dict]):
    def get_stream_writer():
        def writer(payload: dict) -> None:
            payloads.append(payload)

        return writer

    return get_stream_writer


class EvaluateWriterTest(unittest.IsolatedAsyncioTestCase):
    async def test_writer_last_agent_auto_passes_without_strategy(self) -> None:
        payloads: list[dict] = []
        evaluate = make_evaluate_node(_FailIfCalled(), _FailIfCalled())
        with patch(_WRITER_MODULE, _spy_stream_writer(payloads)):
            update = await evaluate(_writer_state())
        self.assertEqual(update["eval_next"], "finalize")
        self.assertEqual(update["outcome"], "done")
        self.assertIn(2, update["passed_steps"])

    async def test_writer_evaluate_emits_no_eval_sse(self) -> None:
        payloads: list[dict] = []
        evaluate = make_evaluate_node(_FailIfCalled(), _FailIfCalled())
        with patch(_WRITER_MODULE, _spy_stream_writer(payloads)):
            await evaluate(_writer_state())
        eval_events = [p for p in payloads if p.get("event") == "eval"]
        self.assertEqual(eval_events, [])

    async def test_retrieve_still_calls_strategy_and_emits_eval(self) -> None:
        payloads: list[dict] = []
        retrieve_eval = MagicMock()
        retrieve_eval.evaluate = AsyncMock(
            return_value=EvalResult(status="pass", feedback="ok")
        )
        evaluate = make_evaluate_node(_FailIfCalled(), retrieve_eval)
        with patch(_WRITER_MODULE, _spy_stream_writer(payloads)):
            await evaluate(_retrieve_state())
        retrieve_eval.evaluate.assert_awaited()
        self.assertTrue(any(p.get("event") == "eval" for p in payloads))


if __name__ == "__main__":
    unittest.main()
