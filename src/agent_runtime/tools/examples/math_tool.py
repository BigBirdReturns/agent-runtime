from __future__ import annotations
import ast
import operator as op
from typing import Any

from agent_runtime.tools.base import Tool, ToolError

_ALLOWED = {
    ast.Add: op.add,
    ast.Sub: op.sub,
    ast.Mult: op.mul,
    ast.Div: op.truediv,
    ast.Pow: op.pow,
    ast.USub: op.neg,
}

class MathTool(Tool):
    name = "math"
    description = "Evaluates a safe arithmetic expression."

    async def run(self, arguments: dict[str, Any]) -> dict[str, Any]:
        expr = str(arguments.get("expression", "")).strip()
        if not expr:
            raise ToolError("Missing expression", code="bad_input")
        expr = expr.replace("^", "**")
        try:
            value = self._eval(expr)
            return {"result": value}
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
