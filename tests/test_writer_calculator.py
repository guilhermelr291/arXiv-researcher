"""Writer calculator checks C1–C21, C26–C36 (CALC-01–03, CALC-05–06)."""

from __future__ import annotations

import ast
import inspect
import unittest
from types import SimpleNamespace
from typing import cast
from unittest.mock import MagicMock, patch

from langchain_core.messages import ToolMessage
from langchain_core.tools import ToolException
from langgraph.prebuilt import ToolNode

from plan_based_researcher.agents import calculator as calculator_mod
from plan_based_researcher.agents.calculator import calculator
from plan_based_researcher.agents.factory import AgentFactory
from plan_based_researcher.agents.planner import PlannerRunner
from plan_based_researcher.agents.registry import PLAN_AGENTS, REGISTRY, planner_prompt_abilities
from plan_based_researcher.agents.writer import WriterRunner, _system_prompt
from plan_based_researcher.api.schemas import PlanStep, ResearchPlan
from plan_based_researcher.eval.strategies import (
    RetrieveEvalStrategy,
    SearchEvalStrategy,
)
from plan_based_researcher.graph.build import GraphDeps, build_graph
from plan_based_researcher.policy import Policy

from tests.test_writer_stream import (
    _CHAT,
    _GET_WRITER,
    _QueuedLLM,
    _chunk,
    _spy_stream_writer,
    _tool_chunk,
)

_PLANNER_LLM = "plan_based_researcher.agents.planner.ChatOpenAI"


def _calc(expression: str) -> str:
    return str(calculator.invoke({"expression": expression}))


def _eval_blob(messages: object) -> str:
    parts: list[str] = []
    if isinstance(messages, list):
        for item in messages:
            parts.append(_eval_blob(item))
        return "\n".join(parts)
    content = getattr(messages, "content", None)
    if content is not None:
        parts.append(str(content))
    name = getattr(messages, "name", None)
    if name is not None:
        parts.append(str(name))
    parts.append(str(messages))
    return "\n".join(parts)


class RegistryPlannerTest(unittest.IsolatedAsyncioTestCase):
    def test_registry_writer_tools_is_calculator(self) -> None:
        self.assertEqual(REGISTRY["writer"].tools, ("calculator",))

    def test_planner_abilities_include_arithmetic_capability(self) -> None:
        self.assertIn(
            "compute arithmetic on numbers present in packed chunks",
            planner_prompt_abilities(),
        )

    def test_planner_abilities_omit_calculator_name(self) -> None:
        self.assertNotIn("calculator", planner_prompt_abilities())

    def test_plan_agents_unchanged(self) -> None:
        self.assertEqual(PLAN_AGENTS, frozenset({"search", "retrieve", "writer"}))

    async def test_complete_rejects_calculator_agent_name(self) -> None:
        structured = MagicMock()

        async def ainvoke(_payload: object) -> ResearchPlan:
            return ResearchPlan(
                steps=[
                    PlanStep(
                        agent="calculator",
                        task="add the FLOPs",
                        reasoning="numbers are in the pack",
                    )
                ]
            )

        structured.ainvoke = ainvoke
        llm = MagicMock()
        llm.with_structured_output.return_value = structured
        with patch(_PLANNER_LLM, return_value=llm):
            runner = PlannerRunner(api_key="sk-test")
            with self.assertRaises(ValueError) as ctx:
                await runner._complete("plan please")
        self.assertIn("invalid agent name", str(ctx.exception))


class ProductGraphNodesTest(unittest.TestCase):
    def test_product_graph_nodes_exclude_calculator_and_tools(self) -> None:
        class _StubFactory:
            def create(self, name: str) -> object:
                raise RuntimeError("tests do not run agents")

        compiled = build_graph(
            GraphDeps(
                factory=cast(AgentFactory, _StubFactory()),
                search_eval=SearchEvalStrategy(api_key=None),
                retrieve_eval=RetrieveEvalStrategy(api_key=None),
            )
        )
        names = set(compiled.nodes) - {"__start__", "__end__"}
        expected = {
            "gate",
            "planner",
            "dispatch",
            "search",
            "execute",
            "evaluate",
            "replan",
            "finalize",
        }
        self.assertEqual(names, expected)
        self.assertNotIn("calculator", names)
        self.assertNotIn("tools", names)


class CalculatorEvalTest(unittest.TestCase):
    def test_eval_2_plus_3_times_4_is_14(self) -> None:
        self.assertEqual(_calc("2+3*4"), "14")

    def test_eval_10_div_4_is_2_5(self) -> None:
        self.assertEqual(_calc("10/4"), "2.5")

    def test_eval_2_pow_10_is_1024(self) -> None:
        self.assertEqual(_calc("2**10"), "1024")

    def test_eval_1e3_plus_1_is_1001(self) -> None:
        self.assertEqual(_calc("1e3+1"), "1001")

    def test_eval_unary_minus_paren_is_minus_5(self) -> None:
        self.assertEqual(_calc("-(2+3)"), "-5")

    def test_eval_empty_or_whitespace_returns_error(self) -> None:
        for expression in ("", "   ", "\n\t"):
            with self.subTest(expression=repr(expression)):
                result = _calc(expression)
                self.assertIn("error", result)

    def test_eval_name_os_returns_error(self) -> None:
        result = _calc("os")
        self.assertIn("error", result)

    def test_eval_div_zero_returns_error(self) -> None:
        result = _calc("1/0")
        self.assertIn("error", result)

    def test_eval_over_max_length_returns_error(self) -> None:
        expression = "0" * (Policy.writer_calculator_expression_max + 1)
        result = _calc(expression)
        self.assertIn("error", result)

    def test_calculator_module_ast_has_no_eval_or_exec_call(self) -> None:
        tree = ast.parse(inspect.getsource(calculator_mod))
        calls: list[str] = []
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            if isinstance(func, ast.Name) and func.id in {"eval", "exec"}:
                calls.append(func.id)
            if isinstance(func, ast.Attribute) and func.attr in {"eval", "exec"}:
                calls.append(func.attr)
        self.assertEqual(calls, [])


class GroundingCopyTest(unittest.TestCase):
    def test_grounding_rule_derived_arithmetic_carve_out(self) -> None:
        rule = Policy.GROUNDING_RULE
        self.assertIn("derived result", rule)
        self.assertIn("cite the operands", rule)
        self.assertIn("do not invent a citation for the result", rule)
        self.assertIn("do not treat the result as a new source", rule)
        self.assertIn("arithmetic on operands that each have a real [n]", rule)

    def test_writer_system_prompt_includes_grounding_rule(self) -> None:
        self.assertIn(Policy.GROUNDING_RULE, _system_prompt())

    def test_writer_abilities_mention_packed_chunk_arithmetic(self) -> None:
        abilities = REGISTRY["writer"].abilities
        self.assertIn("compute arithmetic", abilities)
        self.assertIn("packed chunks", abilities)

    def test_writer_abilities_omit_calculator_name(self) -> None:
        self.assertNotIn("calculator", REGISTRY["writer"].abilities)

    def test_calculator_schema_tells_writer_how_to_call(self) -> None:
        self.assertEqual(calculator.name, "calculator")
        schema = calculator.args["expression"]
        self.assertEqual(schema["type"], "string")
        self.assertIn("2+3*4", schema["description"])
        self.assertIn("No names", schema["description"])
        self.assertIn("calculator with expression", _system_prompt())
        self.assertNotIn("calculator", planner_prompt_abilities())


class WriterInnerGraphTest(unittest.TestCase):
    def test_inner_graph_routes_with_tools_condition(self) -> None:
        source = inspect.getsource(WriterRunner.__init__)
        self.assertIn("tools_condition", source)
        with patch(_CHAT, return_value=MagicMock()):
            runner = WriterRunner(api_key="sk-test")
        nodes = set(runner._inner.nodes)
        self.assertIn("writer", nodes)
        self.assertIn("tools", nodes)
        edges = {(edge.source, edge.target) for edge in runner._inner.get_graph().edges}
        self.assertIn(("writer", "tools"), edges)
        self.assertIn(("writer", "__end__"), edges)
        self.assertIn(("tools", "writer"), edges)

    def test_inner_graph_tools_node_is_tool_node(self) -> None:
        with patch(_CHAT, return_value=MagicMock()):
            runner = WriterRunner(api_key="sk-test")
        self.assertIsInstance(runner._tools_node, ToolNode)

    def test_calculator_handle_tool_error_true(self) -> None:
        self.assertIs(calculator.handle_tool_error, True)

    def test_calculator_handle_validation_error_true(self) -> None:
        self.assertIs(calculator.handle_validation_error, True)

    def test_writer_tool_node_handle_tool_errors_true(self) -> None:
        with patch(_CHAT, return_value=MagicMock()):
            runner = WriterRunner(api_key="sk-test")
        self.assertIs(runner._tools_node._handle_tool_errors, True)


class WriterToolLoopTest(unittest.IsolatedAsyncioTestCase):
    async def test_runner_invokes_calculator_then_sets_markdown(self) -> None:
        llm = _QueuedLLM(
            [
                [_tool_chunk("calculator", {"expression": "2+3*4"})],
                [SimpleNamespace(content="The total is 14 [1]")],
            ]
        )
        with (
            patch(_CHAT, return_value=llm),
            patch(_GET_WRITER, _spy_stream_writer([])),
        ):
            runner = WriterRunner(api_key="sk-test")
            with patch.object(calculator, "func", wraps=calculator.func) as spy:
                result = await runner.run(
                    {"query": "q", "evidence_chunks": [_chunk()]}
                )
        spy.assert_called_once_with(expression="2+3*4")
        self.assertEqual(result["writer_markdown"], "The total is 14 [1]")

    async def test_calculator_error_string_is_tool_result_not_outcome_error(self) -> None:
        llm = _QueuedLLM(
            [
                [_tool_chunk("calculator", {"expression": "1/0"})],
                [SimpleNamespace(content="Could not divide [1]")],
            ]
        )
        with (
            patch(_CHAT, return_value=llm),
            patch(_GET_WRITER, _spy_stream_writer([])),
        ):
            result = await WriterRunner(api_key="sk-test").run(
                {"query": "q", "evidence_chunks": [_chunk()]}
            )
        self.assertNotEqual(result.get("outcome"), "error")
        follow = _eval_blob(llm.astream_payloads[1])
        self.assertIn("error", follow.lower())

    async def test_unknown_tool_name_is_tool_error_not_raise(self) -> None:
        llm = _QueuedLLM(
            [
                [_tool_chunk("web_search", {"q": "x"})],
                [SimpleNamespace(content="No extra tool [1]")],
            ]
        )
        with (
            patch(_CHAT, return_value=llm),
            patch(_GET_WRITER, _spy_stream_writer([])),
        ):
            result = await WriterRunner(api_key="sk-test").run(
                {"query": "q", "evidence_chunks": [_chunk()]}
            )
        self.assertEqual(result["writer_markdown"], "No extra tool [1]")
        follow = _eval_blob(llm.astream_payloads[1])
        self.assertIn("error", follow.lower())

    async def test_after_round_cap_model_call_has_no_calculator_tool(self) -> None:
        llm = _QueuedLLM(
            [
                [_tool_chunk("calculator", {"expression": "1+1"})],
                [SimpleNamespace(content="Done [1]")],
            ]
        )
        with (
            patch(_CHAT, return_value=llm),
            patch(_GET_WRITER, _spy_stream_writer([])),
            patch.object(Policy, "writer_calculator_rounds", 1),
        ):
            await WriterRunner(api_key="sk-test").run(
                {"query": "q", "evidence_chunks": [_chunk()]}
            )
        self.assertEqual(len(llm.bind_calls), 1)
        self.assertEqual(len(llm.astream_payloads), 2)

    async def test_invalid_calculator_args_feed_error_tool_message(self) -> None:
        llm = _QueuedLLM(
            [
                [_tool_chunk("calculator", {})],
                [SimpleNamespace(content="Need an expression [1]")],
            ]
        )
        with (
            patch(_CHAT, return_value=llm),
            patch(_GET_WRITER, _spy_stream_writer([])),
        ):
            result = await WriterRunner(api_key="sk-test").run(
                {"query": "q", "evidence_chunks": [_chunk()]}
            )
        self.assertEqual(result["writer_markdown"], "Need an expression [1]")
        follow = llm.astream_payloads[1]
        self.assertTrue(
            any(
                isinstance(msg, ToolMessage) and "error" in str(msg.content).lower()
                for msg in follow
            )
        )

    async def test_tool_exception_feeds_error_tool_message(self) -> None:
        def boom(expression: str) -> str:
            raise ToolException("error: boom")

        llm = _QueuedLLM(
            [
                [_tool_chunk("calculator", {"expression": "2+2"})],
                [SimpleNamespace(content="Recovered [1]")],
            ]
        )
        with (
            patch(_CHAT, return_value=llm),
            patch(_GET_WRITER, _spy_stream_writer([])),
        ):
            runner = WriterRunner(api_key="sk-test")
            with patch.object(calculator, "func", side_effect=boom):
                result = await runner.run(
                    {"query": "q", "evidence_chunks": [_chunk()]}
                )
        self.assertEqual(result["writer_markdown"], "Recovered [1]")
        follow = llm.astream_payloads[1]
        self.assertTrue(
            any(
                isinstance(msg, ToolMessage) and "error" in str(msg.content).lower()
                for msg in follow
            )
        )


if __name__ == "__main__":
    unittest.main()
