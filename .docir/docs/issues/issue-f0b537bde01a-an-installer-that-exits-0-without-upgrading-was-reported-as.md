---
code:
- src/docir/modules/release/**
- src/docir/entry_points/cli/self_cmds.py
code_baseline:
  src/docir/entry_points/cli/self_cmds.py: eccf98aff5ad
  src/docir/modules/release/**: 2a1da03eeaad
created: '2026-09-24'
description: Why a pinned uv-tool receipt made `docir self upgrade` claim the newest
  build, and what docir now says instead of guessing.
id: issue-f0b537bde01a
owner: maintainer
related:
- adr-a555ee6bc484
- adr-31aa7aa60d11
- adr-bea870d0b666
status: resolved
tags:
- cli
- release
- agents
title: An installer that exits 0 without upgrading was reported as already current
type: issue
updated: '2026-09-24'
---

## Symptom

`docir self upgrade` printed `package 0.28.0 (already the newest build)` on an
installation that was not the newest build. `docir self status` on that same
install, minutes apart, reported `latest: 0.29.0, update_available: true`.

## Cause

The install had been created with an exact pin, which `uv tool` records:

```toml
requirements = [{ name = "docir", specifier = "==0.28.0" }]
```

`uv tool upgrade docir` resolves within that recorded requirement, so there was
one candidate and nothing to do. It exited **0** — and it printed the cause and
the remedy:

```
Nothing to upgrade

hint: `docir` is pinned to `0.28.0` (installed with an exact version pin);
      reinstall with `uv tool install docir@latest` to upgrade to a new version.
```

docir captured that text and discarded it: `_upgrade_the_package_then_restart`
printed `outcome.message` only when the installer declined to run or failed. On
exit 0 it re-executed into an environment it had not checked, and
`render_upgrade` then reported "already the newest build" from
`upgraded_from == __version__` alone, without reference to what is published.

This is not specific to uv. A pip held back by a constraint file exits 0 and
says nothing at all — measured — so the general condition is "the installer
succeeded and the version did not move", of which a pin is one cause.

## Resolution

`upgrade_package()` reads the version the environment holds after a successful
run, through a new `VersionProbe` port, and `UpgradeOutcome.version_moved`
carries the answer three-valued: `None` is *could not tell* and falls through to
the behaviour every release before this one had.

When it is `False`, docir does not re-execute — there is nothing to hand off to —
and reports three things: that the version did not move and which release is
being missed, the installer's own output verbatim, and one instruction that holds
whatever the cause (`docir self status` names the method; then `self upgrade
--no-package`). The store half still runs, so the command is not a failure.

docir does **not** diagnose the cause and does **not** repair the installation.
Rewriting a recorded requirement would reverse a declaration whose reason docir
cannot see — a team pinning docir so every member's build matches the store
format their committed `.docir/` was written by is the case adr-ab4598c6f707 is
about — and `uv tool install docir@latest --force` is the wrong repair for four
of the five requirement shapes a receipt can hold (editable, git, plain, pinned).
