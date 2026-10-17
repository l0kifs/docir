---
code:
- src/docir/modules/agents/application/service.py
- src/docir/entry_points/cli/self_cmds.py
code_baseline:
  src/docir/entry_points/cli/self_cmds.py: eccf98aff5ad
  src/docir/modules/agents/application/service.py: e15c7bed2d65
created: '2026-10-17'
description: Run by an older build — directly, or by self upgrade after a package
  step that did not move the version — agent update replaces newer generated files
  with older text and exits 0.
id: issue-af3f335688f4
owner: maintainer
related:
- issue-f0b537bde01a
- adr-3a2d5ee7bc84
- adr-a555ee6bc484
status: resolved
tags:
- agents
- release
title: An older docir's agent update overwrites skill files a newer build wrote, and
  calls it an update
type: issue
updated: '2026-10-17'
---

## What is wrong

`docir agent update` writes every generated file from the running build's templates, whatever
the file's stamp says. Run by an older docir in a repository whose skill a newer build wrote,
it replaces the newer text with the older one, reports `updated <newer> -> <older>` and exits 0.
`_write_skill` and `_write_pointer` read the existing stamp only to report it.

`docir self upgrade` reaches the same write whenever its package step does not move the
version — an environment docir does not own, or an installer that exits 0 on a pin
(issue-f0b537bde01a). The store half then runs on the build that was meant to be replaced,
and its `agent update` is that build's.

## How it showed

Upgrading this machine from 0.30.0: the uv tool was pinned to `==0.30.0`, `uv tool upgrade`
changed nothing, and `self upgrade` carried on and rewrote this repository's committed 0.30.2
skill files with 0.30.0's — 0.30.1's `--append-section` guidance gone, exit 0.

Reproduced in a scratch repository whose skill 0.30.2 installed, with 0.30.0 from `uvx`:
plain `agent update` and `self upgrade` each reported `claude updated 0.30.2 -> 0.30.0`,
exited 0, and left the entry point 20 lines shorter. A teammate on an older release running
either command in a shared repository does the same to files somebody else committed.

## What would fix it

A file stamped by a newer docir than the running one is **kept**, not written: a `kept` row
naming both versions, a stderr warning, exit 0. `--force` writes anyway, because a team pinned
below the stamp on purpose — the case issue-f0b537bde01a declines to second-guess — wants the
skill matched to its pin, and an intentional downgrade has to stay one flag away. An equal or
older stamp, and a file with no stamp, behave as today. Ordering is PEP 440, as the release
check's. The guard sits in the agents service, so `install`, `update` and `self upgrade` all
get it, and the stalled upgrade's carry-on becomes safe without changing it.

Rejected: stopping `self upgrade` when the package step stalls. It fixes one of the two paths,
and the store half is still worth running there — reindex and check describe the store either
way.

Residual risk: a pinned team keeps a newer skill describing flags its build rejects until
somebody passes `--force`. The failure is loud — the flag errors — and the `kept` row names
the cause.

## Resolution

`AgentSetupService._write` — the one place skills and the `AGENTS.md` pointer both pass
through — now reads the stamp before writing. A file stamped by a newer docir than the
running one is reported `kept`, with that version and a note naming `docir agent update
--force`, and nothing in it or its skill directory is written or swept; the CLI repeats the
note on stderr, for `agent install`, `agent update` and `self upgrade` alike. `--force` writes
it anyway. Ordering is PEP 440; an absent or unparseable stamp is written over as before.

Pinned at the service and through the CLI, and five re-injected bugs were each caught: the
guard removed, text comparison (`0.9.0` above `0.10.0`), `force` ignored, the warning
silenced, an unparseable stamp read as newer. In a scratch repository whose skill carried a
newer stamp, `agent update` and `self upgrade --no-package` kept it with exit 0, and `--force`
wrote this build's text.

Builds released before the fix still overwrite; the guard protects files from its release on.
