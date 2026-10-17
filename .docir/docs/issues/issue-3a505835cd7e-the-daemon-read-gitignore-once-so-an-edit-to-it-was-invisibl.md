---
code:
- src/docir/platform/filesystem/code_matcher.py
- src/docir/platform/filesystem/gitignore.py
code_baseline:
  src/docir/platform/filesystem/code_matcher.py: b41b14bb7069
  src/docir/platform/filesystem/gitignore.py: 54f7c5b78cdb
created: '2026-10-17'
description: Code fingerprints through the daemon used the ignore rules from when
  it started, so check and --verified disagreed with --no-daemon after any .gitignore
  edit.
id: issue-3a505835cd7e
owner: maintainer
related:
- adr-1d1eddbb6fbd
- issue-c2e8ce341a00
status: resolved
tags:
- daemon
- integrity
title: The daemon read .gitignore once, so an edit to it was invisible to check until
  a restart
type: issue
updated: '2026-10-17'
---

## What is wrong

`RepositoryCodeMatcher` built its `GitignoreIndex` once, in its constructor, and the
composition root builds one matcher per container. The daemon keeps one container for its
whole life, so the index did too — every `.gitignore` it had parsed and every directory
verdict it had cached. An edit to an ignore file changed what a fresh process fingerprints
and left the daemon answering from the old rules until it idled out or was replaced for
other code or another schema. The docs watcher does not help: it watches `docs/`.

## How it showed

A scratch repository with `src/main.py` and `src/gen/out.txt`, and one decision governing
`src/**`. Through a warm daemon, `docir check` reported no code finding before and after
`src/gen/` was added to `.gitignore`, on every call to the same daemon; `docir --no-daemon
check` on the same tree reported `code-drifted`, and so did the next daemon after `docir
daemon stop`. Live since 0.28.0, the release that started reading `.gitignore` — the
matcher had lived as long as the container since 0.10.0, harmlessly, while it cached
nothing. Every existing test asked a fresh matcher the second question, which is why none
failed.

## What else it reaches

The writes share the matcher. `docir update --verified` and the baseline a new `--code`
glob mints, run through the daemon, recorded digests taken under the old rules (by the same construction; not separately
reproduced) — committed
evidence that a teammate's `--no-daemon check` then disagrees with.

## Resolution

The index is scoped to one batch of patterns: `CodeMatcher` gained `matches_all` and
`fingerprint_all`, `RepositoryCodeMatcher` builds a fresh index per batch, and the three
callers that looped over patterns — `check`'s two passes and the write path's
`fingerprint_patterns` — ask in one batch. One index per *call* was measured and rejected:
+205-251ms per `check` over this repository's 124 globs. Per batch costs ~50ms on a warm
`check`, the two rebuilds the daemon used to skip.

Pinned twice, each by asking the *same* object the second question: a matcher re-reads an
edited ignore file, and a container — the daemon's stand-in — reports the drift on its next
`check`. Both fail with the old lifetime re-injected. Re-run through a live daemon on the
scratch repository: drift reported after the edit, gone after reverting it, one pid
throughout.
