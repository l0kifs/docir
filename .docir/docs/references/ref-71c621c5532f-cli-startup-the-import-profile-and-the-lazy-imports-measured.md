---
code:
- src/docir/entry_points/cli/**
code_baseline:
  src/docir/entry_points/cli/**: 9b5043ef9da1
created: '2026-10-17'
description: Where the CLI's import time went on docir 0.13.1, and why deferring rich
  in the renderer and composition in the runner were both reverted — read before retrying
  either.
id: ref-71c621c5532f
owner: maintainer
related:
- issue-9509f9fa3631
status: active
tags:
- cli
title: 'CLI startup: the import profile, and the lazy imports measured and rejected'
type: reference
updated: '2026-10-17'
---

The measurements behind [[issue-9509f9fa3631]]'s fixes and refusals: the import profile taken
on docir 0.13.1 (2026-08-14), before `sqlalchemy` left the client, and the two lazy-import
candidates that were applied, measured and reverted. The issue holds the current floor; this
holds why the obvious next moves were not made. Re-measure before retrying one —
`docs/playbooks/ab-time-a-startup-change.md` is the instrument for a change this size.

## Profile — where the 0.8s goes

`python -X importtime -m docir version` loads **925 modules**. Attributing self-time to the
top-level package, the same three lead every run: `sqlalchemy` (145 modules, 156-419 ms),
`docir` itself (134 modules), `alembic` (50 modules, 47-240 ms), then `rich` + `pygments` +
`markdown_it` (150 modules together) and `pydantic`/`pydantic_settings`.

None of that is needed to print a version, and — the point — **none of it is needed to run a
command against a warm daemon**, where the CLI is a socket client. The chain that pulls it in
is module-scope: `cli/app.py` -> `cli/runner.py` -> `entry_points/composition.py`, which
imports `sqlalchemy` and the whole in-process object graph at line 18; `cli/rendering.py`
imports `rich.console`/`panel`/`table` at line 17.

## Profile — what a socket-only client would cost

Measured with the venv interpreter, minimum of 7 runs (the minimum is the stable statistic
here; medians on this laptop wander by 300 ms):

| what is imported | min |
|---|---|
| bare interpreter | 39 ms |
| `typer` only | 100 ms |
| `typer` + settings + transport + payload (a socket-only client) | 147 ms |
| the same, but with `rich` (0.13.1's `rendering`) | 339 ms |
| `docir.entry_points.cli.app` (0.13.1) | 952 ms |

So a daemon-mode client that imported only what it uses would start in ~150-340 ms against
~950 ms at 0.13.1.

## The two candidates the profile named

In order of return:

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

## The `rich` half was measured and rejected

The obvious companion change — defer `rich` out of `cli/rendering.py`, since the JSON path never
renders a table — moves ~10ms. In a warm process `import docir.entry_points.cli.rendering` costs
about 2ms more than `docir.entry_points.payload` alone, and `typer` does not pull `rich` in on its
own (checked: zero rich modules after `from typer.main import get_command`), so there is no large
transitive graph hiding behind it. Against 30 call sites and the `conftest` console-width pinning
that would have to move to a `COLUMNS` env var, it is not worth the churn. Do not retry it without
a fresh measurement.

## Candidate 1 was measured and rejected

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
`composition` therefore drops ~10 modules, not a graph: the SQLAlchemy fix
([[issue-9509f9fa3631#Fixed: the SQLAlchemy chain]]) already took everything this candidate was pointing at, and what was left of it is docir's own
modules under a different name.

Keeping the change would also mean relocating `DEFAULT_INIT_ID_STYLE` out of
`composition` — a public name, so a `CONTRACT.md` change — to buy ~40 ms that no
end-to-end measurement can see. Same verdict and the same rule as the `rich` half: do not
retry without a fresh measurement.

This does not touch what is left of the floor, which
[[issue-9509f9fa3631#What is left]] tracks.
