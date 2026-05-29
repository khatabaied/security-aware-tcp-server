# Security-Aware Multi-Client TCP Server

## Overview

This project is a Python-based multi-client TCP server that allows multiple clients to connect to a central server and submit math requests over a structured JSON-based protocol.

The server handles concurrent client sessions using threads, places incoming math requests into a shared FIFO queue, processes each request in a consistent order, and returns structured results to each client.

For GitHub and resume presentation, this project is best framed as a network programming and security-aware server project. It demonstrates TCP socket programming, client-server communication, protocol design, request logging, input handling, session tracking, and graceful connection termination.

## Skills Demonstrated

- Python programming
- TCP socket programming
- Client-server architecture
- Threading and concurrency
- JSON protocol design
- FIFO request handling
- Input parsing
- Request logging
- Session management
- Network troubleshooting
- Technical documentation

## Key Features

- Multi-client server support
- Threaded client handling
- Shared FIFO request queue
- JSON line-based protocol
- Join/ack handshake
- Math request processing
- Client session tracking
- Request and response logging
- Graceful client disconnect handling
- Security-aware controls in the improved version, including authentication, input validation, rate limiting, and audit-style logging

## Architecture Summary

The application follows a central server and multiple client model. A client starts a session by connecting to the server and sending a join message with a client name. The server responds with an acknowledgement message, then accepts math requests from the client.

Each math request includes a message type, request identifier, and either a basic operation with operands or a full math expression. The server processes the request and returns a result or an error response. When the client is finished, it sends a close message and the server terminates the session cleanly.

## Protocol Design

The project uses a simple JSON-based protocol over TCP. Each message is sent as text with one JSON object per line. This makes message parsing more reliable because the server can separate individual messages using line boundaries.

Example message flow:

```text
client connects -> join -> server ack -> math request -> result/error -> close -> bye
```

## Programming Environment

The application was developed in Python using PyCharm for coding, testing, and debugging.

Example commands:

```bash
make server
make client
make client2
make client3
```

The server listens on localhost and clients connect using the same IP address and port. Multiple client instances can be started in separate terminals to simulate concurrent users.

## Screenshots

### Server Initialization

![Server Initialization](screenshots/server-initialization.png)

### Client Initialization

![Client Initialization](screenshots/client-initialization.png)

### Server - Simultaneous Client Loop

![Server Simultaneous Loop](screenshots/server-simultaneous-loop.png)

### Complex Equations - Server and Multiple Clients

![Complex Equations Server](screenshots/complex-equations-server.png)

![Complex Equations Client 1](screenshots/complex-equations-client1.png)

![Complex Equations Client 2](screenshots/complex-equations-client2.png)

![Complex Equations Client 3](screenshots/complex-equations-client3.png)

### Preprogrammed Loop Test

![Preprogrammed Loop Server](screenshots/preprogrammed-loop-server.png)

![Preprogrammed Loop Client](screenshots/preprogrammed-loop-client.png)

## What I Learned

This project helped strengthen my understanding of how network applications communicate over TCP. I practiced building a server that can handle multiple clients, designing a structured protocol, tracking client sessions, logging activity, and debugging client-server communication issues.

## Suggested Resume Description

**Security-Aware Multi-Client TCP Server | Python, TCP Sockets, Threading, JSON**  
Built a Python TCP server that accepts concurrent client connections and processes math requests over a JSON-based protocol. Implemented threaded client handling
