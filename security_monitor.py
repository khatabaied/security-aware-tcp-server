"""Security monitoring helpers for the TCP math server.

This module adds light-weight security controls that make the project more
security-focused, I added additional secuirty features, like input validation
to make the server more secuire and realistic, as well as adding things like rate limiting.
"""

import re
import time
from collections import defaultdict, deque

from network_project.shared.config import AUTH_TOKEN

MAX_NAME_LENGTH = 32
MAX_EXPRESSION_LENGTH = 120
MAX_OPERANDS = 2
RATE_LIMIT_WINDOW_SECONDS = 10
RATE_LIMIT_MAX_REQUESTS = 12

_NAME_RE = re.compile(r"^[A-Za-z0-9_.-]{1,32}$")
_EXPRESSION_RE = re.compile(r"^[0-9+\-*/%().\s]+$")

# Per-client request timestamps for basic rate limiting.
_REQUEST_TIMESTAMPS = defaultdict(deque)


def security_event(event_type, session_or_addr, details, log_func):
    """Write a structured security event to the normal server log."""
    if hasattr(session_or_addr, "name"):
        source = f"user={session_or_addr.name} ip={session_or_addr.ip}:{session_or_addr.port}"
    else:
        source = f"addr={session_or_addr}"
    log_func(f"[SECURITY] event={event_type} {source} details={details}")


def validate_join_request(message, addr, log_func):
    """Validate the client's first join message and shared lab token."""
    if not isinstance(message, dict):
        security_event("MALFORMED_JOIN", addr, "join payload was not a JSON object", log_func)
        return False, "Invalid join request"

    client_name = str(message.get("name", "")).strip()
    token = message.get("auth_token")

    if token != AUTH_TOKEN:
        security_event("AUTH_FAILED", addr, f"invalid token for name={client_name!r}", log_func)
        return False, "Authentication failed"

    if not _NAME_RE.match(client_name):
        security_event("INVALID_CLIENT_NAME", addr, f"rejected name={client_name!r}", log_func)
        return False, "Client name must be 1-32 characters and use only letters, numbers, '.', '_', or '-'"

    return True, "ok"


def validate_math_message(message, session, log_func):
    """Validate math request shape and flag suspicious input patterns."""
    if not isinstance(message, dict):
        security_event("MALFORMED_REQUEST", session, "request was not a JSON object", log_func)
        return False, "Invalid request"

    if is_rate_limited(session):
        security_event("RATE_LIMIT_TRIGGERED", session, "too many requests in short time window", log_func)
        return False, "Rate limit exceeded"

    expression = message.get("expression")
    operands = message.get("operands", [])
    operation = message.get("operation")

    if expression is not None:
        expression_text = str(expression)
        if len(expression_text) > MAX_EXPRESSION_LENGTH:
            security_event("LONG_EXPRESSION_REJECTED", session, f"length={len(expression_text)}", log_func)
            return False, "Expression is too long"
        if not _EXPRESSION_RE.match(expression_text):
            security_event("SUSPICIOUS_EXPRESSION_REJECTED", session, f"expression={expression_text!r}", log_func)
            return False, "Expression contains unsupported characters"
        return True, "ok"

    if operation not in {"add", "sub", "mul", "div", "mod"}:
        security_event("INVALID_OPERATION", session, f"operation={operation!r}", log_func)
        return False, "Unsupported operation"

    if not isinstance(operands, list) or len(operands) != MAX_OPERANDS:
        security_event("INVALID_OPERANDS", session, f"operands={operands!r}", log_func)
        return False, "Exactly two operands are required"

    for operand in operands:
        if not isinstance(operand, (int, float)):
            security_event("NON_NUMERIC_OPERAND", session, f"operand={operand!r}", log_func)
            return False, "Operands must be numeric"

    return True, "ok"


def is_rate_limited(session):
    """Return True if a client exceeds the request threshold."""
    key = f"{session.ip}:{session.port}:{session.name}"
    now = time.time()
    timestamps = _REQUEST_TIMESTAMPS[key]

    while timestamps and now - timestamps[0] > RATE_LIMIT_WINDOW_SECONDS:
        timestamps.popleft()

    timestamps.append(now)
    return len(timestamps) > RATE_LIMIT_MAX_REQUESTS
