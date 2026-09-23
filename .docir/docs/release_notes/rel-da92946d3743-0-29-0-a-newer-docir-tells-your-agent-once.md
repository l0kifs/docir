---
created: '2026-09-23'
description: The release check moved out of one person's shell and into the store,
  and stopped naming a command four of six installations cannot run.
id: rel-da92946d3743
related:
- adr-bea870d0b666
- adr-a555ee6bc484
- adr-31aa7aa60d11
- adr-ab4598c6f707
status: published
tags: []
title: 0.29.0 — a newer docir tells your agent, once
type: release_note
updated: '2026-09-23'
---

## 🎯 The release

**A newer docir tells your agent, once — and never tells it something it cannot do.**

The release check has existed since 0.12.0 and was off behind an environment variable, which
is a setting in one person's shell. The reader it was built for is an agent, and it never saw
it. This release moves the decision into the store, where a team takes it once.

### A store now answers the question

`docir init` writes a committed `config.yaml` beside `docs-schema.yaml`:

```yaml
update_check: true
```

Creating a store is the act that opts in — deliberate, taken once, and inherited by everyone
who clones the repo. A machine that never created a store and never set the variable still
never contacts PyPI. Existing stores gain the file from `docir self upgrade`, which appends to
it the way it appends to `.gitignore`: a key already present is an answer somebody gave, so a
store that set `false` keeps it.

`DOCIR_UPDATE_CHECK=0` turns it off for one shell, `=1` on. A run with `CI` set never checks —
an agent that follows an upgrade instruction inside a job makes that job's docir version depend
on the day it ran.

### It says nothing it cannot back

The notice used to name `docir self upgrade` to every installation. That command's package step
declines for two of the six kinds docir tells apart: an ephemeral `uvx` run has nothing to
upgrade, and a `project` install is docir as a dependency of the tree you are working in — what
an editable checkout and every lockfile-managed project detect as.

- a `project` install is told **nothing**
- an install with no upgrade command carries its own explanation instead — `uvx docir@latest`,
  or your lockfile
- an install docir owns is told to run `docir self upgrade` **between tasks rather than during
  one**, because the command replaces the running process, respawns the daemon and rebuilds the
  index

It is announced at most once per release per day per store. `docir self status` is still the
unthrottled answer for a reader who is asking rather than being told:

```bash
docir self status --refresh
```

### MCP hears it too

Over MCP the notice arrives in the server's instructions, at the handshake — the one place an
agent with no stderr will read it, at the one cadence that does not spend the context budget
that body-less skeletons exist to protect. `--json` is unchanged: `docir query`, `docir search`
and `docir context` emit a bare array, and an envelope around them would break every consumer
to deliver a courtesy.

## 🎯 Also in this release

- **`docir_doctor` gives an MCP client the environment it is running in** — the daemon, the
  peers a read is skipping, the model in force, the thread cap.
- **`DOCIR_EMBED_THREADS` caps how many cores the embedding model may take** (GitHub #23).
- **`docir check --against main` reports id collisions before the merge** (GitHub #22).

## 🐛 Bug fixes

- The established file keeps a duplicated id, decided by git history (GitHub #30).
- An id more than one file claims is refused, `--force` included (GitHub #29).
- A governed code glob is never silently unwatched (GitHub #26).

## 🔗 Full changelog

See [CHANGELOG.md](https://github.com/l0kifs/docir/blob/v0.29.0/CHANGELOG.md)
