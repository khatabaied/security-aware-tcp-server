"""Shared host/port settings used by both the client and the server."""

# Loopback means local-only testing on this machine.
# Change this to your LAN IP if you want remote clients to connect.
HOST = "127.0.0.1"
# Both sides must use the same port number.
PORT = 5050

# Shared lab token required during the client join handshake.
# This is intentionally simple for a local portfolio/demo project.
AUTH_TOKEN = "student-lab-token"
