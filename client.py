"""Interactive TCP client for the math server.

This is the user-side program.
Flow is:
1) connect to server
2) send join and wait for ack
3) send math requests (preset mode or manual mode)
4) send close and wait for bye
"""

# TCP client socket.
import socket
# Supports direct file execution and module execution.
from pathlib import Path
import sys
# Cleanup helper so close errors do not crash shutdown.
from contextlib import suppress
# Random request generation and pacing delays.
import random
import time

# Makes imports work when running this file directly.
if __package__ is None or __package__ == "":
    PROJECT_ROOT = Path(__file__).resolve().parents[2]
    if str(PROJECT_ROOT) not in sys.path:
        sys.path.insert(0, str(PROJECT_ROOT))

from network_project.shared.config import HOST, PORT, AUTH_TOKEN
from network_project.shared.protocol import send_json, recv_json

# Supported operation names in short input form.
SUPPORTED_OPERATIONS = {"add", "sub", "mul", "div", "mod"}


def parse_equation_input(raw_text):
    """Convert user input into math payload fields.

    Supported quick formats:
    - `add 5 3`
    - `5 + 3`
    Anything else non-empty is treated as an expression string.
    """
    text = raw_text.strip()
    # Empty input means nothing to send.
    if not text:
        return None

    # Split by spaces so we can detect short forms like "add 5 3" and "5 + 3".
    parts = text.split()

    # Operation-word form: add 5 3
    if len(parts) == 3 and parts[0].lower() in SUPPORTED_OPERATIONS:
        op = parts[0].lower()
        try:
            a = float(parts[1])
            b = float(parts[2])
            return {"operation": op, "operands": [a, b]}
        except ValueError:
            return None

    # Symbol form: 5 + 3
    if len(parts) == 3 and parts[1] in {"+", "-", "*", "/", "%"}:
        # Protocol uses operation words, so convert symbol to operation name.
        symbol_to_op = {"+": "add", "-": "sub", "*": "mul", "/": "div", "%": "mod"}
        try:
            a = float(parts[0])
            b = float(parts[2])
            return {"operation": symbol_to_op[parts[1]], "operands": [a, b]}
        except ValueError:
            return None

    # Everything else goes to expression mode as-is.
    return {"expression": text}


def prompt_mode():
    """Prompt until user chooses preset mode (1) or manual mode (2)."""
    while True:
        mode = input("Type 1 to run preset loop or 2 to enter an equation: ").strip()
        if mode in {"1", "2"}:
            return mode
        print("Invalid selection. Type 1 or 2.")


def build_random_math_request(request_id):
    """Build one random operation-mode math request."""
    operation_to_symbol = {
        "add": "+",
        "sub": "-",
        "mul": "*",
        "div": "/",
        "mod": "%",
    }
    operation = random.choice(list(operation_to_symbol.keys()))
    # Keep numbers simple for readable output.
    left = random.randint(1, 50)
    right = random.randint(1, 50)

    # Avoid divide/mod by zero in generated requests.
    if operation in {"div", "mod"} and right == 0:
        right = 1

    return (
        {
            "type": "math",
            "request_id": request_id,
            "operation": operation,
            "operands": [left, right],
        },
        f"{left} {operation_to_symbol[operation]} {right}",
    )


def send_math_and_print_response(client_file, request):
    """Send one math request and print success/error result."""
    # Shared request path used by both preset and manual modes.
    send_json(client_file, request)
    response = recv_json(client_file)
    # Protocol marks success with status=ok.
    if isinstance(response, dict) and response.get("status") == "ok":
        print(f"Result: {response.get('result')}")
    else:
        error_message = response.get("error") if isinstance(response, dict) else "Unknown error"
        print(f"Error: {error_message}")


def start_client():
    """Run client from connection start to graceful shutdown."""
    client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    # File wrapper makes line-based JSON send/receive easier.
    client_file = None

    try:
        # Connect to configured host/port.
        client.connect((HOST, PORT))
        client_file = client.makefile(mode='rw')

        name = input("Enter your name: ")

        # Handshake step 1: identify this client.
        token = input("Enter lab access token: ").strip() or AUTH_TOKEN

        send_json(client_file, {
            "type": "join",
            "name": name,
            "auth_token": token
        })

        # Handshake step 2: continue only if server acknowledges join.
        response = recv_json(client_file)
        if not isinstance(response, dict) or response.get("type") != "ack" or response.get("status") != "ok":
            print("Connection was not acknowledged by server. Closing client.")
            return

        # Join succeeded, so normal request flow starts here.
        print(response.get("message", "Connected."))
        request_id = 1
        mode = prompt_mode()
        if mode == "1":
            # Preset mode sends 20 requests at random intervals.
            print("Running preset loop with 20 random equations...")
            for _ in range(20):
                # Delay so requests are not sent at a fixed cadence.
                wait_seconds = random.uniform(0.5, 2.0)
                time.sleep(wait_seconds)
                request, equation_text = build_random_math_request(request_id)
                print(f"Equation {request_id}: {equation_text}")
                send_math_and_print_response(client_file, request)
                # request_id is echoed back by the server in result messages.
                request_id += 1
        else:
            # Manual mode: user types equations one by one.
            print("Enter equations like: add 5 3, 8 % 3, or (2-3)/2 + 2")
            print("Type 'close' to disconnect at any time.")
            while True:
                raw_equation = input(f"Equation {request_id}: ")
                if raw_equation.strip().lower() in {"close", "exit", "quit"}:
                    # User chooses to stop entering equations.
                    break
                parsed = parse_equation_input(raw_equation)

                if parsed is None:
                    print("Invalid format. Try: add 5 3 or (2-3)/2 + 2")
                    continue

                # Common request envelope for both operation/expression payloads.
                request = {
                    "type": "math",
                    "request_id": request_id,
                }
                if "expression" in parsed:
                    request["expression"] = parsed["expression"]
                else:
                    request["operation"] = parsed["operation"]
                    request["operands"] = parsed["operands"]

                send_math_and_print_response(client_file, request)

                again = input("Send another equation? (y/n): ").strip().lower()
                if again != "y":


                    break
                request_id += 1

        # Graceful protocol shutdown.
        send_json(client_file, {
            "type": "close"
        })

        response = recv_json(client_file)
        if isinstance(response, dict):
            print(response.get("message", "Disconnected."))
    except (ConnectionRefusedError, ConnectionResetError, OSError) as error:
        # Common networking errors: server down, reset connection, etc.
        print(f"Connection error: {error}. Ensure server is running on {HOST}:{PORT}.")
    finally:
        # Always attempt cleanup.
        if client_file is not None:
            with suppress(Exception):
                client_file.close()
        with suppress(Exception):
            client.close()


if __name__ == "__main__":
    start_client()
