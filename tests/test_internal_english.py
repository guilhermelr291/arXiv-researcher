"""LANG-01–04: structured-output fields and prompt locks for English internals."""

from __future__ import annotations

import inspect
import unittest

from plan_based_researcher.agents.gate import _SYSTEM_PROMPT as GATE_SYSTEM
from plan_based_researcher.agents import planner as planner_mod
from plan_based_researcher.agents.retrieve import _FORMULATE_SYSTEM as RETRIEVE_FORMULATE
from plan_based_researcher.agents.registry import REGISTRY
from plan_based_researcher.agents.writer import _system_prompt as writer_system
from plan_based_researcher.api.schemas import GateDecision, PlanStep
from plan_based_researcher.eval.strategies import (
    _retrieve_checklist,
    _search_checklist,
)
from plan_based_researcher.eval.types import EvalResult, SearchWaveJudgement


class InternalEnglishLocksTest(unittest.TestCase):
    def test_plan_step_fields_require_english(self) -> None:
        self.assertIn("English", PlanStep.model_fields["task"].description or "")
        self.assertIn("English", PlanStep.model_fields["reasoning"].description or "")

    def test_eval_fields_require_english(self) -> None:
        self.assertIn("English", EvalResult.model_fields["feedback"].description or "")
        self.assertIn(
            "English", SearchWaveJudgement.model_fields["reasoning"].description or ""
        )

    def test_gate_reason_matches_query_language(self) -> None:
        self.assertIn(
            "query language", GateDecision.model_fields["reason"].description or ""
        )
        self.assertIn("MUST match the query language", GATE_SYSTEM)

    def test_planner_and_writer_prompts(self) -> None:
        source = inspect.getsource(planner_mod)
        self.assertIn("Write every task and reasoning in English", source)
        self.assertIn("Do not copy the student query language", source)
        self.assertIn("Never emit a Portuguese task", source)
        self.assertIn("in English", REGISTRY["planner"].abilities)
        system = writer_system()
        self.assertIn("student query language", system)
        self.assertIn("do not switch the answer to English", system)

    def test_eval_checklists_english_feedback(self) -> None:
        self.assertIn("in English", _search_checklist())
        self.assertIn("in English", _retrieve_checklist())
        self.assertIn("student query first", _retrieve_checklist())
        self.assertIn("Do not retry the retrieve query", _retrieve_checklist())
        self.assertIn("plan_inadequate=true", _search_checklist())

    def test_retrieve_checklist_no_plan_inadequate_for_paper_facet(self) -> None:
        self.assertNotIn("plan_inadequate", _retrieve_checklist())

    def test_retrieve_checklist_yes_feedback_is_subquery(self) -> None:
        text = _retrieve_checklist()
        self.assertIn("English subquery", text)
        self.assertIn("Do not recite [n]", text)
        self.assertIn("keep-set sizes", text)
        self.assertIn("numbers copied from current chunks", text)

    def test_retrieve_checklist_hole_feedback_is_facet(self) -> None:
        self.assertIn("English facet of the hole", _retrieve_checklist())

    def test_retrieve_formulate_hops_are_english_chunk_terms(self) -> None:
        self.assertIn("English chunk terms", RETRIEVE_FORMULATE)
        self.assertIn("Do not copy the full retrieve task prose as a hop", RETRIEVE_FORMULATE)

    def test_retrieve_formulate_when_to_emit_hops(self) -> None:
        self.assertIn("length at least 2", RETRIEVE_FORMULATE)
        self.assertIn("distinct coverages", RETRIEVE_FORMULATE)
        self.assertIn("one chunk cannot cover", RETRIEVE_FORMULATE)
        self.assertIn("empty hops", RETRIEVE_FORMULATE)
        self.assertIn("one chunk can cover the task", RETRIEVE_FORMULATE)


if __name__ == "__main__":
    unittest.main()
