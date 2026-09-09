"""WSTR-07: map LangSmith-like execute runs to Writer triples."""

from __future__ import annotations

import unittest
from types import SimpleNamespace

from plan_based_researcher.eval.ragas_map import map_execute_run


def _chunk(excerpt: str, *, n: int = 1) -> dict:
    return {
        "chunk_id": f"c{n}",
        "n": n,
        "arxiv_id": "2609.01617",
        "version": "1",
        "title": "t",
        "year": 2026,
        "url": "https://arxiv.org/abs/2609.01617",
        "excerpt": excerpt,
    }


def _run(**kwargs: object) -> SimpleNamespace:
    defaults: dict[str, object] = {
        "id": "run-1",
        "trace_id": "trace-1",
        "name": "execute",
        "inputs": {},
        "outputs": {},
    }
    defaults.update(kwargs)
    return SimpleNamespace(**defaults)


class RagasMapTest(unittest.TestCase):
    def test_complete_triple_maps_all_four_fields(self) -> None:
        run = _run(
            id="run-abc",
            inputs={
                "query": "What is LoRA?",
                "evidence_chunks": [_chunk("LoRA is low-rank adaptation.", n=1)],
            },
            outputs={"writer_markdown": "LoRA is low-rank adaptation [1]."},
        )
        triple = map_execute_run(run)
        self.assertIsNotNone(triple)
        assert triple is not None
        self.assertEqual(triple["user_input"], "What is LoRA?")
        self.assertEqual(
            triple["retrieved_contexts"],
            ["LoRA is low-rank adaptation."],
        )
        self.assertEqual(triple["response"], "LoRA is low-rank adaptation [1].")
        self.assertEqual(triple["run_id"], "run-abc")

    def test_missing_query_returns_none(self) -> None:
        run = _run(
            inputs={"evidence_chunks": [_chunk("excerpt")]},
            outputs={"writer_markdown": "markdown"},
        )
        self.assertIsNone(map_execute_run(run))

    def test_missing_excerpts_returns_none(self) -> None:
        run = _run(
            inputs={"query": "What is LoRA?"},
            outputs={"writer_markdown": "markdown"},
        )
        self.assertIsNone(map_execute_run(run))

    def test_missing_markdown_returns_none(self) -> None:
        run = _run(
            inputs={
                "query": "What is LoRA?",
                "evidence_chunks": [_chunk("excerpt")],
            },
            outputs={},
        )
        self.assertIsNone(map_execute_run(run))

    def test_nested_execute_payload_unwraps_one_level(self) -> None:
        run = _run(
            id="nested-1",
            inputs={
                "execute": {
                    "query": "What is QLoRA?",
                    "evidence_chunks": [_chunk("QLoRA quantizes adapters.", n=1)],
                }
            },
            outputs={"execute": {"writer_markdown": "QLoRA quantizes adapters [1]."}},
        )
        triple = map_execute_run(run)
        self.assertIsNotNone(triple)
        assert triple is not None
        self.assertEqual(triple["user_input"], "What is QLoRA?")
        self.assertEqual(
            triple["retrieved_contexts"],
            ["QLoRA quantizes adapters."],
        )
        self.assertEqual(triple["response"], "QLoRA quantizes adapters [1].")
        self.assertEqual(triple["run_id"], "nested-1")

    def test_rerank_chunks_not_used_as_retrieved_contexts(self) -> None:
        writer_excerpt = "post-cut writer excerpt"
        run = _run(
            inputs={
                "query": "What is LoRA?",
                "evidence_chunks": [_chunk(writer_excerpt)],
                "chunks": ["first-stage hybrid hit"],
                "chunks_scored": [
                    {"content": "pre-cut scored chunk", "score": 0.99},
                ],
            },
            outputs={"writer_markdown": "LoRA [1]."},
        )
        triple = map_execute_run(run)
        self.assertIsNotNone(triple)
        assert triple is not None
        self.assertEqual(triple["retrieved_contexts"], [writer_excerpt])
        self.assertNotIn("first-stage hybrid hit", triple["retrieved_contexts"])
        self.assertNotIn("pre-cut scored chunk", triple["retrieved_contexts"])

        rerank_only = _run(
            inputs={
                "query": "What is LoRA?",
                "chunks": ["first-stage hybrid hit"],
                "chunks_scored": [
                    {"content": "pre-cut scored chunk", "score": 0.99},
                ],
            },
            outputs={"writer_markdown": "LoRA [1]."},
        )
        self.assertIsNone(map_execute_run(rerank_only))

    def test_retrieve_fallback_only_when_inputs_lack_evidence_chunks(self) -> None:
        fallback = {"trace-1": ["retrieve-output excerpt"]}
        with_chunks = _run(
            trace_id="trace-1",
            inputs={
                "query": "What is LoRA?",
                "evidence_chunks": [_chunk("execute-input excerpt")],
            },
            outputs={"writer_markdown": "LoRA [1]."},
        )
        triple = map_execute_run(
            with_chunks,
            retrieve_chunks_by_trace=fallback,
        )
        self.assertIsNotNone(triple)
        assert triple is not None
        self.assertEqual(triple["retrieved_contexts"], ["execute-input excerpt"])

        without_chunks = _run(
            trace_id="trace-1",
            inputs={"query": "What is LoRA?"},
            outputs={"writer_markdown": "LoRA [1]."},
        )
        fallback_triple = map_execute_run(
            without_chunks,
            retrieve_chunks_by_trace=fallback,
        )
        self.assertIsNotNone(fallback_triple)
        assert fallback_triple is not None
        self.assertEqual(
            fallback_triple["retrieved_contexts"],
            ["retrieve-output excerpt"],
        )


if __name__ == "__main__":
    unittest.main()
