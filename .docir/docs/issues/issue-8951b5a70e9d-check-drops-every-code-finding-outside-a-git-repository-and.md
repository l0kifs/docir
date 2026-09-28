---
code:
- src/docir/modules/documents/application/services/maintenance_service.py
- src/docir/modules/documents/domain/services/checks/verification_rules.py
code_baseline:
  src/docir/modules/documents/application/services/maintenance_service.py: 674a90c913a0
  src/docir/modules/documents/domain/services/checks/verification_rules.py: 91bee7b137da
created: '2026-09-28'
description: With no repository above the store, docir check skips unmatched-code,
  code-unwatched, code-changed and code-drifted without a word, even when documents
  declare code globs.
id: issue-8951b5a70e9d
owner: maintainer
related:
- adr-1cccd77cb023
- adr-49bb8cc48938
status: resolved
tags:
- integrity
- cli
title: check drops every code finding outside a git repository and says nothing, so
  the silence reads as clean
type: issue
updated: '2026-09-28'
---

## Problem

`docir check` resolves `code:` globs against the git repository above the store
(`Settings.code_root`). When there is none, `MaintenanceService` passes `None` for
both code inputs and four findings go silent together: `unmatched-code`,
`code-unwatched`, `code-changed` and `code-drifted`. Nothing in the output says
so — no finding, no field, and `docir doctor` does not report `code_root`.

That is the right call for the plain global `~/.docir`, where nobody declares
`code:`. It is the wrong one for a store whose documents *do* declare globs: an
empty code section there reads exactly like a tree where nothing moved.

## Reproduction

Copy this repository's store out of the repository and reindex it:

```bash
cp -R .docir /tmp/store-copy/.docir && cd /tmp/store-copy
DOCIR_NO_DAEMON=1 docir reindex
docir check | jq -r '.[].kind' | sort | uniq -c
```

In place, `check` reports 88 `code-changed`/`code-drifted` findings on 259
documents. The copy reports none of them and nothing in their place; only
`code-unverified`, which needs no tree, survives. Measured 2026-09-28 by
`benchmarks/agent_tokens.py`, whose audit runs on exactly such copies.

## Why silence is the defect

adr-1cccd77cb023 already decided this shape for the index: `check` refuses to
report a verdict it could not reach, and `empty-index` is how it says so. A
skipped code section is the same verdict at smaller scale — `check --strict` and
an agent reading the findings both see a clean store.

It now matters more. The packaged skill tells agents that `check`'s findings are
the answer for the kinds it reports, and has to carry a caveat that outside the
repository silence is not a clean result. A caveat is what an agent skims past;
a finding is what it reads.

## Proposed fix

When no repository encloses the store and at least one live document declares
`code:`, report one warning — say `code-unchecked` — naming how many documents
declare globs and why none were resolved. A warning, never an error: the store
is not broken, and `--strict` gates on errors only. A store with no `code:`
anywhere reports nothing, so the global default stays quiet.

Once it ships, the skill's "outside the store's git repository" caveat can go.

## Resolution

Built as proposed. `MaintenanceService._unresolved_code_issue` reports one `code-unchecked` warning when the service has no `CodeMatcher` and an unarchived document declares `code:` — archived ones are skipped by every code finding, so their silence hides nothing. No `doc_ids`, and not in `ERROR_KINDS`; the name is reserved against a store-defined check. `TestTheUncheckedCode` in `tests/modules/documents/test_code_references.py` pins it, each test shown to fail under its injected bug.

The packaged skill no longer carries the caveat: its "When to use" entry for checking now names `code-unchecked` as the finding that means the code went unchecked. `docir check --help`, the MCP `docir_check` tool, `CONTRACT.md`, README and arch-ad342aae8293 name it too.
