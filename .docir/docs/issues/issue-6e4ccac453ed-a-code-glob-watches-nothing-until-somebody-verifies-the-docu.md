---
code:
- src/docir/modules/documents/domain/services/checks/verification_rules.py
- src/docir/modules/documents/application/services/code_evidence.py
code_baseline:
  src/docir/modules/documents/application/services/code_evidence.py: 793cdf7277e9
  src/docir/modules/documents/domain/services/checks/verification_rules.py: cd968669505d
created: '2026-09-16'
description: Drift digests are written only by --verified, and in docir's own store
  none of the 99 documents naming the code they govern ever was — so nothing reported
  when that code moved.
id: issue-6e4ccac453ed
owner: maintainer
related:
- adr-d9e6d5ccd0b4
- adr-bd7c4f3c5764
status: resolved
tags:
- cli
- integrity
title: A code glob watches nothing until somebody verifies the document
type: issue
updated: '2026-09-17'
verified: '2026-09-17'
verified_code:
  src/docir/modules/documents/application/services/code_evidence.py: 793cdf7277e9
  src/docir/modules/documents/domain/services/checks/verification_rules.py: cd968669505d
verified_content: ed193d97811c
---

A `code:` glob is a promise that `docir check` will say something when the code under it
moves. It only does once the document is `--verified`: `verified_code` is written by that
flag and by nothing else, so a document nobody has reviewed carries no digest, and
`code-changed` skips it without a word.

## What that costs, measured

In docir's own store, 99 documents name the code they govern and not one of them had ever
been `--verified`. `code-changed` could fire on none of them: every glob named its code,
watched it, and reported nothing when it moved.

Nothing tells those 99 that they are inert. The glob renders on every read view, `docir
query --code` finds them, and `unmatched-code` still fires if a pattern stops matching — so
the feature looks live from every angle except the one it exists for.

## Why the obvious fix is the wrong one

Fingerprinting on the write that declares a glob would close it, and writing that digest
into `verified_code` would be laundering: the field means *somebody read this*, and a write
that fills it in makes the review clock a side effect of running a command. That is the
rule [[adr-d9e6d5ccd0b4]] states and [[adr-bd7c4f3c5764]] exists for.

The way out is that these are two different claims. "The code moved since somebody read
this" needs a reviewer. "The code moved since this document said it governs this" needs
only the write that said it — and it is the claim that can be made automatically, because
it asserts nothing about anybody having read anything.

## What the shape of the fix has to satisfy

Storage in the file, not the index: the index is gitignored and rebuilt, so a baseline
living only there would reset on every `reindex` and never fire.

Minted once per pattern and never refreshed by a mechanical write. Re-declaring a glob
through `--set-code` reads nothing, so re-basing there would hand every write a way to
clear a drift nobody looked at — the same laundering through a cheaper door.

And the two findings have to partition the patterns rather than overlap, or one moved file
is reported twice under two names.
