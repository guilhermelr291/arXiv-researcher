"""VOY-01, VOY-06: VoyageEmbeddingAdapter wraps VoyageAIEmbeddings (no live HTTP)."""

from __future__ import annotations

import asyncio
import inspect
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from plan_based_researcher.adapters.voyage_embeddings import (
    EMBEDDING_MODEL_ID,
    VoyageEmbeddingAdapter,
)


class VoyageEmbeddingAdapterTest(unittest.TestCase):
    def test_constructor_forwards_model_truncation_api_key_without_output_dimension(
        self,
    ) -> None:
        fake = MagicMock()
        with patch(
            "plan_based_researcher.adapters.voyage_embeddings.VoyageAIEmbeddings",
            return_value=fake,
        ) as ctor:
            adapter = VoyageEmbeddingAdapter(api_key="sk-test")
        ctor.assert_called_once()
        self.assertEqual(ctor.call_args.args, ())
        kwargs = ctor.call_args.kwargs
        self.assertEqual(EMBEDDING_MODEL_ID, "voyage-4-large")
        self.assertEqual(kwargs["model"], "voyage-4-large")
        self.assertNotEqual(kwargs["model"], "voyage-4")
        self.assertNotEqual(kwargs["model"], "voyage-4-lite")
        self.assertIs(kwargs["truncation"], True)
        self.assertEqual(kwargs["api_key"], "sk-test")
        self.assertNotIn("output_dimension", kwargs)
        self.assertIs(adapter._embeddings, fake)

    def test_embed_documents_delegates_to_aembed_documents_length_1024(self) -> None:
        fake = MagicMock()
        vectors = [[0.0] * 1024, [1.0] * 1024]
        fake.aembed_documents = AsyncMock(return_value=vectors)
        with patch(
            "plan_based_researcher.adapters.voyage_embeddings.VoyageAIEmbeddings",
            return_value=fake,
        ):
            adapter = VoyageEmbeddingAdapter(api_key="sk-test")
        texts = ["doc-a", "doc-b"]
        result = asyncio.run(adapter.embed_documents(texts))
        fake.aembed_documents.assert_awaited_once_with(texts)
        self.assertEqual(len(result), 2)
        self.assertEqual(len(result[0]), 1024)
        self.assertEqual(len(result[1]), 1024)
        self.assertEqual(result, vectors)

    def test_embed_query_delegates_to_aembed_query_length_1024(self) -> None:
        fake = MagicMock()
        vector = [0.1] * 1024
        fake.aembed_query = AsyncMock(return_value=vector)
        with patch(
            "plan_based_researcher.adapters.voyage_embeddings.VoyageAIEmbeddings",
            return_value=fake,
        ):
            adapter = VoyageEmbeddingAdapter(api_key="sk-test")
        result = asyncio.run(adapter.embed_query("query text"))
        fake.aembed_query.assert_awaited_once_with("query text")
        self.assertEqual(len(result), 1024)
        self.assertEqual(result, vector)

    def test_constructor_omits_api_key_and_output_dimension_and_does_not_import_voyageai(
        self,
    ) -> None:
        fake = MagicMock()
        with patch(
            "plan_based_researcher.adapters.voyage_embeddings.VoyageAIEmbeddings",
            return_value=fake,
        ) as ctor:
            VoyageEmbeddingAdapter()
        ctor.assert_called_once()
        self.assertEqual(ctor.call_args.args, ())
        kwargs = ctor.call_args.kwargs
        self.assertNotIn("api_key", kwargs)
        self.assertNotIn("output_dimension", kwargs)
        self.assertEqual(kwargs["model"], "voyage-4-large")
        self.assertIs(kwargs["truncation"], True)
        source = inspect.getsource(
            inspect.getmodule(VoyageEmbeddingAdapter)  # type: ignore[arg-type]
        )
        self.assertNotIn("import voyageai", source)
        self.assertNotIn("from voyageai", source)
