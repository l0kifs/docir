---
code:
- src/docir/entry_points/cli/**
- benchmarks/latency.py
created: '2026-08-14'
description: 'Startup still dominates after the SQLAlchemy fix: ~0.49s of a 0.53s
  warm-daemon read is process start and imports. What remains is pydantic-settings
  (~97ms) and docir''s own 130 modules.'
id: issue-9509f9fa3631
owner: maintainer
related:
- arch-1cfb1b212237
- adr-ab9c454b760c
status: open
tags:
- cli
- daemon
- material
title: Interpreter startup, not retrieval, dominates read latency
type: issue
updated: '2026-08-16'
---

## What was measured

`benchmarks/latency.py` (new) times whole `python -m docir` processes rather than
`dispatch()` calls, because the three daemon modes differ only in what a *process* has to
do before it can answer. It grows one store through 25 -> 100 -> 500 -> 2000 generated
documents and samples `context`, `search` and `get` in a warm daemon, a cold daemon and
`--no-daemon`, plus `docir version` as a floor: that command builds no container and opens
no store, so it prices starting Python and importing docir and nothing else.

2026-08-14, docir 0.13.1, Apple M1, `bge-small-en-v1.5`. p50 seconds.

## Numbers

| command | mode | 25 | 100 | 500 | 2000 |
|---|---|---|---|---|---|
| `context` | warm daemon | 0.86 | 0.87 | 1.23 | 1.42 |
| `context` | no daemon | 1.43 | 1.43 | 1.50 | 1.90 |
| `search` | warm daemon | 0.87 | 0.82 | 0.83 | 0.82 |
| `get` | warm daemon | 0.83 | 0.84 | 0.82 | 0.83 |
| `docir version` | floor | 0.87 | 0.82 | 0.85 | 0.73 |

Subtract the floor: a warm-daemon `get` or `search` is under 0.1s of work at every corpus
size, and flat from 25 to 2000 documents. The floor row wanders ~0.1s between runs, so
differences under ~0.15s are noise.

## Why it matters

The read path is already fast; the CLI's own import graph is what the agent waits for.
Any ranking or index work optimises the small half of the number. Two consequences worth
carrying into other decisions:

- The daemon's only measurable read-path win is the lazily-loaded embedding model on
  `context` (~0.5s, adr-ab9c454b760c). On `get` and `search` it is a wash — neither
  command loads a model in either mode.
- A cold daemon costs ~1.7s for a command that needs no model at all, because the spawn
  builds a container regardless. That is an investment the next command repays, not a
  fee, but it is why the first command after an idle shutdown or an upgrade feels slow.

## What to try

Profile first: `python -X importtime -m docir version` names the expensive imports. The
known candidates are Typer/rich at module scope in `entry_points/cli`, and anything the
CLI imports eagerly that only one command needs — `fastmcp` is already lazy in
`mcp/cmds.py` for exactly this reason, and that is the pattern to copy.

## What not to conclude

That the semantic scan is fine forever. `context` is the one command that grows with the
corpus, and it grows in *vectors* rather than documents (10 000 at 2 000 documents, since
every `##` section is embedded, adr-927aa43d9635): warm p50 moves 0.86 -> 1.42 across the
sweep. Past a few thousand documents that scan, not the startup cost, becomes the number
to attack.

## Profile — where the 0.8s goes (2026-08-14)

`python -X importtime -m docir version` loads **925 modules**. Attributing self-time to the
top-level package, the same three lead every run: `sqlalchemy` (145 modules, 156-419 ms),
`docir` itself (134 modules), `alembic` (50 modules, 47-240 ms), then `rich` + `pygments` +
`markdown_it` (150 modules together) and `pydantic`/`pydantic_settings`.

None of that is needed to print a version, and — the point — **none of it is needed to run a
command against a warm daemon**, where the CLI is a socket client. The chain that pulls it in
is module-scope: `cli/app.py` -> `cli/runner.py` -> `entry_points/composition.py`, which
imports `sqlalchemy` and the whole in-process object graph at line 18; `cli/rendering.py`
imports `rich.console`/`panel`/`table` at line 17.

Measured with the venv interpreter, minimum of 7 runs (the minimum is the stable statistic
here; medians on this laptop wander by 300 ms):

| what is imported | min |
|---|---|
| bare interpreter | 39 ms |
| `typer` only | 100 ms |
| `typer` + settings + transport + payload (a socket-only client) | 147 ms |
| the same, but with `rich` (today's `rendering`) | 339 ms |
| `docir.entry_points.cli.app` (today) | 952 ms |

So a daemon-mode client that imported only what it uses would start in ~150-340 ms against
~950 ms today. Two candidate changes, in order of return:

1. **`runner.py` should not import `composition` at module scope.** `Container`,
   `build_in_process_executor` and `peer_status` are needed only on the in-process path;
   moving them inside the functions that use them (types under `TYPE_CHECKING`, which
   already works — the module has `from __future__ import annotations`) keeps `sqlalchemy`
   and `alembic` out of every daemon-mode command.
2. **`rendering.py` should import `rich` inside the human-output path.** Captured stdout
   takes the JSON path, which needs `json` and `payload.trim` and nothing else; `rich` and
   its `pygments`/`markdown_it` dependencies cost ~190 ms that an agent never uses.

Neither changes behaviour, and `--no-daemon` still pays the full cost — correctly, since it
does build the container.

## Fixed: the SQLAlchemy chain (2026-08-14)

`entry_points/composition.py` now imports `platform.persistence.engine`,
`platform.persistence.sqlalchemy_uow` and `sqlalchemy.exc` **inside** the three functions that
construct an engine (`build_container`, the peer builder, `initialize_store`), with
`sqlalchemy.Engine` under `TYPE_CHECKING`. No public name moved, so `cli/runner.py` and
`cli/app.py` needed no change and every caller benefits.

`python -m docir version` loads **655 modules instead of 925**, and neither `sqlalchemy` nor
`alembic` is among them. `benchmarks/latency.py --sizes 25`, same machine, before -> after p50:

| command | mode | before | after |
|---|---|---|---|
| `docir version` | floor | 0.87 | **0.49** |
| `context` | warm daemon | 0.86 | **0.53** |
| `search` | warm daemon | 0.87 | **0.55** |
| `get` | warm daemon | 0.83 | **0.53** |
| `context` | cold daemon | 2.16 | 1.91 |
| `context` | no daemon | 1.43 | 1.39 |

A warm read is ~0.33s cheaper — about 38%. `--no-daemon` is unchanged, which is the check that
the change is correct rather than lucky: that mode does build a container, so it still pays for
SQLAlchemy, and only the modes that never needed it stopped paying.

## The `rich` half was measured and rejected

The obvious companion change — defer `rich` out of `cli/rendering.py`, since the JSON path never
renders a table — moves ~10ms. In a warm process `import docir.entry_points.cli.rendering` costs
about 2ms more than `docir.entry_points.payload` alone, and `typer` does not pull `rich` in on its
own (checked: zero rich modules after `from typer.main import get_command`), so there is no large
transitive graph hiding behind it. Against 30 call sites and the `conftest` console-width pinning
that would have to move to a `COLUMNS` env var, it is not worth the churn. Do not retry it without
a fresh measurement.

## What is left

The floor is now `pydantic` + `pydantic_settings` (~276ms, from `config/settings.py`, needed by
every command) and docir's own 130 modules (~190ms). Removing pydantic-settings from `Settings` is
a design change, not a lazy import, and it should be prototyped and measured before it is chosen.

## Candidate 1 was measured and rejected (2026-08-16)

Deferring `composition` out of `cli/runner.py` module scope moves nothing on its own, and
the reason is `cli/app.py`: it imports `composition` at module scope too, for `init` /
`schema validate` / `self upgrade`, and `DEFAULT_INIT_ID_STYLE` is a Typer parameter
default — evaluated at import, so no lazy import reaches it.

Both halves were applied together (the constant inlined to make the experiment run), then
reverted. Same machine and docir 0.13.1; the floor reproduced at 0.53 against the 0.49
recorded on 2026-08-14.

| measure | before | after |
|---|---|---|
| `import docir.entry_points.cli.app`, min of 9 | 416 ms | 375 ms |
| modules loaded by `docir version` | 657 | 646 |

`benchmarks/latency.py --sizes 25 --samples 15`, p50 seconds:

| command | mode | before | after |
|---|---|---|---|
| `context` | warm daemon | 0.515 | 0.551 |
| `search` | warm daemon | 0.538 | 0.568 |
| `get` | warm daemon | 0.536 | 0.561 |
| `version` | floor | 0.539 | 0.530 |

Every warm p50 moved *up*, inside the ~0.15s this benchmark already documents as noise.
The ~40 ms is real, and only visible at import scope.

## Why candidate 1 is spent

`composition`'s expensive imports are `documents.api`, `tags.api` and `agents.api` — and
`app.py` imports those *directly*, for its Typer defaults (`ID_STYLES`, `PROFILE_NAMES`,
`AGENT_NAMES`, `DEFAULT_TAG_PAGE`, `DEFAULT_CONTEXT_EXPAND`). Those are evaluated when the
command tree is built, so they cannot be deferred without moving the constants. Deferring
`composition` therefore drops ~10 modules, not a graph: the SQLAlchemy fix above already
took everything this candidate was pointing at, and what was left of it is docir's own
modules under a different name.

Keeping the change would also mean relocating `DEFAULT_INIT_ID_STYLE` out of
`composition` — a public name, so a `CONTRACT.md` change — to buy ~40 ms that no
end-to-end measurement can see. Same verdict and the same rule as the `rich` half: do not
retry without a fresh measurement.

This does not touch **What is left**: `pydantic-settings` and docir's own ~130 modules are
still the floor, and still the only remaining candidates.
