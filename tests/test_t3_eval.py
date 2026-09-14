"""T3 retrieve eval routes on likely_in_paper (ARX9-01)."""

from __future__ import annotations

import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from plan_based_researcher.eval.types import EvalResult
from plan_based_researcher.graph.nodes.evaluate import make_evaluate_node
from plan_based_researcher.policy import Policy

_WRITER_MODULE = "plan_based_researcher.graph.nodes.evaluate.get_stream_writer"

_PAPER = {
    "arxiv_id": "2609.11929",
    "version": "1",
    "title": "paper",
    "year": 2026,
    "url": "https://arxiv.org/abs/2609.11929",
    "categories": ["cs.LG"],
}
_CHUNK = {
    "chunk_id": "gold-b87b59a7",
    "n": 1,
    "arxiv_id": "2609.11929",
    "version": "1",
    "title": "paper",
    "year": 2026,
    "url": "https://arxiv.org/abs/2609.11929",
    "excerpt": "percentages 44 29 19 8",
}
_FOREIGN = {**_CHUNK, "chunk_id": "foreign", "arxiv_id": "1706.03762", "version": "7"}
_GAP = "absolute corpus N for generation editing interleaved"


def _spy_stream_writer(payloads: list[dict]):
    def get_stream_writer():
        def writer(payload: dict) -> None:
            payloads.append(payload)

        return writer

    return get_stream_writer


def _t3_state(
    *,
    chunks: list[dict] | None = None,
    retry_used: int = 0,
    ingest_case: str = "t3",
) -> dict:
    retry_counts = {}
    if retry_used:
        retry_counts["1"] = retry_used
    return {
        "last_agent": "retrieve",
        "step_index": 1,
        "plan": [
            {"agent": "search", "task": "find papers on the topic"},
            {"agent": "retrieve", "task": "retrieve corpus sizes and composition"},
            {"agent": "writer", "task": "write the grounded answer"},
        ],
        "passed_steps": [0],
        "outcome": "pending",
        "replan_used": False,
        "steps_executed": 2,
        "retry_counts": retry_counts,
        "papers": [_PAPER],
        "evidence_chunks": list(chunks) if chunks is not None else [_CHUNK],
        "retrieve_ingest": {"case": ingest_case, "gap_step_indices": [], "gap_tasks": [], "walked": False},
        "hole_tasks": [],
        "eval_by_step": {},
    }


class _FailSearch:
    async def evaluate_wave(self, state: dict) -> object:
        raise AssertionError("search_eval must not run for retrieve")


class T3EvalRoutesTest(unittest.IsolatedAsyncioTestCase):
    async def _run(self, result: EvalResult, state: dict | None = None) -> dict:
        retrieve_eval = MagicMock()
        retrieve_eval.evaluate = AsyncMock(return_value=result)
        evaluate = make_evaluate_node(_FailSearch(), retrieve_eval)
        payloads: list[dict] = []
        with patch(_WRITER_MODULE, _spy_stream_writer(payloads)):
            return await evaluate(state if state is not None else _t3_state())

    async def test_likely_in_paper_routes_all_four(self) -> None:
        cases = (
            ("na", True, False, False),
            ("yes", False, True, False),
            ("no", True, False, True),
            ("unknown", True, False, True),
        )
        for lip, passed, retry, hole in cases:
            with self.subTest(likely_in_paper=lip):
                update = await self._run(
                    EvalResult(
                        status="fail",
                        feedback=_GAP,
                        likely_in_paper=lip,
                    )
                )
                if passed:
                    self.assertIn(1, update["passed_steps"])
                else:
                    self.assertNotIn(1, update["passed_steps"])
                if retry:
                    self.assertEqual(update["eval_next"], "dispatch")
                    self.assertEqual(update["retry_counts"].get("1"), 1)
                else:
                    self.assertNotEqual(update.get("retry_counts", {}).get("1"), 1)
                    if passed and not hole:
                        self.assertEqual(update["eval_next"], "dispatch")
                holes = update.get("hole_tasks") or []
                if hole:
                    self.assertIn({"task": _GAP, "reason": "gap"}, holes)
                else:
                    self.assertNotIn({"task": _GAP, "reason": "gap"}, holes)

    async def test_likely_in_paper_commands_over_status(self) -> None:
        disagree = (
            ("na", "retry", True, False, False),
            ("yes", "pass", False, True, False),
            ("no", "retry", True, False, True),
            ("unknown", "pass", True, False, True),
        )
        for lip, status, passed, retry, hole in disagree:
            with self.subTest(likely_in_paper=lip, status=status):
                update = await self._run(
                    EvalResult(status=status, feedback=_GAP, likely_in_paper=lip)
                )
                if passed:
                    self.assertIn(1, update["passed_steps"])
                else:
                    self.assertNotIn(1, update["passed_steps"])
                if retry:
                    self.assertEqual(update["eval_next"], "dispatch")
                    self.assertEqual(update["retry_counts"].get("1"), 1)
                if hole:
                    self.assertIn(
                        {"task": _GAP, "reason": "gap"},
                        update.get("hole_tasks") or [],
                    )
                else:
                    self.assertNotIn(
                        {"task": _GAP, "reason": "gap"},
                        update.get("hole_tasks") or [],
                    )

    async def test_empty_likely_in_paper_pass_is_na(self) -> None:
        for raw in ("", "maybe"):
            with self.subTest(likely_in_paper=raw):
                update = await self._run(
                    EvalResult(status="pass", feedback=_GAP, likely_in_paper=raw)
                )
                self.assertIn(1, update["passed_steps"])
                self.assertNotIn(
                    {"task": _GAP, "reason": "gap"},
                    update.get("hole_tasks") or [],
                )
                self.assertNotEqual(update.get("retry_counts", {}).get("1"), 1)

    async def test_empty_likely_in_paper_retry_is_unknown(self) -> None:
        for raw in ("", "maybe"):
            with self.subTest(likely_in_paper=raw):
                update = await self._run(
                    EvalResult(status="retry", feedback=_GAP, likely_in_paper=raw)
                )
                self.assertIn(1, update["passed_steps"])
                self.assertIn(
                    {"task": _GAP, "reason": "gap"},
                    update.get("hole_tasks") or [],
                )
                self.assertNotEqual(update["eval_next"], "replan")
                self.assertNotEqual(update.get("retry_counts", {}).get("1"), 1)

    async def test_empty_likely_in_paper_fail_is_unknown(self) -> None:
        for raw in ("", "maybe"):
            with self.subTest(likely_in_paper=raw):
                update = await self._run(
                    EvalResult(status="fail", feedback=_GAP, likely_in_paper=raw)
                )
                self.assertIn(1, update["passed_steps"])
                self.assertIn(
                    {"task": _GAP, "reason": "gap"},
                    update.get("hole_tasks") or [],
                )
                self.assertNotEqual(update["eval_next"], "replan")

    async def test_t3_empty_chunks_retries(self) -> None:
        update = await self._run(
            EvalResult(status="retry", feedback="evidence_chunks is empty."),
            _t3_state(chunks=[]),
        )
        self.assertNotIn(1, update["passed_steps"])
        self.assertEqual(update["eval_next"], "dispatch")
        self.assertEqual(update["retry_counts"].get("1"), 1)

    async def test_t3_foreign_chunk_retries(self) -> None:
        update = await self._run(
            EvalResult(status="retry", feedback="Chunk is not from admitted papers."),
            _t3_state(chunks=[_FOREIGN]),
        )
        self.assertNotIn(1, update["passed_steps"])
        self.assertEqual(update["eval_next"], "dispatch")
        self.assertEqual(update["retry_counts"].get("1"), 1)

    async def test_t3_retry_exhausted_pass_hole_no_replan(self) -> None:
        self.assertEqual(Policy.max_retries_per_step, 1)
        update = await self._run(
            EvalResult(status="retry", feedback=_GAP, likely_in_paper="yes"),
            _t3_state(retry_used=1),
        )
        self.assertIn(1, update["passed_steps"])
        self.assertIn(
            {"task": _GAP, "reason": "gap"},
            update.get("hole_tasks") or [],
        )
        self.assertEqual(update["eval_next"], "dispatch")
        self.assertNotEqual(update["eval_next"], "replan")

    async def test_t1_no_query_retry_replans(self) -> None:
        update = await self._run(
            EvalResult(
                status="fail",
                plan_inadequate=True,
                feedback="T1: no usable papers after ingest. Do not retry the retrieve query.",
            ),
            _t3_state(chunks=[], ingest_case="t1"),
        )
        self.assertNotIn(1, update["passed_steps"])
        self.assertEqual(update["eval_next"], "replan")
        self.assertFalse(update.get("retry_counts", {}).get("1"))

    async def test_t2a_no_query_retry_replans(self) -> None:
        update = await self._run(
            EvalResult(
                status="fail",
                plan_inadequate=True,
                feedback=(
                    "T2a: at least one passed ranking ingested no usable HTML; "
                    "hybrid ran on living papers. Do not retry the retrieve query."
                ),
            ),
            _t3_state(ingest_case="t2a"),
        )
        self.assertNotIn(1, update["passed_steps"])
        self.assertEqual(update["eval_next"], "replan")
        self.assertFalse(update.get("retry_counts", {}).get("1"))

    async def test_likely_in_paper_no_does_not_set_plan_inadequate(self) -> None:
        update = await self._run(
            EvalResult(
                status="fail",
                plan_inadequate=True,
                feedback=_GAP,
                likely_in_paper="no",
            )
        )
        self.assertIn(1, update["passed_steps"])
        self.assertEqual(update["eval_next"], "dispatch")
        self.assertNotEqual(update["eval_next"], "replan")
        self.assertFalse((update.get("last_eval") or {}).get("plan_inadequate"))


if __name__ == "__main__":
    unittest.main()
