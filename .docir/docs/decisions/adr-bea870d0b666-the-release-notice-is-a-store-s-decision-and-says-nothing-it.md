---
code:
- src/docir/modules/release/**
- src/docir/config/settings.py
- src/docir/entry_points/cli/runner.py
code_baseline:
  src/docir/config/settings.py: 0efce1767374
  src/docir/entry_points/cli/runner.py: 8363b6c5539a
  src/docir/modules/release/**: 1c63497956b5
created: '2026-09-23'
description: Why the ambient update notice is opted into by `docir init` rather than
  a shell, what it refuses to tell a checkout, and where MCP carries it.
id: adr-bea870d0b666
owner: maintainer
related:
- kind: refines
  to: adr-a555ee6bc484
- adr-31aa7aa60d11
- adr-ab4598c6f707
- adr-36d6156ffab9
status: accepted
tags:
- agents
- cli
- release
title: The release notice is a store's decision, and says nothing it cannot act on
type: decision
updated: '2026-09-23'
verified: '2026-09-23'
verified_code:
  src/docir/config/settings.py: 0efce1767374
  src/docir/entry_points/cli/runner.py: 8363b6c5539a
  src/docir/modules/release/**: 1c63497956b5
verified_content: ddfa0b338582
---

## Context

adr-a555ee6bc484 built the release check and left it off, on three arguments. Two
still hold and one was aimed at the wrong reader.

The two that hold: this is the only network call docir makes in its life, and a
documentation tool that phones home unasked is not one people keep installed. The
third was that a notice repeating on every command until someone acts on it stops
being read — the argument `DOCIR_SCHEMA_NOTICE` settles one field over.

That third one describes a person at a prompt. docir's reader is an agent, and an
agent does not learn to skip a line; it follows it. So the same notice that a
person tunes out is one an agent will act on — including in the middle of
something else, and including where the command it names cannot run.

Which is the defect the feature actually had. The notice said `run docir self
upgrade` to every installation. The package step of that command declines for two
of the six kinds `Installation` distinguishes: an ephemeral `uvx` environment has
nothing to upgrade, and a `project` install is docir as a dependency of the tree
being worked in. `project` is what an editable checkout detects as — docir's own
repository, on the day it publishes the release the notice would name — and what
every lockfile-managed project detects as. Four of the six cells were wrong.

The other half of the gap: an opt-in that lives in one person's shell reaches one
person's shell. A store is committed and read by a whole team, and the MCP
transport — where an agent has no stderr to read — carried nothing at all.

## Decision

**The opt-in is recorded in the store, and `docir init` writes it.** A new
committed `config.yaml` beside `docs-schema.yaml`, holding `update_check: true`.
Creating a store is the act that opts in: deliberate, taken once, and inherited
by everyone who clones the repo. Nobody who never ran `docir init` is contacted,
so the promise in SECURITY.md survives — it now names this file as well as the
variable.

**A new file, never a new key in an existing one.** A store is read by whatever
docir each teammate installed (adr-ab4598c6f707), and a build that has never
heard of `config.yaml` cannot fail on it. A key added to `stores.yaml` is exactly
how 0.20.0 came to refuse every read of a store a later build wrote.

**Precedence is environment, then CI, then the store.** `DOCIR_UPDATE_CHECK` set
to anything decides, in both directions — it is how one person opts out of a
committed decision, and how one opts into a CI run that would otherwise be
silent. `CI` being set forces it off: a build server cannot act on the notice,
and an agent that acts on it there makes the job's docir version depend on the
day it ran.

**An installation that cannot act on the notice is not given one.** `notice_for`
is the decision table the single line used to be. A `project` install gets
nothing. An installation with an `upgrade_command` is told to run `docir self
upgrade`; one without carries its own `explanation`, which already names the
thing that does work (`uvx docir@latest`, or the lockfile).

**The notice names the moment, not just the command.** `self upgrade` replaces
the running process, stops and respawns a daemon whose build stamp no longer
matches, and rebuilds the index. Between tasks that is right; during one it means
the remaining steps run on a build nothing verified. The line says so, because an
agent has no other way to know.

**It is announced once per version per day per store.** `release-check.json`
gains `announced` and `announced_on` beside the fetched answer, so the file is
now read-modify-write from both sides — the daemon fetches, the CLI announces.
`docir self status` stays unthrottled: it is the answer for a reader who is
asking rather than being told.

**MCP carries it in the server's instructions.** Read once, at the handshake,
which is the cadence the notice wants. Not a tool result: three of those answer
with a bare JSON array that has nowhere to put a key, and a line appended to
every result would spend the context budget that body-less skeletons exist to
protect.

**Nothing fetches outside the daemon.** A CLI-side background refresh was
considered and does not work: a `docir query` process answers and exits in
0.4–0.7s, PyPI replies in 0.4–0.5s, and a `daemon=True` thread is killed at
interpreter exit — so the cache would never be written and every command would
pay a TLS handshake for nothing. With `--no-daemon` and no daemon ever run, the
notice is simply silent, which is the same rule `latest` already follows: absent
means unknown.

## Consequences

- One more committed file per store. `docir self upgrade` tops it up the way it
  tops up `.gitignore`, and both **append and never rewrite**: a key already
  present is an answer somebody gave, whatever its value, so an opt-out survives
  the upgrade that would otherwise reverse it.
- `--json` is unchanged. The notice stays on stderr for the CLI, because
  `query`, `search` and `context` emit a bare array and an envelope around them
  would break every consumer and every installed build to deliver a courtesy.
- A long-lived MCP server started before a release ships does not learn about it;
  the next client session does, and `docir_doctor` answers on demand.
- docir's own repository is silent by construction, so this feature cannot be
  exercised from a checkout. The tests inject the installation rather than
  detecting it, and a guard asserts that a `project` install is told nothing.
