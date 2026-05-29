# Used for connect/disconnect timestamps so we can compute session length.
from datetime import datetime
# One lock per client so writes to that client socket do not overlap.
import threading


class ClientSession:
    """Data container for one connected client.

    Think of this class as the server's "record" for a single client session.
    It stores who the client is, where they connected from, when they connected,
    when they disconnected, and how many math requests they sent.
    """

    def __init__(self, name, conn, conn_file, addr):
        # Identity + socket handles we keep for this session.
        self.name = name
        self.conn = conn
        self.conn_file = conn_file
        # Original (ip, port) tuple from server.accept().
        self.addr = addr
        self.ip = addr[0]
        self.port = addr[1]
        # Session timing fields.
        self.connect_time = datetime.now()
        self.disconnect_time = None
        # Counter for how many math requests this client sent.
        self.request_count = 0
        # Protects writes so two threads never write to this stream at once.
        self.send_lock = threading.Lock()

    def end_session(self):
        """Set disconnect timestamp when the session is ending."""
        self.disconnect_time = datetime.now()

    def get_duration_seconds(self):
        """Return session duration in seconds (0 if still active)."""
        if self.disconnect_time is None:
            return 0
        return (self.disconnect_time - self.connect_time).total_seconds()
