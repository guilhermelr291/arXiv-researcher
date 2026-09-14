"""ARX-16 / Quick 015: pinned mock search does not call export.arxiv.org."""

from __future__ import annotations

import unittest
from unittest.mock import patch

from plan_based_researcher.adapters.arxiv import ArxivPaperAdapter


class ArxivMockSearchTest(unittest.IsolatedAsyncioTestCase):
    async def test_mock_search_returns_pinned_hit_without_http(self) -> None:
        adapter = ArxivPaperAdapter(mock_arxiv_id="2609.11929v1")
        with patch(
            "plan_based_researcher.adapters.arxiv._search_sync",
            side_effect=AssertionError("export.arxiv.org must not be called"),
        ) as live:
            hits = await adapter.search("ignored query", max_results=8)
        live.assert_not_called()
        self.assertEqual(len(hits), 1)
        self.assertEqual(hits[0].arxiv_id, "2609.11929")
        self.assertEqual(hits[0].version, "1")

    async def test_mock_search_logs_skip_line(self) -> None:
        adapter = ArxivPaperAdapter(mock_arxiv_id="2609.11929v1")
        with self.assertLogs(
            "plan_based_researcher.adapters.arxiv", level="WARNING"
        ) as captured:
            await adapter.search("ignored query", max_results=8)
        self.assertTrue(
            any(
                "MOCK_ARXIV_ID=2609.11929v1; skipping live arXiv search" in line
                for line in captured.output
            )
        )


if __name__ == "__main__":
    unittest.main()
