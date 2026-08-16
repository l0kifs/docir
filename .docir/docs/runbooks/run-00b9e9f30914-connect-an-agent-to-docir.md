---
created: '2026-08-16'
description: The two transports an agent can use — the installed CLI skill or the
  bundled MCP server — and why both answer identically.
id: run-00b9e9f30914
owner: maintainer
related:
- adr-354a4270ecd8
- adr-3a2d5ee7bc84
status: active
tags:
- agents
- cli
title: Connect an agent to docir
type: runbook
updated: '2026-08-16'
---

Some agents run shell commands; some only call MCP tools. docir supports both, and the
choice is about your client rather than about capability — the two expose the same
vocabulary and cannot answer differently.

## The CLI path: install the skill

For an agent that has a shell, install the instructions once per repository:

```bash
docir agent install                          # a Claude skill, plus an AGENTS.md block linking it
docir agent install --agent claude-writing   # add the document-writing rules
docir agent install --agent agents           # link the skills from AGENTS.md
docir agent update                           # refresh after upgrading docir
```

The generated files carry a version stamp, so `update` reports the transition. An
`AGENTS.md` docir did not write is never rewritten — only docir's own marker block is.

## The MCP path: one command

For a client that speaks only MCP, the server ships inside docir. There is no extra to
install, because an agent that cannot run shell commands could not install one:

```bash
claude mcp add docir -- docir mcp serve
```

`docir mcp serve` speaks stdio, which is what an MCP client spawns. `--transport http`
serves over HTTP instead, with `--host` and `--port` to bind it. `uvx docir mcp serve`
runs the server without installing anything at all.

## The tools are the commands

Every tool is one request through the same dispatcher the CLI crosses, so a tool and its
command are the same code path. The names are prefixed — `docir_context`, `docir_get`,
`docir_add` — because the CLI's verbs are generic and would collide in a client's tool
list.

There is one tool per command, plus `docir_schema` for the thing an agent needs that is
not a command. Results are trimmed exactly as the piped CLI output is, and reads return
the same body-less skeletons.

## Choosing between them

Install the skill when the agent has a shell: it teaches the whole workflow, including
the parts that are judgement rather than invocation.

Reach for MCP when the client has no shell, or when you want docir available without the
agent learning a CLI. Running both is fine — they are the same store through the same
dispatcher, and neither knows the other exists.
