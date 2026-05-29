# Security-Focused Additions

This version keeps the original multi-client TCP math server but adds light-weight security controls and audit-style logging.

## Added Controls

- Shared lab access token during the join handshake
- Client name validation to reduce log injection/noisy identities
- Input validation for math messages
- Expression length limits
- Character allowlist for expression-mode requests
- Numeric operand validation
- Basic per-client rate limiting
- Structured security events written to `network_project/logs/server.log`

## Example Security Events

The server now logs events like:

```text
[SECURITY] event=AUTH_FAILED addr=('127.0.0.1', 50000) details=invalid token for name='alice'
[SECURITY] event=SUSPICIOUS_EXPRESSION_REJECTED user=alice ip=127.0.0.1:50001 details=expression='__import__("os")'
[SECURITY] event=RATE_LIMIT_TRIGGERED user=alice ip=127.0.0.1:50001 details=too many requests in short time window
```

## Resume Framing

This is still a networking/programming project, but it can now be described as security-aware because it includes authentication, input validation, rate limiting, and audit logging.
