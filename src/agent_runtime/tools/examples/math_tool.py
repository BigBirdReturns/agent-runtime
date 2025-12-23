from __future__ import annotations
import ast
import operator as op
from typing import Any, Dict
from pydantic import BaseModel, Field, ValidationError

from agent_runtime.tools.base import Tool, ToolError

_ALLOWED = {
    ast.Add: op.add,
    ast.Sub: op.sub,
    ast.Mult: op.mul,
    ast.Div: op.truediv,
    ast.Pow: op.pow,
    ast.USub: op.neg,
}

class MathToolInput(BaseModel):
    expression: str = Field(
        ...,
        min_length=1,
        max_length=200,
        pattern=r"^[0-9\s\+\-\*/\^\(\)\.]+$",
        description="Arithmetic expression using digits and + - * / ^ ( ) .",
    )

class MathToolOutput(BaseModel):
    result: float

class MathTool(Tool):
    name = "math"
    description = "Evaluates a safe arithmetic expression."

    @property
    def input_schema(self) -> Dict[str, Any]:
        return MathToolInput.model_json_schema()

    @property
    def output_schema(self) -> Dict[str, Any]:
        return MathToolOutput.model_json_schema()

    async def run(self, arguments: dict[str, Any]) -> dict[str, Any]:
        try:
            inputs = MathToolInput(**arguments)
        except ValidationError as e:
            raise ToolError(f"Invalid input: {e.errors()}", code="bad_input")

        expr = inputs.expression.strip().replace("^", "**")
        try:
            value = float(self._eval(expr))
            return MathToolOutput(result=value).model_dump()
        except Exception as e:
            raise ToolError(f"Invalid expression: {e}", code="bad_input")

    def _eval(self, expr: str) -> float:
        node = ast.parse(expr, mode="eval").body
        return float(self._eval_node(node))

    def _eval_node(self, node):
        if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
            return node.value
        if isinstance(node, ast.BinOp) and type(node.op) in _ALLOWED:
            return _ALLOWED[type(node.op)](self._eval_node(node.left), self._eval_node(node.right))
        if isinstance(node, ast.UnaryOp) and type(node.op) in _ALLOWED:
            return _ALLOWED[type(node.op)](self._eval_node(node.operand))
        raise ValueError("Unsupported operation")
