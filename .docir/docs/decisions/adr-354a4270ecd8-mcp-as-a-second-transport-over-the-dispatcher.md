---
created: '2026-08-03'
description: Why docir mcp serve is a third client of the dispatcher rather than a
  second implementation.
id: adr-354a4270ecd8
owner: maintainer
related:
- adr-3a2d5ee7bc84
- kind: refines
  to: arch-1cfb1b212237
status: accepted
tags:
- architecture
- agents
title: MCP as a second transport over the dispatcher
type: decision
updated: '2026-08-05'
---

## Context

An agent can only use docir if it can reach the CLI. `docir agent install`
(adr-3a2d5ee7bc84) covers assistants that run shell commands — it teaches Claude Code or
an `AGENTS.md` reader to drive `docir context`, `docir add` and the rest. An
assistant that calls **tools over the Model Context Protocol and never runs a
shell** could not use docir at all, and that describes most clients now shipping:
Cursor, Codex, VS Code, ChatGPT and Claude Desktop discover capabilities as MCP
tools.

A survey of the adjacent field (`ref-a6db21f52427`) put this first among the
gaps: Basic Memory, qmd and sqlite-memory each ship an MCP server, and it is how
they are installed at all. It was also the cheapest gap to close, because the
command vocabulary already lives in exactly one place.

The design question was never *whether* — it was where the tools get their
behaviour from. A tool surface written against `DocumentService` would be a
second implementation of the same commands, free to drift from the CLI's
defaults, its validation and its output shape. The thing worth protecting is
that it cannot.

## Decision

Add **`docir mcp serve`** as a third client of `Dispatcher`, beside the CLI and
the daemon socket. `entry_points/mcp/` holds a `server.py` (the tool surface) and
a `cmds.py` (the Typer command); no business logic, per the entry_points rule.

- **Every tool is one `Request` through a `RequestExecutor`** — the same boundary
  the CLI crosses and the same one the daemon protocol crosses. There is exactly
  one tool per dispatcher command (19 of them), plus a `docir_schema` tool for
  the one thing an agent needs that is not a command: the merged types, statuses
  and relation kinds it must write against. `ping` is deliberately unexposed —
  it is the daemon's liveness probe, not a document operation.
- **The daemon is the default executor.** An MCP session is many calls over a
  long-lived process, which is precisely the case the warm model exists for;
  `--no-daemon` holds one in-process container open for the server's lifetime
  instead. Calls are serialized by a lock, because FastMCP runs sync tools in a
  thread pool and neither executor promises re-entrancy.
- **The read contract carries over unchanged.** `docir_context` /
  `docir_search` / `docir_query` return body-less skeletons; only `docir_get`
  carries a body. Every result passes through the same `trim` the piped CLI JSON
  uses — moved to `entry_points/payload.py` so both transports share one
  implementation rather than two that agree today.
- **Errors keep their identity.** A dispatcher failure and a transport failure
  both become a `ToolError` carrying the docir message. An exit code cannot
  cross MCP, so the message is the whole of what the client gets.
- **`fastmcp` ships by default, not behind an extra.** An extra is the smaller
  install and the wrong default: the audience for the MCP server is an agent
  that speaks *only* MCP, and such an agent cannot be told to install an extra,
  because it cannot reach docir to be told. Weighed against ~12 MB (onnxruntime,
  already a dependency, is 68 MB) that trade is not close. The cost that would
  have been real — fastmcp's ~0.3s import on every `docir get` — is avoided
  instead by structure: `server.py` imports fastmcp at module scope and
  `cmds.py` imports `server` *inside* the command, so only `mcp serve` pays it.
  The `embeddings` extra, a no-op alias since fastembed became a hard dependency,
  was dropped in the same change rather than left as a second way to say nothing.

## Consequences

- **The vocabulary now has three surfaces and one definition.** A new dispatcher
  command must be given a tool, and a test asserts the *names* of the exposed
  set against `Dispatcher._handlers` — a count could not tell "all exposed" from
  "the mapping and the dispatcher drifted together".
- **Tool names are frozen-ish.** They are prefixed (`docir_context`, not
  `context`) because the CLI's names are generic verbs that collide across
  servers in a client's tool list. Renaming one breaks saved prompts, so the
  mapping is spelled out in the test rather than derived.
- **This is not the read-path improvement.** MCP changes who can reach docir,
  not what they get: retrieval is still document-level, with no chunking and no
  reranking. Those remain open — gaps 2 and 3 of `ref-a6db21f52427`.
- **The lazy import in `cmds.py` is now load-bearing.** With fastmcp a default
  dependency, nothing but that deferred import keeps its ~0.3s off the read path
  every other command runs. Hoisting it to the top of the module would be
  invisible in the tests and would slow every `docir get` in the project.
- **`docir` has no extras left.** `pip install docir` is the whole product;
  `docir[embeddings]` and `docir[mcp]` both resolve to it and warn.
