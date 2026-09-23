---
code:
- src/docir/modules/documents/application/services/store_repairer.py
- src/docir/platform/filesystem/git_history.py
code_baseline:
  src/docir/modules/documents/application/services/store_repairer.py: 9f1e0f7f7801
  src/docir/platform/filesystem/git_history.py: 578151ff4967
created: '2026-09-23'
description: Why check --fix reads commit history to pick the established document,
  and why a filename tiebreak now says it could not tell.
id: adr-39210c34551a
owner: maintainer
related:
- issue-9683b4713792
- adr-1d1eddbb6fbd
- adr-3cfa867c8537
status: proposed
tags: []
title: Which of two colliding files keeps the id is decided by git, then created,
  then the alphabet
type: decision
updated: '2026-09-23'
---

## Decision

When two files claim one id, `docir check --fix` keeps the **established** one and re-issues
the rest. Three keys, in order, and the repair message names which decided:

1. **When git first added the file.** The established document has an older add commit than
   the one that arrived at the merge.
2. **`created`.** The documented intent, kept as the fallback where there is no history.
3. **The filename.** Deterministic and meaningless, kept only so the repair terminates — and
   it now says so: *"nothing else separated them; check this is the one your readers cited"*.

The established one keeps the id because an existing `related` edge naming it was written
against *some* document and cannot say which, so the document more readers have already cited
is the one to leave alone.

## What was actually wrong

`created` was already the primary key and already implemented — the reporter's "first by
filename keeps the id" describes the *tiebreak*, not the rule. Measured on three probes:

| `created` | survivor |
|---|---|
| both the same day | the file whose name sorts first |
| established older | established |
| established **newer** | the incoming one — the date overrules the alphabet |

The third proves the rule works. The defect is that `created` is a **`date`**, so it never
separates two branches cut from one base and merged inside a day — which is the shape of
nearly every real collision. The documented key silently degrades to filename order exactly
when a collision is most likely, and after a merge that is a coin flip on titles' first
letters.

## Why git, when docir does not shell out to git

This is the first `subprocess` call to `git` in docir, and it is a deliberate exception to the
precedent [[adr-1d1eddbb6fbd]] set when it parsed `.gitignore` rather than calling
`git check-ignore`.

That precedent is about **per-machine answers**. `git check-ignore` reports
`.git/info/exclude` and the user's global excludes, so a digest built on it would differ
between colleagues — which was the defect being fixed. Committed history is the opposite: it
is the same for everyone who has it, and it is the only record of which of two files arrived
later. Nothing inside the store holds that. `created` is the store's own attempt at it and is
too coarse; an incoming-edge count cannot work either, because edges are addressed by id and
both files answer to it — the same reason `delete` cannot pick between them
([[adr-3cfa867c8537]]).

Bounded accordingly: a five-second timeout, `check=False`, every failure mapped to `None`, and
the call made only when a collision actually exists. `None` is **unknown, never new** — an
untracked file, a shallow clone whose history does not reach the add, a store with no
repository above it, a machine without git. Each falls through to the next key rather than
sorting as if added at the epoch.

## Why the filename tiebreak now speaks

A filename tiebreak is a statement that docir *could not tell*. Leaving it silent was the
whole complaint: the repair looked authoritative and was arbitrary.

It cannot be replaced by a refusal. `check --fix` is the only sanctioned recovery path, and
[[adr-3cfa867c8537]]'s `delete` refusal now points at it by name — a `--fix` that can decline
would leave a caller with a refusal pointing at a refusal. So it repairs, and reports the
quality of its own evidence, which is the distinction between a repair somebody can check and
a coin flip they cannot see.

## What this does not build

The **pre-merge check** — the more valuable half of GitHub #22. The collision is knowable the
moment the second branch allocates, which is while it is still cheap to renumber; afterwards
whoever merges second is repairing a conflict. `check` has everything it needs except a
comparison against a base ref. Left open on the issue, deliberately: it is a new command
surface, not a tiebreak.

## Consequences

The repair stays a single command with no new flag, and its output now carries how confident
it was. A store outside a repository behaves exactly as before, which is what keeps the global
`~/.docir` and every test fixture unaffected.
