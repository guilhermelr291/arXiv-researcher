"""Writer-only arithmetic tool: ast walk, never eval/exec."""

from __future__ import annotations

import ast
import operator

from langchain_core.tools import ToolException, tool
from pydantic import BaseModel, Field

from plan_based_researcher.policy import Policy

_OPS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.Pow: operator.pow,
}


class CalculatorInput(BaseModel):
    expression: str = Field(
        description=(
            "One arithmetic string of numeric literals only: int, float, 1eN, "
            "+ - * / **, unary minus, parentheses. Copy figures from packed "
            "[n] chunks. No names, variables, or calls. Example: 2+3*4"
        )
    )


def _eval(node: ast.AST) -> int | float:
    if isinstance(node, ast.Expression):
        return _eval(node.body)
    if isinstance(node, ast.Constant) and type(node.value) in (int, float):
        return node.value
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.USub):
        return -_eval(node.operand)
    if isinstance(node, ast.BinOp) and type(node.op) in _OPS:
        return _OPS[type(node.op)](_eval(node.left), _eval(node.right))
    raise ValueError("unsupported expression")


@tool("calculator", args_schema=CalculatorInput)
def calculator(expression: str) -> str:
    """Exact arithmetic on packed-chunk numbers. Call instead of multiplying in your head."""
    try:
        if not expression.strip():
            raise ValueError("empty expression")
        if len(expression) > Policy.writer_calculator_expression_max:
            raise ValueError("expression too long")
        value = _eval(ast.parse(expression, mode="eval"))
        if isinstance(value, float) and value.is_integer():
            value = int(value)
        return str(value) if isinstance(value, int) else format(value, ".16g")
    except Exception as exc:
        raise ToolException(f"error: {exc}") from exc


calculator.handle_tool_error = True
calculator.handle_validation_error = True
