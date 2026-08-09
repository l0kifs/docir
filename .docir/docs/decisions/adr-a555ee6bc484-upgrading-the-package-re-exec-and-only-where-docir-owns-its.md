---
code:
- src/docir/modules/release/**
- src/docir/entry_points/daemon/release_watch.py
created: '2026-08-09'
description: How docir self upgrade installs a new docir, which installs it refuses
  to touch, and why the release check is opt-in.
id: adr-a555ee6bc484
owner: maintainer
related:
- kind: refines
  to: adr-31aa7aa60d11
- adr-3a2d5ee7bc84
status: accepted
tags:
- cli
- agents
- daemon
title: 'Upgrading the package: re-exec, and only where docir owns its environment'
type: decision
updated: '2026-08-09'
---

## Context

adr-31aa7aa60d11 built `docir self upgrade` and left the package install out of
it, saying the omission was a separate decision: the process running the
installer is the code being replaced, so every step after that call is the old
build's work — starting with the rebuild that stamps which version built the
index. That left the one thing an agent cannot do for itself. It can run every
docir command; it cannot know that a newer docir exists, and it cannot install it
without being told the right incantation for an environment it did not create.

## Decision

**The package step runs first and then re-executes docir.** `os.execv` replaces
the process with `python -m docir` from the upgraded environment, carrying a
hidden `--upgraded-from` so the report still names the version that was there.
`-m docir` rather than `sys.argv[0]`: the console script is a generated shebang
wrapper, and the interpreter is the one thing that certainly belongs to the
environment that was just upgraded. The flag is also the loop guard — a process
that already carries it never runs the installer again.

**An installer runs only where docir owns its environment.** A `uv tool` install
(`uv-receipt.toml` at the root of the venv), a pipx install
(`pipx_metadata.json`), or a virtualenv (`pyvenv.cfg`, upgraded through
`sys.executable -m pip`). Every other case returns no command and a reason:

- a **checkout or path install** (PEP 610 `direct_url.json` naming a `file:` URL)
  belongs to a project whose lockfile decides its version — upgrading it from
  underneath would leave that lockfile describing something that is no longer
  installed;
- an **ephemeral `uvx` environment** (under uv's cache) has nothing to upgrade;
  it is resolved per run and discarded;
- an **unrecognised layout** gets no guess at all. Running the wrong installer
  against the wrong environment is worse than doing nothing, and "nothing
  happened, here is why" is a complete answer.

Every marker read is one an installer wrote for its own bookkeeping, so this is
reading a fact rather than inferring one.

**A failed install stops the command.** The local steps would otherwise resync a
store against a docir the user believes they no longer have.

**The release check is opt-in, daily, and cached.** `docir self status` reads the
last answer and reaches PyPI only on `--refresh`, skipping even that when the
answer is already from today. `DOCIR_UPDATE_CHECK=1` puts the fetch in the daemon
— the one process nobody is waiting on — and lets every command print a one-line
stderr notice from the cached file. Off by default on the argument
`DOCIR_SCHEMA_NOTICE` already makes about repeated notices, and one more: this is
the only network call docir makes in its life, and a documentation tool that
phones home unasked is not one people keep installed.

**`latest` is three-valued.** A version, or `None` meaning nobody has checked or
the check failed — never "up to date". Every network failure collapses to `None`,
so being offline is not news about docir.

**Version ordering is PEP 440, from `packaging`.** Hand-rolling it is how `0.9.0`
ends up newer than `0.10.0`, and how a release candidate becomes unorderable. The
dependency already arrived transitively; declaring it is the rule this project
applied to `watchfiles` and `markdown-it-py`.

## Consequences

- A new leaf module, `release` — it looks at the *installation*, owns no index or
  database state, and depends only on `platform.clock`. Same shape as `agents`
  (adr-3a2d5ee7bc84), and like it, in-process rather than through the dispatcher.
- One more file in the store: `release-check.json`, the last answer and its date.
  Outside the index, because it is a fact about the installation and `reindex`
  must not be able to lose it.
- The test suite is structurally safe from self-upgrading: it runs from a
  checkout, which detects as `project`, and a test asserts exactly that.
- Nothing about the release check is exposed over MCP. An MCP server *is* a docir
  process a client is talking to, and the command that replaces it is not a tool
  it should be able to call.
