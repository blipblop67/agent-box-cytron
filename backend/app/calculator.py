"""
The Calculator node. Never uses raw eval() - once an expression can contain
arbitrary agent/LLM output, eval() is a code-execution hole. simpleeval
restricts evaluation to arithmetic (no attribute access, no imports, no
function calls beyond a small allow-listed math set).
"""
import math

from simpleeval import EvalWithCompoundTypes


def evaluate(expression: str) -> float:
    evaluator = EvalWithCompoundTypes(
        functions={
            "abs": abs, "round": round, "min": min, "max": max,
            "sqrt": math.sqrt, "pow": pow, "floor": math.floor, "ceil": math.ceil,
        },
        names={"pi": math.pi, "e": math.e},
    )
    result = evaluator.eval(expression)
    if not isinstance(result, (int, float)):
        raise ValueError(f"Expression did not evaluate to a number: {result!r}")
    return result
