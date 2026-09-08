"""STRM-01, STRM-03: SseFrame encoder and unbuffered SSE headers."""

from __future__ import annotations

import json
import unittest

from plan_based_researcher.api.sse import SSE_HEADERS, SseFrame, encode_sse


class SseFrameTest(unittest.TestCase):
    def test_encode_plan_round_trips_json_keys(self) -> None:
        text = SseFrame("plan", {"steps": []}).encode().decode("utf-8")
        self.assertTrue(text.startswith("event: plan\n"))
        data_line = next(line for line in text.splitlines() if line.startswith("data: "))
        payload = json.loads(data_line.removeprefix("data: "))
        self.assertIn("steps", payload)

    def test_encode_answer_complete_round_trips_json_keys(self) -> None:
        text = SseFrame("answer_complete", {"markdown": "", "citations": []}).encode().decode(
            "utf-8"
        )
        self.assertTrue(text.startswith("event: answer_complete\n"))
        data_line = next(line for line in text.splitlines() if line.startswith("data: "))
        payload = json.loads(data_line.removeprefix("data: "))
        self.assertIn("markdown", payload)
        self.assertIn("citations", payload)

    def test_unknown_event_raises_value_error(self) -> None:
        with self.assertRaises(ValueError):
            SseFrame("not_an_sse_event", {}).encode()

    def test_sse_headers_exactly_three_keys(self) -> None:
        self.assertEqual(
            SSE_HEADERS,
            {
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )

    def test_encode_sse_equals_sse_frame_encode(self) -> None:
        data = {"steps": []}
        self.assertEqual(encode_sse("plan", data), SseFrame("plan", data).encode())
