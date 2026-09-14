"""Writer sees hole_tasks, not retrieve-step eval feedback (ARX9-05)."""

from __future__ import annotations

import unittest

from plan_based_researcher.agents.writer import _system_prompt, _user_prompt
from plan_based_researcher.policy import Policy

_RETRIEVE_FEEDBACK = "hunt total size 59M 38M 120K from current chunks"
_HOLE = "absolute corpus N for generation editing interleaved"


class T3WriterHolesTest(unittest.TestCase):
    def test_writer_prompt_lists_gap_hole_tasks(self) -> None:
        state = {
            "query": "What is the corpus size?",
            "step_index": 2,
            "plan": [
                {"agent": "search", "task": "find papers on the topic"},
                {"agent": "retrieve", "task": "retrieve corpus sizes"},
                {"agent": "writer", "task": "write the grounded answer"},
            ],
            "passed_steps": [0, 1],
            "papers": [],
            "evidence_chunks": [],
            "search_artifacts": {},
            "hole_tasks": [{"task": _HOLE, "reason": "gap"}],
            "eval_by_step": {},
            "gate": {"language": "en"},
        }
        user = _user_prompt(state, "(no evidence chunks provided)")
        self.assertIn(f"{_HOLE} (gap)", user)
        self.assertIn(Policy.HOLE_RULE, _system_prompt())

    def test_writer_step_eval_feedback_ignores_retrieve(self) -> None:
        state = {
            "query": "What is the corpus size?",
            "step_index": 2,
            "plan": [
                {"agent": "search", "task": "find papers on the topic"},
                {"agent": "retrieve", "task": "retrieve corpus sizes"},
                {"agent": "writer", "task": "write the grounded answer"},
            ],
            "passed_steps": [0, 1],
            "papers": [],
            "evidence_chunks": [],
            "search_artifacts": {},
            "hole_tasks": [{"task": _HOLE, "reason": "gap"}],
            "eval_by_step": {
                "1": {
                    "feedback": _RETRIEVE_FEEDBACK,
                    "step_index": 1,
                    "status": "pass",
                }
            },
            "last_eval": {
                "feedback": _RETRIEVE_FEEDBACK,
                "step_index": 1,
                "status": "pass",
            },
            "gate": {"language": "en"},
        }
        user = _user_prompt(state, "(no evidence chunks provided)")
        self.assertNotIn(_RETRIEVE_FEEDBACK, user)
        self.assertNotIn("59M", user)


if __name__ == "__main__":
    unittest.main()
