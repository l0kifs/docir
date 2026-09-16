---
code:
- src/docir/entry_points/mcp/cmds.py
code_baseline:
  src/docir/entry_points/mcp/cmds.py: ea3f85d64c83
created: '2026-09-16'
description: docir mcp serve dies in build_server when the schema will not load, so
  the client sees only a closed connection where the CLI prints the error that names
  the fix.
id: issue-2f07f83e6b84
owner: maintainer
related:
- adr-354a4270ecd8
- adr-36d6156ffab9
status: open
tags:
- cli
- integrity
title: An unloadable schema kills the MCP server with no message
type: issue
updated: '2026-09-16'
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

## What a fix has to decide

A server with no store cannot answer `docir_get`. So the question is whether it starts at all:

- Refuse to start, but on stderr with the message rather than a traceback — cheapest, and
  the client still only sees a closed connection.
- Start degraded: register the tools and have each return the store error, so an agent asking
  anything is told why instead of losing the connection.

The second is what makes the message reach the reader it was written for, and it is the one
that needs a decision about what a tool list means when nothing behind it works.
