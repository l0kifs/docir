---
code:
- src/docir/entry_points/mcp/cmds.py
- src/docir/entry_points/mcp/server.py
code_baseline:
  src/docir/entry_points/mcp/cmds.py: d1b6879eb575
  src/docir/entry_points/mcp/server.py: f8a743539681
created: '2026-09-16'
description: docir mcp serve dies in build_server when the schema will not load, so
  the client sees only a closed connection where the CLI prints the error that names
  the fix.
id: issue-2f07f83e6b84
owner: maintainer
related:
- adr-354a4270ecd8
- adr-36d6156ffab9
status: resolved
tags:
- cli
- integrity
title: An unloadable schema kills the MCP server with no message
type: issue
updated: '2026-09-22'
verified: '2026-09-22'
verified_code:
  src/docir/entry_points/mcp/cmds.py: d1b6879eb575
  src/docir/entry_points/mcp/server.py: f8a743539681
verified_content: 653e1ff45611
---

Every refusal docir writes for a schema it cannot load is worded for a reader. Over MCP, no
reader gets it: `docir mcp serve` builds its executor at startup, `load_schema` raises, the
exception escapes `build_server`, and the process dies. The client sees `Connection closed`.

## Measured, two ways in

```
# a schema this build cannot validate
DOCIR_HOME=<store> python -m docir mcp serve   -> traceback, client: "Connection closed"
# a schema above this build's store format (adr-36d6156ffab9)
DOCIR_HOME=<store> python -m docir mcp serve   -> traceback, client: "Connection closed"
```

The CLI answers both with the sentence the error was written to carry — `runner.py` maps a
`DocirError` onto an exit code and prints it. The MCP entry point has no equivalent, so the
one transport where the reader is definitely an agent is the one that says nothing.

## Why it is not the floor's problem

The floor made a second way in; it did not make the hole. Any unloadable schema has always
done this, and [[adr-354a4270ecd8]] made every MCP tool one `Request` through the dispatcher
precisely so the two transports could not drift — but the *startup* path was never part of
that, because it runs before any request exists.

## What shipped

`build_server` catches the store error, builds the surface anyway behind an executor that
answers every command with it, and puts the same sentence in front of the server's
instructions — which a client reads at the handshake, before it has written a plan around
tools that cannot work. All 23 tools still list, so the reader can tell "this store cannot be
opened" from "docir does not do that here".

`_UnavailableExecutor` rather than a special case inside each tool, so the error travels the
path a dispatcher error already travels: `_Gateway` turns a `DocirError` into a `ToolError`.
One implementation, the rule [[adr-354a4270ecd8]] exists to keep.

Driving the real server found two defects reading the code did not: a closure over the
`except` variable, which Python unbinds, so `docir_schema` raised `NameError` instead of the
store error; and a top-level `fastmcp` import, which broke the guard that importing the CLI
must not pay fastmcp's startup ([[issue-9509f9fa3631]]).

The daemon path fails differently — a timeout naming the wrong cause rather than a server that
dies — and is [[issue-1e310cf366b8]].
