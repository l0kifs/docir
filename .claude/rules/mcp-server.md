---
paths:
  - "src/docir/entry_points/mcp/**"
  - "src/docir/entry_points/payload.py"
---

# The MCP server

A third client of the dispatcher, never a second implementation.

- **`docir mcp serve` is a third client of the dispatcher, not a second implementation
  (adr-354a4270ecd8).** Every tool in `entry_points/mcp/server.py` is one `Request` through a
  `RequestExecutor` — the same boundary the CLI and the daemon socket cross, which is the
  mechanism behind the equivalence README claims. Exactly one tool per dispatcher command
  (`ping` excepted: a liveness probe, not a document operation) plus **two** that are not
  commands and could not be: `docir_schema`, and `docir_doctor` (adr-a18d0577739f).
  `doctor` snapshots the environment *before* anything dispatches — dispatching is what
  replaces a stale daemon and builds a missing index — so a `doctor` command would report the
  state after the repairs it exists to report. Its composition (`build_report`) and payload
  shape (`as_payload`) therefore live in `entry_points/doctor.py` and are shared with the CLI,
  which keeps only the spinner and the table-or-JSON choice: a second transport composing the
  report itself is exactly the drift this rule prevents, and it would show up only as two
  reports that disagree. A third exception stays a decision, because the tool-surface test
  names both by hand. `test_mcp_server.py` asserts the
  exposed tool **names** against `Dispatcher._handlers`, so a new command that reaches only
  the CLI fails the build; the names are prefixed (`docir_context`) because the CLI's are
  generic verbs that collide in a client's tool list, and renaming one breaks saved prompts.
  Results go through the same `trim` as the piped CLI JSON — that is why it lives in
  `entry_points/payload.py` rather than in `cli/rendering.py`. `fastmcp` is a **default
  dependency**, not an extra: an agent that only speaks MCP cannot be told to install one.
  `server.py` imports it at module scope and `cmds.py` imports `server` *inside* the command —
  keep that lazy, it is ~0.3s of import that no other command should pay.
