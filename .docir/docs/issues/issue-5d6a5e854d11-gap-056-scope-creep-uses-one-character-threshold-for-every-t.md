---
created: '2026-07-30'
description: A glossary, a rule register and a probe log are long by definition; the
  check has no way to know that and advises splitting them.
id: issue-5d6a5e854d11
owner: maintainer
related:
- ref-cb2beaa41604
- adr-2a3f625bb2f8
status: open
tags:
- schema
- material
title: GAP-056 — `scope-creep` uses one character threshold for every type, so a register
  is always too long
type: issue
updated: '2026-07-30'
---

# GAP-056 — `scope-creep` uses one character threshold for every type, so a register is always too long

**Class:** unstated · **Severity:** material · **Confidence:** observed
**Flow:** FLOW-003 (maintenance) · **Step:** `docir lint --deep`
**Frequency:** every run against a corpus containing a reference document

## Finding

`scope-creep` compares a body's character count against a single constant, regardless of
the document's type. Nothing in the schema can raise or waive it, and nothing states what
the threshold is.

## What happens today

OBSERVED. Of the 7 `scope-creep` findings on docir's own store, 5 are documents whose
length is the point: the two architecture documents (19 144 and 28 427 chars), the business
rule register (36 823), the glossary (8 100) and the discovery probe log (28 546). A
glossary split in half is two glossaries; a rule register split in half is a register that
no longer answers "what are the rules".

## Impact

Advisory rather than blocking, so the cost is noise rather than a broken build — but it is
noise that arrives on every run and cannot be silenced, and it lands hardest on exactly the
document types added to hold long reference material. Together with GAP-055 it means all 21
findings `lint --deep` produces against the product's own corpus are unactionable.

The parallel is `orphan` under `--strict` (GAP-006): a warning that fires on the default
state of correct usage. That was fixed by giving findings a severity so the gate could
ignore the noisy kind. Here the equivalent knob does not exist — the threshold is neither
per-type nor configurable nor documented.

## Proposed default

Make the threshold a per-type schema key (`max_body_chars`, alongside `review_days`), with
the current constant as the default and no limit when a type sets it to 0. The bundled
`reference` type would set 0: a register is a register. State the default in
`docir lint --help`, which currently describes the check without naming a number.

## Actors affected

- repository maintainer

## Evidence

- `src/docir/modules/documents/application/services/maintenance_service.py` (the
  scope-creep threshold constant)
- `.docir/docs-schema.yaml` (the `reference` type, added 2026-07-30)
- PROBE-L2 in the 2026-07-30 probe log
