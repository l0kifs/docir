---
created: '2026-08-05'
description: A cycle is only meaningful for relation kinds that assert direction;
  counting the default symmetric kind made 120 correct edges unrecordable in this
  store.
id: issue-44875a5a6ca6
owner: maintainer
related:
- adr-234b956a48d8
- arch-0a3c2d6d54a6
- adr-599055502f0e
- issue-9cb85759076d
status: resolved
tags:
- integrity
- material
title: The cycle check counts symmetric `relates_to` edges, so a mutual reference
  is a permanent warning
type: issue
updated: '2026-08-05'
---

**Class:** incorrect · **Severity:** material
**Flow:** arch-0a3c2d6d54a6 · **Step:** `docir check`

## Finding

`_find_cycles` (`graph_checks.py:285-288`) builds its adjacency from **every** relation,
regardless of kind. `relates_to` — the default kind, and the one a bare id in `related:`
means — asserts no direction: "A relates to B" and "B relates to A" are the same claim.
Two documents that each name the other therefore form a two-node cycle that `check`
reports, permanently, on a corpus that is modelled correctly.

This is the same defect class the layering check already fixed. `_DEPENDENCY_KINDS` exists
precisely because reading every kind as a dependency made the most natural thing a user
can model into a warning no edit could silence. The cycle check never got the same
treatment.

## What happens today

OBSERVED, at scale, in this store. Converting the corpus's prose cross-references into
typed edges proposed 260 new `relates_to` edges. Adding all of them takes `docir check`
from 0 findings to **127 cycles** — every one of them a mutually-referencing pair that is
correctly modelled. Restricting the pass to a cycle-free subset was the only way to keep
`check` usable, and it dropped **120 of the 260 edges**: a flow document may no longer
link the gaps found in it, because each of those gaps already links back to the flow.

## Impact

The graph is the feature that distinguishes docir from a folder of files, and this makes
half of it unrecordable. The alternative — record the edges and accept 127 warnings —
teaches people to ignore `check` output, which is where the duplicate-id detection lives.
That is the failure mode `check --strict`'s severity split was introduced to end.

## Proposed direction

Give `_find_cycles` its own kind allowlist, as the layering check has. A cycle is only
meaningful for kinds that assert *direction* — `supersedes`, `depends_on`, `refines`,
`implements`. `relates_to` and `contradicts` are symmetric and should not contribute
edges to the cycle graph at all. Keep the constant separate from
`_DEPENDENCY_KINDS`: they answer different questions and have already diverged once.

## Resolution

FIXED. `_find_cycles` now builds its adjacency from `_DIRECTED_KINDS`
(`supersedes`, `depends_on`, `refines`, `implements`) only. `relates_to` and
`contradicts` are symmetric and contribute no edge, so a mutually-referencing
pair is no longer a finding.

One exception, found by a test rather than by reasoning: a **self**-edge is
reported whatever its kind. Symmetry is what makes a mutual pair legitimate and
it is exactly what makes "A relates to A" empty, so the narrowing had to stop
short of it — `check` is the only thing that sees a self-edge a merge or a
hand-edit put on disk (issue-2ebfc018f29a). The first version of this fix
silently dropped that detection and
`test_a_self_edge_already_on_disk_is_still_reported` caught it.

The 101 edges the old rule had blocked were added in the same pass: every
document that cites another by id in its prose now carries the edge. `docir
check` reports nothing, and no `cycle` finding was traded for them.
