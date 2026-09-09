"""WSTR-04: finalize emits done without answer_complete; halt paths unchanged."""

from __future__ import annotations

import inspect
import unittest
from unittest.mock import patch

from plan_based_researcher.graph.nodes import finalize as finalize_mod
from plan_based_researcher.graph.nodes.finalize import make_finalize_node

_WRITER = "plan_based_researcher.graph.nodes.finalize.get_stream_writer"


def _spy_stream_writer(payloads: list[dict]):
    def get_stream_writer():
        def writer(payload: dict) -> None:
            payloads.append(payload)

        return writer

    return get_stream_writer


class FinalizeTest(unittest.IsolatedAsyncioTestCase):
    async def test_done_emits_only_done_payload(self) -> None:
        payloads: list[dict] = []
        finalize = make_finalize_node()
        with patch(_WRITER, _spy_stream_writer(payloads)):
            await finalize(
                {
                    "outcome": "done",
                    "writer_markdown": "# Answer with [1]",
                    "citations": [{"n": 1, "arxiv_id": "2401.00001"}],
                }
            )
        self.assertEqual(
            payloads, [{"event": "done", "data": {"outcome": "done"}}]
        )
        self.assertFalse(any(p.get("event") == "answer_complete" for p in payloads))

    def test_source_has_no_answer_complete(self) -> None:
        source = inspect.getsource(finalize_mod)
        self.assertNotIn("answer_complete", source)

    async def test_refused_emits_done_with_gate_reason(self) -> None:
        payloads: list[dict] = []
        finalize = make_finalize_node()
        with patch(_WRITER, _spy_stream_writer(payloads)):
            await finalize(
                {
                    "outcome": "refused",
                    "gate": {"reason": "out of scope"},
                }
            )
        self.assertEqual(len(payloads), 1)
        self.assertEqual(payloads[0]["event"], "done")
        self.assertEqual(payloads[0]["data"]["outcome"], "refused")
        self.assertEqual(payloads[0]["data"]["reason"], "out of scope")

    async def test_insufficient_and_error_keep_halt_event_names(self) -> None:
        payloads: list[dict] = []
        finalize = make_finalize_node()
        with patch(_WRITER, _spy_stream_writer(payloads)):
            await finalize(
                {
                    "outcome": "insufficient",
                    "last_eval": {"feedback": "not enough papers"},
                }
            )
        self.assertEqual(len(payloads), 1)
        self.assertEqual(payloads[0]["event"], "insufficient")
        self.assertEqual(payloads[0]["data"]["reason"], "not enough papers")

        payloads.clear()
        with patch(_WRITER, _spy_stream_writer(payloads)):
            await finalize(
                {
                    "outcome": "error",
                    "error_message": "research failed boom",
                }
            )
        self.assertEqual(len(payloads), 1)
        self.assertEqual(payloads[0]["event"], "error")
        self.assertEqual(payloads[0]["data"]["message"], "research failed boom")


if __name__ == "__main__":
    unittest.main()
