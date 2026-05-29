"""Main TCP server for the math service.

How this server works:
It accepts many client sockets at the same time (one handler thread per client).
Every client must send `join` first and receive `ack`.
Math requests from all clients go into one shared FIFO queue.
One worker thread processes that queue in order and sends results.
It logs connect/join/request/response/disconnect events.

So the  queue + single worker setup is what keeps global response order consistent
across different clients.
"""

# TCP socket API.
import socket
# Threads and locks for concurrency.
import threading
# Path/sys used for robust imports when run in different ways.
from pathlib import Path
import sys
# Used to timestamp log lines.
from datetime import datetime
# Used by integration demo timing.
import time
# Shared FIFO queue used to enforce global request order.
from queue import Queue
# Monotonic counter for global request IDs.
import itertools
# Lets cleanup ignore expected close errors.
from contextlib import suppress

# Resolve project root so imports work from CLI and IDE runs.
PROJECT_ROOT = Path(__file__).resolve().parents[2]

if __package__ is None or __package__ == "":
    # Support running this file directly, not only with `python -m`.
    if str(PROJECT_ROOT) not in sys.path:
        sys.path.insert(0, str(PROJECT_ROOT))

from network_project.server.client_session import ClientSession
from network_project.server.math_engine import calculate
from network_project.shared.config import HOST, PORT
from network_project.shared.protocol import send_json, recv_json
from network_project.server.security_monitor import (
    security_event,
    validate_join_request,
    validate_math_message,
)

# Central log path used by log_event().
LOG_DIR = PROJECT_ROOT / "network_project" / "logs"
LOG_FILE = LOG_DIR / "server.log"
# Sequence number shared across all clients.
REQUEST_COUNTER = itertools.count(1)
# All math jobs go here, then one worker drains it.
MATH_REQUEST_QUEUE = Queue()
# Prevents interleaved log writes from multiple threads.
LOG_LOCK = threading.Lock()
# Runtime flag: include verbose analysis fields when enabled.
SERVER_VERBOSE_MODE = False


class MathJob:
    """Represents one math request waiting in the global queue.

    We package everything the worker needs:
    - sequence_id: global arrival order across clients
    - session: where to send the result
    - request_id: echoed back so client can match response
    - operation/operands/expression: math payload
    - done_event: lets handler wait until this job finishes
    """

    def __init__(self, sequence_id, session, request_id, operation, operands, expression):
        # Keep all request data together for the worker thread.
        self.sequence_id = sequence_id
        self.session = session
        self.request_id = request_id
        self.operation = operation
        self.operands = operands
        self.expression = expression
        self.done_event = threading.Event()


def log_event(message):
    """Write one timestamped log line to console and network_project/logs/server.log."""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{timestamp}] {message}"

    with LOG_LOCK:
        # Print live so behavior is easy to watch while running.
        print(line)
        try:
            LOG_DIR.mkdir(parents=True, exist_ok=True)
            with LOG_FILE.open("a", encoding="utf-8") as log_file:
                log_file.write(line + "\n")
        except Exception as error:
            # Logging should never crash server threads.
            print(f"[LOGGING ERROR] {error}")


def process_math_requests():
    """Worker loop that processes queued math requests in strict FIFO order.

    This is the core reason global ordering works across different clients.
    """
    while True:
        job = MATH_REQUEST_QUEUE.get()

        if job is None:
            # Test cleanup sends this sentinel to stop the worker.
            MATH_REQUEST_QUEUE.task_done()
            return

        try:
            # Run math logic in one place (math_engine).
            calc_result = calculate(
                job.operation,
                job.operands,
                job.expression,
                verbose=SERVER_VERBOSE_MODE,
            )

            # Build protocol response payload.
            if calc_result["status"] == "ok":
                response = {
                    "type": "result",
                    "request_id": job.request_id,
                    "status": "ok",
                    "result": calc_result["result"]
                }
            else:
                response = {
                    "type": "result",
                    "request_id": job.request_id,
                    "status": "error",
                    "error": calc_result["error"]
                }
            if SERVER_VERBOSE_MODE and "analysis" in calc_result:
                response["analysis"] = calc_result["analysis"]

            # Lock write path for this client stream.
            with job.session.send_lock:
                send_json(job.session.conn_file, response)

            log_event(
                f"[RESPONSE #{job.sequence_id}] to {job.session.name} "
                f"{format_math_payload(job.operation, job.operands, job.expression)} -> "
                f"{response.get('result', response.get('error'))}"
            )
            if SERVER_VERBOSE_MODE and "analysis" in calc_result:
                analysis = calc_result["analysis"]
                counts = analysis.get("counts", {})
                operands = analysis.get("operands", [])
                operators = analysis.get("operators", [])
                operands_text = ", ".join(
                    f"{item['index']}:{item['value']}" for item in operands
                )
                operators_text = ", ".join(
                    f"{item['index']}:{item['name']}({item['symbol']})" for item in operators
                )
                log_event(
                    f"[VERBOSE #{job.sequence_id}] normalized={analysis.get('normalized_expression')}"
                )
                log_event(
                    f"[VERBOSE #{job.sequence_id}] counts operands={counts.get('operand_count', 0)} "
                    f"operators={counts.get('operator_count', 0)}"
                )
                log_event(
                    f"[VERBOSE #{job.sequence_id}] operands [{operands_text}]"
                )
                log_event(
                    f"[VERBOSE #{job.sequence_id}] operators [{operators_text}]"
                )
        except Exception as error:
            # Log and continue so one bad request does not kill the server.
            log_event(f"[WORKER ERROR] request #{job.sequence_id} -> {error}")
        finally:
            # Release waiting handler thread for this request.
            job.done_event.set()
            MATH_REQUEST_QUEUE.task_done()


def format_math_payload(operation, operands, expression):
    """Format request payload into readable text for logs."""
    if expression is not None:
        return f"expr '{expression}'"
    return f"{operation} {operands}"


def handle_client(conn, addr):
    """Handle one client socket from join handshake through disconnect."""
    conn_file = None
    session = None

    try:
        conn_file = conn.makefile(mode='rw')
        log_event(f"[NEW CONNECTION] {addr}")

        first_message = recv_json(conn_file)

        if first_message is None:
            # Connected but closed socket before sending join.
            log_event(f"[DISCONNECTED EARLY] {addr}")
            return

        if first_message.get("type") != "join":
            # Protocol rule: first message must be join.
            security_event("PROTOCOL_VIOLATION", addr, "first message was not join", log_event)
            send_json(conn_file, {
                "type": "error",
                "message": "First message must be a join request"
            })
            return

        is_valid_join, join_error = validate_join_request(first_message, addr, log_event)
        if not is_valid_join:
            send_json(conn_file, {
                "type": "error",
                "message": join_error
            })
            return

        client_name = first_message.get("name", "Unknown")
        # Create session object that tracks this client's state.
        session = ClientSession(client_name, conn, conn_file, addr)

        log_event(f"[JOIN] {session.name} joined from {session.ip}:{session.port} at {session.connect_time}")

        with session.send_lock:
            send_json(conn_file, {
                "type": "ack",
                "status": "ok",
                "message": f"Welcome {session.name}"
            })

        # Main receive loop for this client.
        while True:
            message = recv_json(conn_file)

            if message is None:
                # EOF from this client.
                break

            msg_type = message.get("type")

            if msg_type == "math":

                is_valid_request, request_error = validate_math_message(message, session, log_event)
                if not is_valid_request:
                    with session.send_lock:
                        send_json(conn_file, {
                            "type": "result",
                            "request_id": message.get("request_id"),
                            "status": "error",
                            "error": request_error
                        })
                    continue

                # Global sequence ID (not per-client) keeps ordering visible in logs.

                request_id = message.get("request_id")
                operation = message.get("operation")
                operands = message.get("operands", [])
                expression = message.get("expression")
                session.request_count += 1
                sequence_id = next(REQUEST_COUNTER)
                job = MathJob(
                    sequence_id=sequence_id,
                    session=session,
                    request_id=request_id,
                    operation=operation,
                    operands=operands,
                    expression=expression,
                )
                MATH_REQUEST_QUEUE.put(job)

                log_event(
                    f"[REQUEST #{sequence_id}] {session.name} "
                    f"sent {format_math_payload(operation, operands, expression)}"
                )
                # Wait for this job to finish before reading this client's next message.

                job.done_event.wait()

            elif msg_type == "close":
                # Normal, explicit client shutdown.


                with session.send_lock:
                    send_json(conn_file, {
                        "type": "bye",
                        "message": f"Goodbye {session.name}"
                    })

                break

            else:
                # Unknown message type: report error but keep client connected.
                security_event("UNSUPPORTED_MESSAGE_TYPE", session, f"msg_type={msg_type!r}", log_event)
                with session.send_lock:
                    send_json(conn_file, {
                        "type": "error",
                        "message": f"Unsupported message type: {msg_type}"
                    })

    except Exception as e:
        log_event(f"[ERROR] {addr} -> {e}")

    finally:

        if session is not None:
            # This records session end and log summary. Whcih matches the protocol format

            session.end_session()
            log_event(
                f"[DISCONNECTED] {session.name} from {session.ip}:{session.port} | "
                f"Duration: {session.get_duration_seconds():.2f}s | "
                f"Requests: {session.request_count}"
            )
        else:
            log_event(f"[DISCONNECTED] {addr}")

        if conn_file is not None:
            with suppress(Exception):

                conn_file.close()
        with suppress(Exception):
            conn.close()


def start_server():
    """Start worker thread and listening socket, the job of this is to accept client requests"""
    global SERVER_VERBOSE_MODE
    run_integration_demo = False

    with suppress(Exception):
        verbose_choice = input("Enable server verbose mode? (y/n): ").strip().lower()
        SERVER_VERBOSE_MODE = verbose_choice == "y"
    with suppress(Exception):
        integration_choice = input(
            "Run startup integration demo for simultaneous clients? (y/n): "
        ).strip().lower()
        run_integration_demo = integration_choice == "y"

    worker = threading.Thread(target=process_math_requests, daemon=True)
    # Daemon so process can exit without waiting for this thread indefinitely.
    worker.start()

    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.bind((HOST, PORT))
    server.listen()

    log_event(f"[LISTENING] Server running on {HOST}:{PORT}")
    log_event(f"[SERVER MODE] verbose={'on' if SERVER_VERBOSE_MODE else 'off'}")
    if run_integration_demo:
        log_event(
            "[INTEGRATION DEMO] enabled: two demo clients will join, send overlapping "
            "math requests, and close automatically."
        )
        demo_thread = threading.Thread(target=run_startup_integration_demo, daemon=True)
        demo_thread.start()

    while True:
        # Wait for next client.
        conn, addr = server.accept()
        # Each client gets its own handler thread.
        thread = threading.Thread(target=handle_client, args=(conn, addr))
        thread.start()


def run_startup_integration_demo():
    """Optional built-in demo using two simultaneous clients.

    It demonstrates:
    - join/ack handshake
    - overlapping requests from two clients
    - clean close/bye flow
    """
    # Let the server enter accept loop first.
    time.sleep(0.4)

    client_a_steps = [
        {"delay": 0.0, "expression": "2 + 2"},
        {"delay": 0.35, "expression": "(8-3) * 2"},
    ]
    client_b_steps = [
        {"delay": 0.15, "expression": "9 % 4"},
        {"delay": 0.20, "expression": "10 / 2"},
    ]

    log_event("[INTEGRATION DEMO] starting client threads: demo-alice and demo-bob")
    thread_a = threading.Thread(
        target=run_demo_client,
        args=("demo-alice", client_a_steps),
        daemon=True,
    )
    thread_b = threading.Thread(
        target=run_demo_client,
        args=("demo-bob", client_b_steps),
        daemon=True,
    )
    thread_a.start()
    thread_b.start()
    thread_a.join()
    thread_b.join()
    log_event("[INTEGRATION DEMO] completed")


def run_demo_client(name, steps):
    """Run one scripted demo client from connect to close.

    Each `steps` item is:
    `{"delay": <seconds>, "expression": "<math expression>"}`
    """
    client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    client_file = None
    try:
        client.connect((HOST, PORT))
        client_file = client.makefile(mode="rw")

        send_json(client_file, {"type": "join", "name": name, "auth_token": "student-lab-token"})
        ack = recv_json(client_file)
        if not isinstance(ack, dict) or ack.get("type") != "ack" or ack.get("status") != "ok":
            log_event(f"[INTEGRATION DEMO] {name}: join failed -> {ack}")
            return

        log_event(f"[INTEGRATION DEMO] {name}: joined successfully")

        request_id = 1
        for step in steps:
            time.sleep(step["delay"])
            expression = step["expression"]
            send_json(
                client_file,
                {
                    "type": "math",
                    "request_id": request_id,
                    "expression": expression,
                },
            )
            result = recv_json(client_file)
            log_event(
                f"[INTEGRATION DEMO] {name}: req#{request_id} expr '{expression}' -> {result}"
            )
            request_id += 1

        send_json(client_file, {"type": "close"})
        bye = recv_json(client_file)
        log_event(f"[INTEGRATION DEMO] {name}: close -> {bye}")
    except Exception as error:
        log_event(f"[INTEGRATION DEMO] {name}: error -> {error}")
    finally:
        if client_file is not None:
            with suppress(Exception):
                client_file.close()
        with suppress(Exception):
            client.close()


if __name__ == "__main__":
    start_server()
