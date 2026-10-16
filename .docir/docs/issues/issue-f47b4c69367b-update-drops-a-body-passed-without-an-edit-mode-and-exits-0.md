---
code:
- src/docir/entry_points/dispatch.py
code_baseline:
  src/docir/entry_points/dispatch.py: 601b242f1b46
created: '2026-10-16'
description: Body text given to update with no append, replace-section or replace-body
  mode was discarded silently while the call reported success.
id: issue-f47b4c69367b
owner: maintainer
related:
- issue-9d4db5cd5f29
- arch-0368cc754c15
status: resolved
tags:
- cli
- integrity
title: update drops a body passed without an edit mode and exits 0
type: issue
updated: '2026-10-16'
---

## What is wrong

`docir update <id> --body-file f.md` — or `--body`, or `--stdin` — with no body edit mode
printed the unchanged document and exited 0. With a metadata flag beside it, that half
landed and the body did not. A caller could not tell from the output that the edit had
been dropped; only reading the body back showed it (GitHub #36). The MCP tool had a third
shape of the same silence: `body` passed beside `replace_body`, which carries its own
text, was discarded.

`--remove-section` with a body was already refused, by a check written for that one
combination (issue-9d4db5cd5f29), so the rule existed and covered one case of three.

## Resolution

The dispatcher refuses body text that no edit mode in the call writes, with exit 2 and an
error naming `--append-section`, `--replace-section` and `--replace-body --force`. The
whole call is refused, metadata included, so nothing half-lands. One predicate covers all
three shapes, and it lives at the dispatcher because each transport folds `body` into a
mode its own way. Blank text is let through: it writes nothing and loses nothing. Two
writing modes at once keep their own error ("only one body edit mode").

Pinned in `test_section_read.py` on the CLI (`--body`, `--body-file`, with and without a
metadata flag) and on the MCP tool, each proven by re-injecting the old behaviour.
