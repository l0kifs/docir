---
code:
- benchmarks/latency.py
- src/docir/entry_points/cli/**
- src/docir/entry_points/daemon/cmds.py
- tests/entry_points/test_cli_import_graph.py
code_baseline:
  benchmarks/latency.py: 492ab63bc432
  src/docir/entry_points/cli/**: 8b97a450d4c1
  src/docir/entry_points/daemon/cmds.py: 22bb79cde96e
  tests/entry_points/test_cli_import_graph.py: 6e2efd676827
created: '2026-08-14'
description: 'Startup, not retrieval, dominates a warm-daemon read: ~0.49s of docir
  version is process start, and with SQLAlchemy, the docs watcher and the site builder
  deferred, what is left is pydantic-settings and the documents.api graph.'
id: issue-9509f9fa3631
owner: maintainer
related:
- adr-ab9c454b760c
- adr-fe7c91f61f32
- arch-1cfb1b212237
revoked: '2026-10-17'
status: open
tags:
- cli
- daemon
- material
title: Interpreter startup, not retrieval, dominates read latency
type: issue
updated: '2026-10-17'
verified_code:
  benchmarks/latency.py: 492ab63bc432
  src/docir/entry_points/cli/**: 8b97a450d4c1
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

Profile first: `python -X importtime -m docir version` names the expensive imports, and
anything the CLI imports eagerly that only one command needs is the pattern to fix —
`fastmcp` in `mcp/cmds.py` was the first, and the watcher and the site builder followed.
Time a change with the interleaved A/B in `docs/playbooks/ab-time-a-startup-change.md`:
`benchmarks/latency.py` cannot resolve anything under ~0.15s. Two candidates were measured
and reverted, and [[ref-71c621c5532f]] has the numbers and the reasons — read it before retrying one.

## What not to conclude

That the semantic scan is fine forever. `context` is the one command that grows with the
corpus, and it grows in *vectors* rather than documents (10 000 at 2 000 documents, since
every `##` section is embedded, adr-927aa43d9635): warm p50 moved 0.86 -> 1.42 across the
sweep. `Embedding.cosine_similarity` now runs on `math.sumprod` rather than generator sums,
which cut the scan over this repo's 1,947 vectors from ~60ms to ~7ms and a warm `context`
dispatch from 94ms to 46ms. The scan is still linear, only eight times cheaper per vector:
past tens of thousands of vectors it, not the startup cost, is the number to attack.

## Fixed: the SQLAlchemy chain

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

## Fixed: the watcher and site-builder imports

`daemon/cmds.py` imported `DocsWatcher` at module scope, and with it `watchfiles` and
`anyio`; `cli/app.py` imported `publishing.api`, and with it `markdown_it` and the page
templates. Only `daemon serve` and `build` use them, so both imports moved inside those
functions. `docir version` loads 570 modules instead of 704, and
`tests/entry_points/test_cli_import_graph.py` fails if any of the four packages reaches the
client again (checked by re-hoisting each import).

Interleaved A/B against a HEAD worktree, same interpreter, 25 pairs, p50 (min):
`docir version` 0.574s (0.517) -> 0.486s (0.389); `import docir.entry_points.cli.app`
0.553s (0.484) -> 0.459s (0.392). `benchmarks/latency.py --sizes 25 --samples 9` could not
see it: its warm rows moved +0.03-0.05s and its floor -0.11s, inside its ~0.15s noise.

## Batching removes it four times out of five

The floor is unchanged — this does not fix the issue, it stops paying it N
times. `docir get` now takes several ids (and `<id>#<heading>` addresses) in one
process, so an agent reading five documents pays one interpreter instead of
five.

`benchmarks/latency.py` grew the pair that prices it: `get x5` is five separate
`get` processes, `get 5in1` is the same five bodies in one command. Same
machine, 25 documents, p50 seconds, 9 warm samples.

| command | warm daemon | cold daemon | no daemon |
|---|---|---|---|
| `get` (one document) | 0.459 | 1.378 | 0.805 |
| `get x5` | 2.506 | 3.133 | 4.248 |
| `get 5in1` | 0.508 | 1.320 | 0.872 |
| `version` (floor) | 0.522 | — | — |

Warm, five bodies go from 2.506s to 0.508s — **4.9x**, and 0.508 is the floor
row, which says the five reads themselves are free at this corpus size. With no
daemon it is the same 4.9x from a worse start. The cold row gains least (2.4x)
because a cold sample pays one spawn per process and the batch only removes
four of five.

The saving is four floors, so it grows with the number of documents read and is
independent of how large they are. That also bounds it: it is worth nothing to a
caller reading one document, which is why `get` still answers a single `doc_id`
with the document object rather than an envelope.

Over MCP the process cost is already amortised — the server is long-lived — and
the win is a different one: five tool calls are five model turns, and one is
one.

## What is left

The floor is `pydantic` + `pydantic_settings` (~65ms self time, from `config/settings.py`,
needed by every command) and the `documents.api` graph (~87ms cumulative), which the client
reaches through `cli/app.py`'s Typer defaults — the chain
[[ref-71c621c5532f#Why candidate 1 is spent]] traces. A socket-only client (`typer` + settings +
transport) imports in ~0.16s against ~0.46s for `cli.app`, interpreter included: that gap is
what is left to win.

Both remaining candidates are design changes, not lazy imports: removing pydantic-settings
from `Settings`, or moving the Typer-default constants out of `documents.api`, `tags.api` and
`agents.api` so the command tree builds without importing the aggregates — a `CONTRACT.md`
change in each module. Prototype either and measure it before choosing it.
