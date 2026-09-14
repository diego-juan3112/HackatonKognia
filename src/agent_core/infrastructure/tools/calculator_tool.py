"""
Herramienta de ejemplo: NO depende de ninguna API externa.

Sirve para dos cosas:
  1. Mostrar el patrón para agregar una tool nueva al agente.
  2. Permitir probar que el grafo de LangGraph funciona de punta a
     punta sin gastar tiempo/credenciales en Azure u OpenAI mientras
     armas el resto del pipeline (ver tests/test_agent_smoke.py).
"""

import ast
import operator

from langchain_core.tools import tool

_ALLOWED_OPERATORS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.Pow: operator.pow,
    ast.USub: operator.neg,
}


def _safe_eval(node: ast.AST) -> float:
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
        return node.value
    if isinstance(node, ast.BinOp) and type(node.op) in _ALLOWED_OPERATORS:
        return _ALLOWED_OPERATORS[type(node.op)](
            _safe_eval(node.left), _safe_eval(node.right)
        )
    if isinstance(node, ast.UnaryOp) and type(node.op) in _ALLOWED_OPERATORS:
        return _ALLOWED_OPERATORS[type(node.op)](_safe_eval(node.operand))
    raise ValueError("Expresión matemática no soportada")


@tool
def calculator(expression: str) -> str:
    """Evalúa una expresión aritmética simple, ej: '2 + 2 * 10'."""
    try:
        tree = ast.parse(expression, mode="eval").body
        return str(_safe_eval(tree))
    except Exception as exc:  # noqa: BLE001
        return f"No pude evaluar '{expression}': {exc}"
