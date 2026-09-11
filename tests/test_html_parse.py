"""Unit tests for arXiv HTML parse drops (bibliography, acknowledgements, contributors)."""

from __future__ import annotations

import unittest

from plan_based_researcher.ingest.html_parse import parse_arxiv_html

_ARTICLE = """\
<html><body>
<article class="ltx_document">
{body}
</article>
</body></html>
"""


def _parse(body: str):
    return parse_arxiv_html(_ARTICLE.format(body=body).encode("utf-8"))


class TestParseArxivHtmlDrops(unittest.TestCase):
    def test_numbered_contributors_section_is_dropped(self) -> None:
        parsed = _parse(
            """
            <section class="ltx_section">
              <h2>6 Conclusion</h2>
              <p>We present the model.</p>
            </section>
            <section class="ltx_section">
              <h2><span class="ltx_tag">7 </span>Contributors</h2>
              <p>Alice and Bob listed by role.</p>
            </section>
            """
        )
        self.assertTrue(parsed.usable)
        self.assertIn("We present the model.", parsed.prose_markdown)
        self.assertNotIn("Alice and Bob", parsed.prose_markdown)
        self.assertNotRegex(parsed.prose_markdown, r"(?i)contributors")

    def test_scientific_contributions_section_is_kept(self) -> None:
        parsed = _parse(
            """
            <section class="ltx_section">
              <h2>3 Contributions</h2>
              <p>We propose a native unified architecture.</p>
            </section>
            """
        )
        self.assertTrue(parsed.usable)
        self.assertIn("We propose a native unified architecture.", parsed.prose_markdown)
        self.assertIn("Contributions", parsed.prose_markdown)

    def test_acknowledgements_section_is_still_dropped(self) -> None:
        parsed = _parse(
            """
            <section class="ltx_section">
              <h2>Conclusion</h2>
              <p>Keep this paragraph.</p>
            </section>
            <section class="ltx_section">
              <h2>Acknowledgements</h2>
              <p>We thank the anonymous reviewers.</p>
            </section>
            """
        )
        self.assertTrue(parsed.usable)
        self.assertIn("Keep this paragraph.", parsed.prose_markdown)
        self.assertNotIn("anonymous reviewers", parsed.prose_markdown)


if __name__ == "__main__":
    unittest.main()
