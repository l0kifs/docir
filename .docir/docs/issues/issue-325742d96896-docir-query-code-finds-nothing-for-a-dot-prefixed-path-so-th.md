---
code:
- src/docir/modules/documents/domain/services/code_globs.py
- .github/workflows/ci.yml
code_baseline:
  .github/workflows/ci.yml: bdba3b7c9037
  src/docir/modules/documents/domain/services/code_globs.py: 27940b520ad4
created: '2026-09-18'
description: _normalize strips a leading dot as a character class, so a document governing
  .github/workflows/** can never be returned by the reverse query — while check's
  own matcher, which does not share the function, reports its drift correctly.
id: issue-325742d96896
owner: maintainer
related:
- kind: refines
  to: issue-90aea6d1b891
- adr-b2cfed9d5888
status: resolved
tags:
- cli
- retrieval
title: docir query --code finds nothing for a dot-prefixed path, so the CI notice
  step is blind to workflow changes
type: issue
updated: '2026-09-18'
---

## What is wrong

`code_globs._normalize` is one line:

```python
return path.strip().lstrip("./").strip("/")
```

`str.lstrip` takes a *character set*, not a prefix. It is there to drop a leading
`./`, and it does — but it also eats the leading dot of any dotted path:

```
_normalize(".github/workflows/ci.yml") == "github/workflows/ci.yml"
```

The pattern side is not normalized the same way (`_compiled` strips `/` only), so
the regex still expects the dot and the two can never meet:

```
matches(".github/workflows/ci.yml", ".github/workflows/ci.yml")  -> False
matches(".github/workflows/**",     ".github/workflows/ci.yml")  -> False
matches("docs/tags.yaml",           "docs/tags.yaml")            -> True
```

## What it costs

Four documents in this store declare a workflow glob and none of them can be
found from the code they govern: adr-b2cfed9d5888, issue-82b01d7f80d0,
issue-b323a5b2ba18 and run-30aceb4eacc6.

```
docir query --include-inactive --code .github/workflows/ci.yml   # []
docir query --include-inactive --code src/docir/entry_points/cli/app.py   # 7
```

The live cost is in this repository's own CI. The "Decisions this branch touches"
step runs `docir query --code` over the changed files, so a pull request that
edits a workflow is told no decision governs it. The document written to be found
exactly there — adr-b2cfed9d5888, which governs `.github/workflows/ci.yml` because
the decision it records is enforced by a CI step — is the one the step cannot
return. A notice that answers "nothing" is indistinguishable from one that has
nothing to say.

`.docir/**` and every other dotted path are affected identically.

## Why nothing reported it

There are two matchers over one grammar. `unmatched-code`, `code-drifted` and
`code-changed` resolve patterns through `platform/filesystem/code_matcher.py`,
which walks the tree with `Path.glob` and never calls `_normalize` — so `check`
reports those four documents' drift correctly, and only the *query* is blind.
The split is why the defect survived: every guard that would have caught it is
on the other matcher, and the query's own tests use `src/` paths.

The rule this breaks is the one in the read-path note — `--code` matches globs as
**text**, before the limit, never by walking the tree — which is right, and is
exactly why the text path needs the grammar the walking path gets for free.

## The fix

Strip the prefix as a prefix, not as a character class, and run the pattern and
the path through the same normalizer so the two sides cannot disagree again.

Verify by injection: restore the `lstrip` and assert the four documents above are
no longer returned for `.github/workflows/ci.yml`. A count alone will not do it —
assert which ids come back, or the guard cannot tell "nothing governs this" from
"the matcher is blind".

## Resolution

FIXED 2026-09-18. `_normalize` now strips a leading `./` as a *prefix* rather than
as a character class, and **both** sides go through it: `matches` normalizes the
pattern as well as the path, so the two cannot drift apart again, and `_compiled`
is cached on the one spelling rather than on however a pattern was typed.

Against this store, `.github/workflows/ci.yml` now returns the seven documents
that govern it, where it returned none.

Guarded in two places, each proven by restoring the `lstrip`. The grammar table in
`test_domain_services.py` gains the dotted cases, including `src/auth/**` against
`.src/auth/login.py`, which must stay **false** — the dot is part of the name, not
noise to be stripped, and a fix that over-stripped would pass every other case.
`TestQueryByPath` asserts *which* id comes back for a dotted path, because an empty
list cannot distinguish "nothing governs this" from "the matcher is blind". A third
injection — normalizing the path but not the pattern — is caught by the same table.

The forward check is untouched. `RepositoryCodeMatcher` still answers "does this
pattern still name anything" by walking the tree, which handled a dotted directory
correctly all along. Only the grammars had to agree, and the shared normalizer is
what makes that structural rather than remembered.
