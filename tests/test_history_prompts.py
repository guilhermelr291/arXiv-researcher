"""AGUI-01 AC 6–8: gate/planner/writer prompts read a trimmed transcript."""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch

from langchain_core.messages import AIMessage

from plan_based_researcher.agents.gate import GateRunner
from plan_based_researcher.agents.planner import PlannerRunner
from plan_based_researcher.agents.writer import WriterRunner
from plan_based_researcher.api.schemas import ResearchPlan
from plan_based_researcher.policy import Policy

_GATE_LLM = "plan_based_researcher.agents.gate.ChatOpenAI"
_PLANNER_LLM = "plan_based_researcher.agents.planner.ChatOpenAI"
_WRITER_LLM = "plan_based_researcher.agents.writer.ChatOpenAI"


def _exchanges(n: int) -> list:
    messages: list = []
    for i in range(1, n + 1):
        messages.append({"role": "user", "content": f"user-{i}"})
        messages.append(AIMessage(content=f"ai-{i}", id=f"ai-{i}"))
    return messages


def _human_blob(payload: object) -> str:
    if isinstance(payload, str):
        return payload
    if isinstance(payload, tuple) and len(payload) >= 2:
        return str(payload[1])
    if isinstance(payload, dict):
        return str(payload.get("content") or "")
    if isinstance(payload, list):
        return "\n".join(_human_blob(item) for item in payload)
    return str(payload)


class HistoryPromptsTest(unittest.IsolatedAsyncioTestCase):
    async def test_gate_window_is_three_exchanges_and_planner_sees_all(self) -> None:
        self.assertEqual(Policy.history_window_exchanges, 3)
        messages = _exchanges(8)
        state = {"query": "user-8", "messages": messages, "papers": []}

        captured: list[str] = []
        structured = MagicMock()

        async def gate_invoke(payload):
            captured.append(_human_blob(payload))
            decision = MagicMock()
            decision.in_domain = True
            decision.model_dump.return_value = {
                "in_domain": True,
                "language": "en",
                "reason": "ok",
            }
            return decision

        structured.ainvoke = gate_invoke
        llm = MagicMock()
        llm.with_structured_output.return_value = structured
        with patch(_GATE_LLM, return_value=llm):
            await GateRunner(api_key="sk-test").run(state)
        blob = "\n".join(captured)
        for i in range(6, 9):
            self.assertIn(f"user-{i}", blob)
        for i in range(1, 6):
            self.assertNotIn(f"user-{i}", blob)

        captured.clear()

        async def plan_invoke(payload):
            captured.append(_human_blob(payload))
            return ResearchPlan(steps=[])

        structured.ainvoke = plan_invoke
        with patch(_PLANNER_LLM, return_value=llm):
            await PlannerRunner(api_key="sk-test").run(state)
        blob = "\n".join(captured)
        self.assertIn("user-1", blob)
        self.assertIn("user-8", blob)

    async def test_writer_window_is_two_plus_evidence(self) -> None:
        self.assertEqual(Policy.writer_history_exchanges, 2)
        chunks = [
            {
                "chunk_id": "c1",
                "n": 1,
                "arxiv_id": "2401.00001",
                "title": "LoRA",
                "year": 2024,
                "url": "https://arxiv.org/abs/2401.00001",
                "excerpt": "low-rank adaptation excerpt",
            }
        ]
        state = {
            "query": "user-4",
            "messages": _exchanges(4),
            "evidence_chunks": chunks,
            "plan": [{"agent": "writer", "task": "Write"}],
            "step_index": 0,
            "gate": {"language": "en"},
        }
        llm = MagicMock()
        seen: list[str] = []

        async def astream(payload):
            seen.append(_human_blob(payload))
            if False:
                yield None

        llm.astream = astream
        llm.bind_tools.return_value = llm
        with patch(_WRITER_LLM, return_value=llm):
            await WriterRunner(api_key="sk-test").run(state)
        blob = "\n".join(seen)
        self.assertIn("user-3", blob)
        self.assertIn("user-4", blob)
        self.assertNotIn("user-1", blob)
        self.assertNotIn("user-2", blob)
        self.assertIn("[1]", blob)
        self.assertIn("low-rank adaptation excerpt", blob)

    async def test_planner_lists_admitted_papers_and_omit_search(self) -> None:
        captured: list[str] = []
        structured = MagicMock()

        async def ainvoke(payload):
            captured.append(_human_blob(payload))
            return ResearchPlan(steps=[])

        structured.ainvoke = ainvoke
        llm = MagicMock()
        llm.with_structured_output.return_value = structured
        papers = [
            {"arxiv_id": "2401.00001", "title": "LoRA: Low-Rank Adaptation"},
            {"arxiv_id": "2305.12345", "title": "QLoRA"},
        ]
        with patch(_PLANNER_LLM, return_value=llm):
            await PlannerRunner(api_key="sk-test").run(
                {
                    "query": "compare them",
                    "messages": [{"role": "user", "content": "compare them"}],
                    "papers": papers,
                }
            )
        blob = "\n".join(captured)
        self.assertIn("2401.00001", blob)
        self.assertIn("LoRA: Low-Rank Adaptation", blob)
        self.assertIn("2305.12345", blob)
        self.assertIn("QLoRA", blob)
        self.assertIn("omit search", blob.lower())
        self.assertIn("already admitted", blob.lower())

    async def test_planner_summary_before_query_and_all_messages(self) -> None:
        captured: list[str] = []
        structured = MagicMock()

        async def ainvoke(payload):
            captured.append(_human_blob(payload))
            return ResearchPlan(steps=[])

        structured.ainvoke = ainvoke
        llm = MagicMock()
        llm.with_structured_output.return_value = structured
        state = {
            "query": "user-8",
            "messages": _exchanges(8),
            "papers": [],
            "conversation_summary": "GOAL-42",
        }
        with patch(_PLANNER_LLM, return_value=llm):
            await PlannerRunner(api_key="sk-test").run(state)
        blob = "\n".join(captured)
        tag = blob.index("<conversation_summary>")
        query = blob.index("Query:")
        self.assertLess(tag, query)
        self.assertIn("Produce an ordered executable plan", blob[:tag])
        self.assertIn("GOAL-42", blob[tag:query])
        self.assertIn("user-1", blob)

    async def test_planner_omits_summary_tag_when_empty(self) -> None:
        for summary in ("", None):
            with self.subTest(summary=summary):
                captured: list[str] = []
                structured = MagicMock()

                async def ainvoke(payload):
                    captured.append(_human_blob(payload))
                    return ResearchPlan(steps=[])

                structured.ainvoke = ainvoke
                llm = MagicMock()
                llm.with_structured_output.return_value = structured
                state = {
                    "query": "hello",
                    "messages": [{"role": "user", "content": "hello"}],
                    "papers": [],
                }
                if summary is not None:
                    state["conversation_summary"] = summary
                with patch(_PLANNER_LLM, return_value=llm):
                    await PlannerRunner(api_key="sk-test").run(state)
                blob = "\n".join(captured)
                self.assertNotIn("<conversation_summary>", blob)

    async def test_gate_last_six_messages_omit_summary(self) -> None:
        messages = [{"role": "user", "content": f"msg-{i}"} for i in range(8)]
        state = {
            "query": "msg-7",
            "messages": messages,
            "conversation_summary": "GOAL-42",
        }
        captured: list[str] = []
        structured = MagicMock()

        async def ainvoke(payload):
            captured.append(_human_blob(payload))
            decision = MagicMock()
            decision.in_domain = True
            decision.model_dump.return_value = {
                "in_domain": True,
                "language": "en",
                "reason": "ok",
            }
            return decision

        structured.ainvoke = ainvoke
        llm = MagicMock()
        llm.with_structured_output.return_value = structured
        with patch(_GATE_LLM, return_value=llm):
            await GateRunner(api_key="sk-test").run(state)
        blob = "\n".join(captured)
        for i in range(2, 8):
            self.assertIn(f"msg-{i}", blob)
        self.assertNotIn("msg-0", blob)
        self.assertNotIn("msg-1", blob)
        self.assertNotIn("<conversation_summary>", blob)
        self.assertNotIn("GOAL-42", blob)

    async def test_writer_two_exchanges_omit_summary(self) -> None:
        state = {
            "query": "user-4",
            "messages": _exchanges(4),
            "conversation_summary": "GOAL-42",
            "evidence_chunks": [
                {
                    "chunk_id": "c1",
                    "n": 1,
                    "arxiv_id": "2401.00001",
                    "title": "LoRA",
                    "year": 2024,
                    "url": "https://arxiv.org/abs/2401.00001",
                    "excerpt": "excerpt",
                }
            ],
            "plan": [{"agent": "writer", "task": "Write"}],
            "step_index": 0,
            "gate": {"language": "en"},
        }
        llm = MagicMock()
        seen: list[str] = []

        async def astream(payload):
            seen.append(_human_blob(payload))
            if False:
                yield None

        llm.astream = astream
        llm.bind_tools.return_value = llm
        with patch(_WRITER_LLM, return_value=llm):
            await WriterRunner(api_key="sk-test").run(state)
        blob = "\n".join(seen)
        self.assertIn("user-3", blob)
        self.assertIn("user-4", blob)
        self.assertNotIn("user-1", blob)
        self.assertNotIn("user-2", blob)
        self.assertNotIn("<conversation_summary>", blob)
        self.assertNotIn("GOAL-42", blob)

    async def test_replan_remaining_omits_summary(self) -> None:
        captured: list[str] = []
        structured = MagicMock()

        async def ainvoke(payload):
            captured.append(_human_blob(payload))
            return ResearchPlan(steps=[])

        structured.ainvoke = ainvoke
        llm = MagicMock()
        llm.with_structured_output.return_value = structured
        state = {
            "query": "follow up",
            "messages": [{"role": "user", "content": "follow up"}],
            "papers": [],
            "plan": [],
            "conversation_summary": "GOAL-42",
        }
        with patch(_PLANNER_LLM, return_value=llm):
            await PlannerRunner(api_key="sk-test").replan_remaining(state)
        blob = "\n".join(captured)
        self.assertNotIn("<conversation_summary>", blob)
        self.assertNotIn("GOAL-42", blob)


if __name__ == "__main__":
    unittest.main()
