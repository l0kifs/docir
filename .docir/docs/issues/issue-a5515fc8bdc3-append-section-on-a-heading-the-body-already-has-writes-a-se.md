---
code:
- src/docir/modules/documents/domain/services/markdown_sections.py
code_baseline:
  src/docir/modules/documents/domain/services/markdown_sections.py: abad4c374b17
created: '2026-10-16'
description: --append-section wrote a new heading at the end even when the body had
  that heading, leaving appended text no section operation could reach.
id: issue-a5515fc8bdc3
owner: maintainer
related:
- issue-9d4db5cd5f29
- arch-0368cc754c15
status: resolved
tags:
- cli
- integrity
title: append-section on a heading the body already has writes a second copy of it
type: issue
updated: '2026-10-16'
---

## What is wrong

`docir update <id> --append-section "Context" --body "..."` on a body that already has
`## Context` wrote a second `## Context` at the end of the body, and every further call
added another. Each exited 0 and `docir check` said nothing; `docir lint --deep` reported
the result only afterwards, as `ambiguous-heading`. The flag's own help said "Append the
body text under this heading".

The duplicate is not cosmetic. Every section operation resolves a heading to its first
occurrence, so the appended text sat under a heading `get --section`, `--replace-section`
and a further append could not reach. The only way out was `--remove-section`, run on the
first copy, which deletes the original text instead (GitHub #37).

## Resolution

`append_section` now extends a heading the body already has and writes no heading line
for it. Where the text lands follows from what a section's own text is: prose goes at the
end of the heading's own text, before its first sub-heading, because after the last
sub-section `get --section` would return it as part of that sub-section and
`--replace-section` of it would erase it. Text opening with a sub-heading is a new last
sub-section. Text carrying a heading at the section's level or above is refused, since
wherever it went it would either pull an existing sub-section under itself or end the
section partway. A heading the body lacks still becomes a new section at the end.

Pinned in `test_domain_services.py` and `test_section_read.py`, on the CLI and the MCP
tool, each proven by re-injecting the old behaviour.
