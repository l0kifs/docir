---
created: '2026-08-06'
description: 'The flag takes heading text and adds the ## itself; passing ''## Resolution''
  silently writes ''## ## Resolution'', which no section-edit mode can repair.'
id: issue-d5f68b44b1d9
related:
- arch-3e305bc76ff0
status: resolved
tags:
- cli
- material
title: '--append-section accepts a heading that already carries its ##, and writes
  it twice'
type: issue
updated: '2026-08-06'
---

**Class:** missing · **Severity:** material
**Flow:** arch-3e305bc76ff0 · **Step:** `docir update <id> --append-section "<heading>"`

## Finding

`--append-section` takes the heading *text* and writes the `##` itself
(`markdown_sections.append_section`: `section = f"{prefix} {heading}"`). Passing the
heading the way it appears in the file — `"## Resolution"` — is accepted silently and
produces `## ## Resolution`. Nothing validates that the argument is not already a
heading, and nothing in the output shows the written line.

## What happens today

REPRODUCED end to end on a scratch store:

```
docir update adr-0001 --append-section "## Resolution" --body "hello"
  body -> '## ## Resolution\n\nhello\n'

docir get adr-0001 --section "Resolution"
  error: no section 'Resolution' in this document; available: '## Resolution'
```

The section is now addressable only by the literal string `## Resolution`, and neither
section-edit mode can repair it:

- `--replace-section "## Resolution"` replaces the *content* and keeps the heading line
  by contract, so the body changes and `## ## Resolution` survives.
- `--append-section "Resolution"` appends a *second*, sibling section rather than fixing
  the first, leaving the document with two Resolution headings.

The only route back is `--replace-body --force` — the riskiest edit mode, the one with
the disk-divergence guard, and the one the agent guide ranks last. So the *safest* body
edit is the one that can produce a state only the *riskiest* one can leave. `docir check`
reports nothing: a doubled `#` is not malformed frontmatter and not a graph problem, so
no tier of validation sees it.

Observed for real while writing the resolution of `issue-aaa512e9c58f`, by an agent that
had read the guide. The guide is correct (`--append-section "Resolution"`, bare); the
defect is that the plausible misreading is accepted rather than refused.

## Impact

Silent body corruption on the edit path documented as the default and safest choice. It
renders as a literal `## Resolution` inside the heading on the published site, and it
breaks `get --section` / `--replace-section` addressing for that section under the name
a reader would use. Agents are the likely victims: they compose the argument from the
heading they just read in a body, where it carries its `##`.

## Proposed direction

Reject a heading argument that already starts with `#`, at Tier 0 — the error can name
the fix exactly ("pass `Resolution`, not `## Resolution`; the level is chosen by
`--level`"). Stripping the markers instead would be the friendlier-looking choice and is
worse: it makes `"### Notes"` silently mean level 2, guessing at an intent the caller
stated. The same check belongs on `--replace-section` and `get --section`, which match by
heading text and so have the identical trap with the identical fix.

Repairing existing damage is deliberately out of scope: one document is affected, and
`check --fix` only repairs what needs no guess.

## Resolution

FIXED. `append_section` now refuses a heading argument whose text begins with
`#`, at Tier 0, and the error names the argument that works: passing
`"## Resolution"` answers with `'Resolution'` rather than writing
`## ## Resolution` and saying nothing.

Stripping the markers was rejected for the reason the filing gave: it would make
`"### Notes"` silently mean level 2, guessing at an intent the caller stated. A
`#` *inside* the text is untouched — `"C# interop"` is a real heading, and
rejecting it would trade one silent failure for a loud wrong one.

The proposed direction asked for the same check on `--replace-section` and
`get --section`. Implementing it showed that neither needs one and `get`
actively must not have one. Both match on heading text, so neither can corrupt:
they *fail* on a marker-carrying argument rather than accepting it. And
hand-editing markdown is permitted, so a file that already carries a doubled
marker has to stay readable — that is how someone finds it and repairs it. What
those two lacked was a decent message. `replace_section` answered "no matching
heading found" and left the caller guessing; it now shares one miss error with
`extract_section` that lists the real headings, so the mirror mistake names its
own fix.

That sharing is the second half of the change: the heading match and the section
end boundary are now one `_locate_section` / `_section_end` pair used by both.
The module's stated contract is that `get --section X` returns exactly the span
`--replace-section X` overwrites, and it was two copies of the same loop —
divergence was a matter of someone editing one of them.

**Affected documents: none remain.** A scan of every `.md` in the repo with the
module's own `_HEADING_RE` finds no heading whose text starts with `#`. The one
document that carried the damage, `issue-aaa512e9c58f`, was repaired via
`--replace-body --force` when the defect was noticed — which is precisely the
evidence for the "only the riskiest mode can repair it" claim above.

Verified by injecting both bugs: dropping the guard fails five domain tests and
two CLI tests, and reverting the miss error fails four more.
