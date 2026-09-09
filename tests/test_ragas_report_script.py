"""WSTR-06: ast.parse-only checks for scripts/ragas_writer_report.py."""

from __future__ import annotations

import ast
import unittest
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
_SCRIPT = _ROOT / "scripts" / "ragas_writer_report.py"


def _source() -> str:
    return _SCRIPT.read_text(encoding="utf-8")


class RagasReportScriptTest(unittest.TestCase):
    def test_ast_parse_succeeds(self) -> None:
        ast.parse(_source())

    def test_settings_absent_dotenv_and_windows_policy_present(self) -> None:
        source = _source()
        tree = ast.parse(source)
        names = {node.id for node in ast.walk(tree) if isinstance(node, ast.Name)}
        self.assertNotIn("Settings", names)
        self.assertNotIn("Settings", source)
        self.assertIn("load_dotenv", source)
        self.assertIn("WindowsSelectorEventLoopPolicy", source)
        self.assertNotIn("rid != args.run_id", source)
        self.assertIn("LangGraph root", source)

    def test_faithfulness_and_answer_relevancy_present(self) -> None:
        source = _source()
        self.assertIn("Faithfulness", source)
        self.assertIn("AnswerRelevancy", source)
        self.assertIn("text-embedding-3-small", source)
        self.assertIn("max_tokens", source)

    def test_openai_embeddings_only(self) -> None:
        source = _source()
        self.assertIn("text-embedding-3-small", source)
        self.assertNotIn("voyage", source.lower())
        self.assertNotIn("Voyage", source)

    def test_persists_reasoning_under_reports_ragas(self) -> None:
        source = _source()
        self.assertIn("reports/ragas", source.replace("\\", "/"))
        self.assertIn("--no-save", source)
        self.assertIn("index.jsonl", source)
        self.assertIn("json.dumps", source)
        self.assertIn("verdict", source)
        self.assertIn("generated_questions", source)
        self.assertIn("faithfulness reasoning", source)


if __name__ == "__main__":
    unittest.main()
