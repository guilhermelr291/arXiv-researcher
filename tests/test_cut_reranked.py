"""Unit tests for Voyage-scale cut, query/document helpers, and score_chunks mapping."""

from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import patch

from langchain_core.documents import Document

from plan_based_researcher.ingest.rerank import (
    build_rerank_query,
    cut_reranked,
    document_text,
    score_chunks,
    scores_from_rerank_results,
)
from plan_based_researcher.policy import Policy
from plan_based_researcher.ports.chunks import ChunkRecord

_VOYAGE_RERANK = "plan_based_researcher.ingest.rerank.VoyageAIRerank"


def _chunk(*, chunk_id="c1", content="hello", section=""):
    return ChunkRecord(
        chunk_id=chunk_id,
        arxiv_id="2609.01617",
        version="1",
        title="t",
        year=2026,
        url="https://arxiv.org/abs/2609.01617",
        kind="prose",
        unit_id=None,
        content=content,
        metadata={"section": section, "caption": "", "unit_ids": []},
    )


class TestCutReranked(unittest.TestCase):
    def test_margin_keeps_prefix_until_first_gap(self) -> None:
        a, b, c = _chunk(chunk_id="a"), _chunk(chunk_id="b"), _chunk(chunk_id="c")
        ranked = [(a, 0.90), (b, 0.80), (c, 0.69)]
        self.assertEqual(cut_reranked(ranked), [a, b])

    def test_top_n_caps_cluster_within_margin(self) -> None:
        ranked = [(_chunk(chunk_id=str(i)), 0.90 - i * 0.01) for i in range(13)]
        kept = cut_reranked(ranked, top_n=12, margin=0.20, floor=0.30)
        self.assertEqual(len(kept), 12)
        self.assertEqual(kept, [chunk for chunk, _ in ranked[:12]])

    def test_floor_drops_when_best_below(self) -> None:
        ranked = [(_chunk(chunk_id="weak"), 0.25), (_chunk(chunk_id="weaker"), 0.10)]
        self.assertEqual(cut_reranked(ranked, floor=0.30), [])

    def test_break_does_not_keep_post_gap_item(self) -> None:
        a, b, c = _chunk(chunk_id="a"), _chunk(chunk_id="b"), _chunk(chunk_id="c")
        ranked = [(a, 0.90), (b, 0.60), (c, 0.89)]
        self.assertEqual(cut_reranked(ranked, margin=0.20, floor=0.30), [a])

    def test_empty_ranked_returns_empty(self) -> None:
        self.assertEqual(cut_reranked([]), [])

    def test_margin_zero_keeps_only_ties_capped_by_top_n(self) -> None:
        a, b, c, d = (
            _chunk(chunk_id="a"),
            _chunk(chunk_id="b"),
            _chunk(chunk_id="c"),
            _chunk(chunk_id="d"),
        )
        ranked = [(a, 0.90), (b, 0.90), (c, 0.89), (d, 0.90)]
        self.assertEqual(
            cut_reranked(ranked, margin=0, top_n=12, floor=0.30),
            [a, b],
        )
        ties = [(_chunk(chunk_id=str(i)), 0.90) for i in range(5)]
        kept = cut_reranked(ties, margin=0, top_n=2, floor=0.30)
        self.assertEqual(kept, [chunk for chunk, _ in ties[:2]])

    def test_default_floor_drops_weak_best(self) -> None:
        ranked = [(_chunk(chunk_id="weak"), 0.25)]
        self.assertEqual(cut_reranked(ranked), [])


class TestBuildRerankQuery(unittest.TestCase):
    def test_empty_or_whitespace_feedback_returns_task_only(self) -> None:
        self.assertEqual(build_rerank_query("  explain RRF  ", ""), "explain RRF")
        self.assertEqual(build_rerank_query("explain RRF", "   "), "explain RRF")
        self.assertEqual(build_rerank_query("explain RRF", "\n\t"), "explain RRF")

    def test_nonempty_feedback_concatenates(self) -> None:
        self.assertEqual(
            build_rerank_query("explain RRF", "missing architecture"),
            "explain RRF\n\nmissing architecture",
        )
        self.assertEqual(
            build_rerank_query("  explain RRF  ", "  missing architecture  "),
            "explain RRF\n\nmissing architecture",
        )


class TestDocumentText(unittest.TestCase):
    def test_empty_or_missing_section_returns_content_only(self) -> None:
        empty_section = _chunk(chunk_id="e", content="prose only", section="")
        self.assertEqual(document_text(empty_section), "prose only")
        whitespace_section = _chunk(chunk_id="w", content="prose only", section="   ")
        self.assertEqual(document_text(whitespace_section), "prose only")
        missing_section = _chunk(chunk_id="m", content="prose only")
        missing_section.metadata.pop("section")
        self.assertEqual(document_text(missing_section), "prose only")


class TestScoresFromRerankResults(unittest.TestCase):
    def test_maps_shuffled_indexes_to_input_order(self) -> None:
        results = [
            SimpleNamespace(index=2, relevance_score=0.91),
            SimpleNamespace(index=0, relevance_score=0.55),
            SimpleNamespace(index=1, relevance_score=0.33),
        ]
        self.assertEqual(
            scores_from_rerank_results(3, results),
            [0.55, 0.33, 0.91],
        )

    def test_missing_index_raises(self) -> None:
        missing = [
            SimpleNamespace(index=0, relevance_score=0.9),
            SimpleNamespace(index=1, relevance_score=0.5),
        ]
        with self.assertRaises(ValueError):
            scores_from_rerank_results(3, missing)
        out_of_range = [SimpleNamespace(index=5, relevance_score=0.1)]
        with self.assertRaises(ValueError):
            scores_from_rerank_results(2, out_of_range)

    def test_duplicate_index_raises(self) -> None:
        results = [
            SimpleNamespace(index=0, relevance_score=0.9),
            SimpleNamespace(index=1, relevance_score=0.5),
            SimpleNamespace(index=0, relevance_score=0.1),
        ]
        with self.assertRaises(ValueError):
            scores_from_rerank_results(2, results)


class TestScoreChunks(unittest.TestCase):
    def test_empty_chunks_does_not_construct(self) -> None:
        with patch(_VOYAGE_RERANK) as rerank_cls:
            scores = score_chunks([], "query", api_key="k")
        self.assertEqual(scores, [])
        rerank_cls.assert_not_called()

    def test_compress_documents_maps_to_input_order(self) -> None:
        chunks = [
            _chunk(chunk_id="c0", content="zero"),
            _chunk(chunk_id="c1", content="one"),
            _chunk(chunk_id="c2", content="two"),
        ]
        compressed = [
            Document(
                page_content="two",
                metadata={"input_index": 2, "relevance_score": 0.91},
            ),
            Document(
                page_content="zero",
                metadata={"input_index": 0, "relevance_score": 0.55},
            ),
            Document(
                page_content="one",
                metadata={"input_index": 1, "relevance_score": 0.33},
            ),
        ]
        with patch(_VOYAGE_RERANK) as rerank_cls:
            compressor = rerank_cls.return_value
            compressor.compress_documents.return_value = compressed
            scores = score_chunks(chunks, "rerank query", api_key="secret-key")
            compressor.acompress_documents.assert_not_called()
        self.assertEqual(scores, [0.55, 0.33, 0.91])
        docs, query = compressor.compress_documents.call_args.args
        self.assertEqual(query, "rerank query")
        self.assertEqual([doc.metadata["input_index"] for doc in docs], [0, 1, 2])
        self.assertEqual(
            [doc.page_content for doc in docs],
            [document_text(c) for c in chunks],
        )
        kwargs = rerank_cls.call_args.kwargs
        self.assertEqual(kwargs["model"], "rerank-3")
        self.assertEqual(kwargs["api_key"], "secret-key")
        self.assertIs(kwargs["truncation"], True)
        self.assertEqual(kwargs["top_k"], len(chunks))
        self.assertNotEqual(kwargs["top_k"], Policy.retrieve_rerank_top_n)
        self.assertEqual(Policy.retrieve_rerank_top_n, 15)

    def test_missing_input_index_raises(self) -> None:
        chunks = [_chunk(chunk_id="c0"), _chunk(chunk_id="c1")]
        compressed = [
            Document(page_content="hello", metadata={"relevance_score": 0.9}),
            Document(
                page_content="hello",
                metadata={"input_index": 1, "relevance_score": 0.1},
            ),
        ]
        with patch(_VOYAGE_RERANK) as rerank_cls:
            rerank_cls.return_value.compress_documents.return_value = compressed
            with self.assertRaises((KeyError, ValueError)):
                score_chunks(chunks, "q", api_key="k")

    def test_missing_relevance_score_raises(self) -> None:
        chunks = [_chunk(chunk_id="c0"), _chunk(chunk_id="c1")]
        compressed = [
            Document(page_content="hello", metadata={"input_index": 0}),
            Document(
                page_content="hello",
                metadata={"input_index": 1, "relevance_score": 0.1},
            ),
        ]
        with patch(_VOYAGE_RERANK) as rerank_cls:
            rerank_cls.return_value.compress_documents.return_value = compressed
            with self.assertRaises((KeyError, ValueError)):
                score_chunks(chunks, "q", api_key="k")


if __name__ == "__main__":
    unittest.main()
