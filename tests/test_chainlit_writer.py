"""WSTR-05: Chainlit typewriter on answer_delta and side panel on citations."""

from __future__ import annotations

import unittest
from pathlib import Path

_APP = (
    Path(__file__).resolve().parents[1]
    / "src"
    / "plan_based_researcher"
    / "ui"
    / "app.py"
)


def _app_source() -> str:
    return _APP.read_text(encoding="utf-8")


def _event_branch(source: str, name: str) -> str:
    marker = f'if event == "{name}"'
    start = source.index(marker)
    rest = source[start + len(marker) :]
    next_if = rest.find("\n    if event ==")
    next_def = rest.find("\ndef ")
    cuts = [i for i in (next_if, next_def) if i != -1]
    end = min(cuts) if cuts else len(rest)
    return marker + rest[:end]


class ChainlitWriterTest(unittest.TestCase):
    def test_source_contains_answer_delta_citations_stream_token_and_side_panel(
        self,
    ) -> None:
        source = _app_source()
        self.assertIn("answer_delta", source)
        self.assertIn("citations", source)
        self.assertIn("stream_token", source)
        self.assertIn("side_panel_texts", source)
        self.assertIn(
            "await _handle_event(event, data, open_steps, answer)",
            source,
        )
        self.assertIn('if event == "answer_delta"', source)
        self.assertIn('if event == "citations"', source)
        delta = _event_branch(source, "answer_delta")
        self.assertIn("stream_token(text)", delta)
        self.assertIn("if not text", delta)
        citations = _event_branch(source, "citations")
        self.assertIn("side_panel_texts", citations)
        self.assertIn("display=\"side\"", citations)

    def test_source_does_not_contain_answer_complete(self) -> None:
        source = _app_source()
        self.assertNotIn("answer_complete", source)

    def test_error_finalizes_partial_answer(self) -> None:
        source = _app_source()
        self.assertIn('event == "done"', source)
        self.assertIn('event == "gate"', source)
        self.assertIn('event == "insufficient"', source)
        self.assertIn('event == "error"', source)
        self.assertNotIn("Strategy", source)
        error = _event_branch(source, "error")
        self.assertIn("finalized", error)
        self.assertIn("msg.send()", error)
        self.assertIn("answer", error)
        self.assertIn("cl.Message", error)


if __name__ == "__main__":
    unittest.main()
