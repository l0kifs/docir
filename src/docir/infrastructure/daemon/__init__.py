# Daemon adapters — the long-lived local worker and its transport.
#
#   * protocol  — length-prefixed JSON framing over the socket.
#   * server    — the Unix-socket server loop (serializes requests, idle-timeout).
#   * client    — a thin connect/send/receive socket client.
#   * lifecycle — PID file, detached spawn, readiness wait, stop/status.
#   * executor  — the RequestExecutor that talks to the daemon (spawning it
#                 transparently and respawning on a stale socket).
