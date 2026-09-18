"""AGUI-01 AC 9–10: Writer evidence from prior citations or insufficient."""

from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from langchain_core.messages import AIMessage

from plan_based_researcher.agents.writer import WriterRunner

_CHAT = "plan_based_researcher.agents.writer.ChatOpenAI"


def _citation(n: int, chunk_id: str, excerpt: str) -> dict:
    return {
        "n": n,
        "chunk_id": chunk_id,
        "arxiv_id": f"2401.0000{n}",
        "title": f"Paper {chunk_id}",
        "year": 2024,
        "url": f"https://arxiv.org/abs/2401.0000{n}",
        "excerpt": excerpt,
    }


class WriterThreadEvidenceTest(unittest.IsolatedAsyncioTestCase):
    async def test_empty_chunks_renumber_prior_citations(self) -> None:
        first = AIMessage(
            content="first [1] [2]",
            id="a1",
            response_metadata={
                "outcome": "done",
                "citations": [
                    _citation(1, "dup", "first copy"),
                    _citation(2, "c2", "second excerpt"),
                ],
            },
        )
        second = AIMessage(
            content="second [1]",
            id="a2",
            response_metadata={
                "outcome": "done",
                "citations": [_citation(1, "dup", "later copy of dup")],
            },
        )
        seen: list[object] = []
        llm = MagicMock()

        async def astream(payload):
            seen.append(payload)
            yield SimpleNamespace(content="Uses [1] and [2].")

        llm.astream = astream
        with patch(_CHAT, return_value=llm):
            result = await WriterRunner(api_key="sk-test").run(
                {
                    "query": "follow up",
                    "messages": [
                        {"role": "user", "content": "first"},
                        first,
                        {"role": "user", "content": "second"},
                        second,
                        {"role": "user", "content": "follow up"},
                    ],
                    "evidence_chunks": [],
                    "plan": [{"agent": "writer", "task": "Write"}],
                    "step_index": 0,
                    "gate": {"language": "en"},
                }
            )
        self.assertEqual(len(seen), 1)
        blob = str(seen[0])
        self.assertIn("[1]", blob)
        self.assertIn("[2]", blob)
        self.assertIn("first copy", blob)
        self.assertIn("second excerpt", blob)
        self.assertNotIn("later copy of dup", blob)
        ns = [c["n"] for c in result["citations"]]
        self.assertEqual(ns, [1, 2] if "[1]" in result["writer_markdown"] else ns)
        by_n = {c["n"]: c["chunk_id"] for c in result["citations"]}
        if 1 in by_n:
            self.assertEqual(by_n[1], "dup")
        ids = [c["chunk_id"] for c in result["citations"]]
        self.assertEqual(len(ids), len(set(ids)))

    async def test_empty_chunks_no_citations_insufficient(self) -> None:
        llm = MagicMock()
        llm.astream = MagicMock(side_effect=AssertionError("Writer model must not run"))
        with patch(_CHAT, return_value=llm):
            result = await WriterRunner(api_key="sk-test").run(
                {
                    "query": "follow up",
                    "messages": [
                        {"role": "user", "content": "hello"},
                        AIMessage(
                            content="refused",
                            id="a1",
                            response_metadata={"outcome": "refused", "citations": []},
                        ),
                    ],
                    "evidence_chunks": [],
                    "plan": [{"agent": "writer", "task": "Write"}],
                    "step_index": 0,
                }
            )
        self.assertEqual(result["outcome"], "insufficient")
        llm.astream.assert_not_called()


if __name__ == "__main__":
    unittest.main()
