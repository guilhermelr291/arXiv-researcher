"""WSTR-01, WSTR-02: WriterRunner streams visible markdown via ChatOpenAI.astream."""

from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from plan_based_researcher.agents.writer import (
    WriterRunner,
    _emit_custom,
    _visible_text,
)

_CHAT = "plan_based_researcher.agents.writer.ChatOpenAI"
_GET_WRITER = "plan_based_researcher.agents.writer.get_stream_writer"


def _chunk(*, n: int = 1) -> dict:
    return {
        "chunk_id": f"c{n}",
        "n": n,
        "arxiv_id": "2609.01617",
        "version": "1",
        "title": "LoRA paper",
        "year": 2026,
        "url": "https://arxiv.org/abs/2609.01617",
        "excerpt": "low-rank adaptation",
    }


def _llm(*contents: object, error: BaseException | None = None) -> MagicMock:
    llm = MagicMock()

    async def astream(_messages: object):
        for content in contents:
            yield SimpleNamespace(content=content)
        if error is not None:
            raise error

    llm.astream = astream
    return llm


def _spy_stream_writer(payloads: list[dict]):
    def get_stream_writer():
        def writer(payload: dict) -> None:
            payloads.append(payload)

        return writer

    return get_stream_writer


class _StreamBoom(RuntimeError):
    pass


class VisibleTextTest(unittest.TestCase):
    def test_string_content_kept(self) -> None:
        chunk = SimpleNamespace(content="Hello [1]")
        self.assertEqual(_visible_text(chunk), "Hello [1]")

    def test_list_blocks_keep_text_drop_reasoning(self) -> None:
        chunk = SimpleNamespace(
            content=[
                {"type": "reasoning", "summary": "hidden chain of thought"},
                {"type": "text", "text": "kept"},
            ]
        )
        self.assertEqual(_visible_text(chunk), "kept")


class EmitCustomTest(unittest.TestCase):
    def test_emit_custom_outside_node_does_not_raise(self) -> None:
        _emit_custom("answer_delta", {"text": "x"})


class WriterRunnerConstructTest(unittest.TestCase):
    def test_api_key_passed_into_chat_openai(self) -> None:
        fake = MagicMock()
        with patch(_CHAT, return_value=fake) as ctor:
            WriterRunner(api_key="sk-test")
        ctor.assert_called_once()
        kwargs = ctor.call_args.kwargs
        self.assertEqual(kwargs["api_key"], "sk-test")
        self.assertEqual(fake.with_structured_output.call_count, 0)


class WriterRunnerStreamTest(unittest.IsolatedAsyncioTestCase):
    async def test_tiny_graph_two_deltas_then_citations(self) -> None:
        payloads: list[dict] = []
        returned: list[dict] = []
        with (
            patch(_CHAT, return_value=_llm("Hello ", "world")),
            patch(_GET_WRITER, _spy_stream_writer(payloads)),
        ):
            runner = WriterRunner(api_key="sk-test")
            result = await runner.run(
                {"query": "what is LoRA?", "evidence_chunks": [_chunk()]}
            )
            returned.append(result)
        self.assertEqual(len(returned), 1)
        result = returned[0]
        kinds = [p["event"] for p in payloads if p["event"] != "answer_start"]
        self.assertEqual(kinds, ["answer_delta", "answer_delta", "citations"])
        delta_texts = [p["data"]["text"] for p in payloads if p["event"] == "answer_delta"]
        self.assertEqual("".join(delta_texts), result["writer_markdown"])
        self.assertEqual(result["writer_markdown"], "Hello world")
        self.assertEqual(result["last_agent"], "writer")
        cit = next(p["data"] for p in payloads if p["event"] == "citations")
        self.assertIn("citations", cit)
        self.assertNotIn("markdown", cit)

    async def test_empty_completed_markdown_still_emits_citations(self) -> None:
        payloads: list[dict] = []
        with (
            patch(_CHAT, return_value=_llm("")),
            patch(_GET_WRITER, _spy_stream_writer(payloads)),
        ):
            runner = WriterRunner(api_key="sk-test")
            result = await runner.run({"query": "q", "evidence_chunks": [_chunk()]})
        self.assertEqual(result["writer_markdown"], "")
        events = [p["event"] for p in payloads]
        self.assertNotIn("answer_delta", events)
        self.assertIn("answer_start", events)
        self.assertIn("citations", events)
        cit = next(p for p in payloads if p["event"] == "citations")
        self.assertEqual(cit["data"]["citations"], [])
        self.assertNotIn("markdown", cit["data"])

    async def test_astream_raise_skips_citations_and_propagates(self) -> None:
        payloads: list[dict] = []
        with (
            patch(_CHAT, return_value=_llm("partial", error=_StreamBoom("llm down"))),
            patch(_GET_WRITER, _spy_stream_writer(payloads)),
        ):
            runner = WriterRunner(api_key="sk-test")
            with self.assertRaises(_StreamBoom):
                await runner.run({"query": "q", "evidence_chunks": [_chunk()]})
        events = [p["event"] for p in payloads]
        self.assertEqual(events, ["answer_start", "answer_delta"])
        self.assertEqual(payloads[1]["data"]["text"], "partial")
        self.assertNotIn("citations", events)

    async def test_unknown_citation_n_omitted(self) -> None:
        payloads: list[dict] = []
        evidence = [_chunk(n=1)]
        with (
            patch(_CHAT, return_value=_llm("Valid [1] and unknown [99].")),
            patch(_GET_WRITER, _spy_stream_writer(payloads)),
        ):
            runner = WriterRunner(api_key="sk-test")
            result = await runner.run(
                {"query": "q", "evidence_chunks": evidence}
            )
        self.assertIn("[99]", result["writer_markdown"])
        self.assertIn("[1]", result["writer_markdown"])
        ns = [c["n"] for c in result["citations"]]
        self.assertEqual(ns, [1])
        self.assertNotIn(99, ns)
        cit = next(p for p in payloads if p["event"] == "citations")
        self.assertEqual([c["n"] for c in cit["data"]["citations"]], [1])
        self.assertEqual(result["last_agent"], "writer")

    async def test_answer_start_before_first_delta(self) -> None:
        payloads: list[dict] = []
        with (
            patch(_CHAT, return_value=_llm("Hello")),
            patch(_GET_WRITER, _spy_stream_writer(payloads)),
        ):
            result = await WriterRunner(api_key="sk-test").run(
                {"query": "q", "evidence_chunks": [_chunk()]}
            )
        events = [p["event"] for p in payloads]
        self.assertGreaterEqual(events.index("answer_start"), 0)
        self.assertGreater(events.index("answer_delta"), events.index("answer_start"))
        start = next(p for p in payloads if p["event"] == "answer_start")
        message_id = start["data"]["message_id"]
        self.assertIsInstance(message_id, str)
        self.assertEqual(len(message_id), 36)
        self.assertEqual(result["writer_message_id"], message_id)

    async def test_citations_per_turn_fields(self) -> None:
        fields = (
            "n",
            "chunk_id",
            "arxiv_id",
            "title",
            "year",
            "url",
            "excerpt",
        )
        payloads: list[dict] = []
        with (
            patch(_CHAT, return_value=_llm("See [1].")),
            patch(_GET_WRITER, _spy_stream_writer(payloads)),
        ):
            result = await WriterRunner(api_key="sk-test").run(
                {"query": "q", "evidence_chunks": [_chunk(n=1)]}
            )
        citations = result["citations"]
        self.assertTrue(citations)
        self.assertEqual(citations[0]["n"], 1)
        for field in fields:
            with self.subTest(field=field):
                self.assertIn(field, citations[0])


if __name__ == "__main__":
    unittest.main()
