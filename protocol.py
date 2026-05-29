"""Shared wire-format helpers.

TCP gives a stream of bytes, not ready-made messages.
So our project makes its own message boundary: one JSON object per line.
`send_json()` always writes a trailing newline, and `recv_json()` always reads
one line before parsing JSON.
"""

# JSON serialization/deserialization for the wire format.
import json


def send_json(sock_file, data):
    """Send one protocol message as a single newline-terminated JSON line."""
    # Framing rule in this project: exactly one JSON object per line.
    message = json.dumps(data)
    sock_file.write(message + "\n")
    sock_file.flush()


def recv_json(sock_file):
    """Read one JSON-line message. Return None if peer closed the stream."""
    # Empty read means EOF (remote side disconnected).
    line = sock_file.readline()
    if not line:
        return None
    # Remove trailing newline before json parsing.
    return json.loads(line.strip())
