"""Math parsing and evaluation logic that the suerver uses.

This is the calculator side of the server.
It supports:
1) operation mode (`add/sub/mul/div/mod` with two operands)
2) expression mode (full expression text like `(2-3)/2 + 2`)

Expression mode is intentionally safe. We parse into AST and evaluate only a
small allowlist of operators/nodes instead of using raw evaluations,
this makes it easier to handle differnet scenarios.
"""

# Parse expressions safely (without eval).
import ast
# Maps AST operators to Python arithmetic functions.
import operator
# Used by tokenizer to recognize numeric literals.
import re


# Binary operators allowed in expression mode.
_BIN_OPS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.Mod: operator.mod,
}

# Unary operators allowed in expression mode.

_UNARY_OPS = {
    ast.UAdd: operator.pos,
    ast.USub: operator.neg,
}

# Symbol -> operation name map used when building verbose analysis.
_OPERATOR_NAMES = {
    "+": "add",
    "-": "sub",
    "*": "mul",
    "/": "div",
    "%": "mod",
}

# Operation name -> symbol map used when building verbose analysis.
_OPERATION_TO_SYMBOL = {
    "add": "+",
    "sub": "-",
    "mul": "*",
    "div": "/",
    "mod": "%",
}


def _tokenize_expression(expression):
    """Break raw expression text into tokens."""
    tokens = []
    index = 0
    length = len(expression)

    while index < length:
        char = expression[index]

        if char.isspace():
            index += 1
            continue

        number_match = re.match(r"(\d+(\.\d+)?|\.\d+)", expression[index:])
        if number_match:
            # Numeric token examples: 12, 12.5, .5
            token = number_match.group(0)
            tokens.append(("NUMBER", token))
            index += len(token)
            continue

        if char in "+-*/%()":
            # Operators and parentheses are standalone tokens.
            token_type = "LPAREN" if char == "(" else "RPAREN" if char == ")" else "OP"
            tokens.append((token_type, char))
            index += 1
            continue

        raise ValueError("Invalid expression")

    return tokens


def _insert_implicit_multiplication(tokens):
    """Insert `*` in places where multiplication is implied.

    Examples:
    - 2(3+4) -> 2*(3+4)
    - (1+2)(3+4) -> (1+2)*(3+4)
    """
    normalized_tokens = []
    prev_type = None

    for token_type, token_value in tokens:
        # If a number/closing parenthesis is followed by a number/opening
        # parenthesis, we treat it as implied multiplication.
        if prev_type in {"NUMBER", "RPAREN"} and token_type in {"NUMBER", "LPAREN"}:
            normalized_tokens.append(("OP", "*"))
        normalized_tokens.append((token_type, token_value))
        prev_type = token_type

    return normalized_tokens


def _tokens_to_expression(tokens):
    """Join tokens back into a normalized expression string."""
    return "".join(token_value for _, token_value in tokens)


def _build_expression_analysis(normalized_expression, normalized_tokens):
    """Create verbose analysis payload for expression mode."""
    operands = []
    operators = []

    for token_type, token_value in normalized_tokens:
        if token_type == "NUMBER":
            operands.append(
                {"index": len(operands) + 1, "value": float(token_value)}
            )
        elif token_type == "OP":
            operators.append(
                {
                    "index": len(operators) + 1,
                    "symbol": token_value,
                    "name": _OPERATOR_NAMES[token_value],
                }
            )

    return {
        "normalized_expression": normalized_expression,
        "operands": operands,
        "operators": operators,
        "counts": {
            "operand_count": len(operands),
            "operator_count": len(operators),
        },
    }


def _build_operation_analysis(operation, operands):
    """Create verbose analysis payload for operation mode."""
    symbol = _OPERATION_TO_SYMBOL.get(operation, "?")
    operator_name = _OPERATOR_NAMES.get(symbol, operation)
    a, b = operands
    return {
        "normalized_expression": f"{a}{symbol}{b}",
        "operands": [
            {"index": 1, "value": float(a)},
            {"index": 2, "value": float(b)},
        ],
        "operators": [
            {
                "index": 1,
                "symbol": symbol,
                "name": operator_name,
            }
        ],
        "counts": {
            "operand_count": 2,
            "operator_count": 1,
        },
    }


def _normalize_expression(expression):
    """Tokenize expression and normalize it (including implied `*`)."""
    tokens = _tokenize_expression(expression)
    normalized_tokens = _insert_implicit_multiplication(tokens)
    normalized_expression = _tokens_to_expression(normalized_tokens)
    return normalized_expression, normalized_tokens


def _eval_ast(node):
    """Evaluate an expression AST recursively, but only for allowed nodes."""
    if isinstance(node, ast.Expression):
        return _eval_ast(node.body)

    if isinstance(node, ast.BinOp):
        # Evaluate both sides first, then apply the operator.
        left = _eval_ast(node.left)
        right = _eval_ast(node.right)
        op_type = type(node.op)
        if op_type not in _BIN_OPS:
            raise ValueError("Unsupported operator")
        if op_type in {ast.Div, ast.Mod} and right == 0:
            raise ZeroDivisionError("Division by zero")
        return _BIN_OPS[op_type](left, right)

    if isinstance(node, ast.UnaryOp):
        # Only unary +x and -x are allowed.
        operand = _eval_ast(node.operand)
        op_type = type(node.op)
        if op_type not in _UNARY_OPS:
            raise ValueError("Unsupported unary operator")
        return _UNARY_OPS[op_type](operand)

    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
        # Plain numeric literal.
        return node.value

    # Block everything else for safety.
    raise ValueError("Unsupported expression syntax")


def evaluate_expression(expression, verbose=False):
    """Evaluate expression text and return protocol-style result dict."""
    try:
        normalized, normalized_tokens = _normalize_expression(expression)
        # Turn text into AST first.
        parsed = ast.parse(normalized, mode="eval")
        # Evaluate using only allowed AST node/operator rules.
        result = _eval_ast(parsed)
        response = {"status": "ok", "result": result}
        if verbose:
            response["analysis"] = _build_expression_analysis(normalized, normalized_tokens)
        return response
    except ZeroDivisionError:
        # Keep this error message consistent with operation mode.
        response = {"status": "error", "error": "Division by zero"}
        if verbose:
            try:
                normalized, normalized_tokens = _normalize_expression(expression)
                response["analysis"] = _build_expression_analysis(normalized, normalized_tokens)
            except ValueError:
                pass
        return response

    # Parse/validation/type issues are all reported as invalid expression.
    except (SyntaxError, ValueError, TypeError):
        return {"status": "error", "error": "Invalid expression"}


def calculate(operation=None, operands=None, expression=None, verbose=False):
    """Main entry point used by server code.

    If `expression` is provided, expression mode is used.
    Otherwise operation mode (`operation` + `operands`) is used.
    Here we are handling the responses based on the different expressions we cant divide by zero for example
    """
    if expression is not None:
        # Expression field always wins if present.
        return evaluate_expression(expression, verbose=verbose)

    if operands is None or len(operands) != 2:
        return {"status": "error", "error": "Exactly 2 operands are required"}

    a, b = operands

    if operation == "add":
        # Direct operation mode math.
        response = {"status": "ok", "result": a + b}
    elif operation == "sub":
        response = {"status": "ok", "result": a - b}

    elif operation == "mul":
        response = {"status": "ok", "result": a * b}
    elif operation == "div":
        if b == 0:
            return {"status": "error", "error": "Division by zero"}

        response = {"status": "ok", "result": a / b}
    elif operation == "mod":
        if b == 0:
            return {"status": "error", "error": "Division by zero"}

        response = {"status": "ok", "result": a % b}
    else:
        return {"status": "error", "error": f"Unsupported operation: {operation}"}

    if verbose:
        response["analysis"] = _build_operation_analysis(operation, operands)
    return response
