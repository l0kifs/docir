# Gap Detection (Phase 5)

- [1. Classification](#1-classification)
- [2. Coverage checklists](#2-coverage-checklists)
- [3. Requirement smells](#3-requirement-smells)
- [4. Conflict triangulation](#4-conflict-triangulation)
- [5. Prioritization](#5-prioritization)

Run this phase **mechanically**. Iterate the checklists against every flow and every core entity; each unchecked box is a candidate finding. Do not rely on noticing things.

## 1. Classification

| Class | Definition | Typical evidence |
|-------|------------|------------------|
| `missing` | A business-necessary scenario has no implementation and no rule | Journey step with no code; no unwanted-behavior rule; off-system workaround |
| `misleading` | Naming, docs or UI imply behavior that differs from actual behavior | Glossary homonyms; label vs computed value mismatch; stale doc |
| `incorrect` | Implemented behavior contradicts stated intent or regulation | Code vs policy/ticket/SME conflict; a test asserting the wrong thing |
| `unusual` | Behavior exists but nobody can justify it | Magic constants, dead branches, hardcoded tenant IDs, "historical reasons" |
| `unstated` | Behavior everyone relies on but nobody wrote down | Implicit invariants, ordering assumptions, tribal knowledge |

## 2. Coverage checklists

### Lifecycle — per core entity

- [ ] Create: who may, what is mandatory, what is validated, what the duplicate rule is
- [ ] Read: who sees what; per-role redaction and visibility
- [ ] Update: which fields are mutable in which state; who approves
- [ ] Delete/archive: soft or hard; retention period; effect on history and reports
- [ ] Transfer of ownership between actors
- [ ] Bulk import/export path — almost always undocumented
- [ ] Merge/deduplicate two records
- [ ] Correction of an entry made in a closed period

### State machine — per stateful entity

- [ ] Every state has a defined exit
- [ ] Every transition has an actor and a precondition
- [ ] Terminal states are truly terminal, or a reopen rule exists
- [ ] Illegal transitions are explicitly rejected, not merely unreachable
- [ ] Concurrent transition by two actors is defined
- [ ] Every enum value is reachable and every one is exited
- [ ] What happens to in-flight entities when the rule changes

### Unhappy paths — per flow

- [ ] External dependency down, slow, or returning partial data
- [ ] Payment / auth / third-party failure, and retry semantics
- [ ] Duplicate submission, double-click, replayed webhook (idempotency)
- [ ] Partial completion then resume; abandonment and its timeout
- [ ] Cancel, undo, rollback, compensating action
- [ ] User error correction after the fact — "I entered the wrong amount yesterday"
- [ ] Data arriving late or out of order
- [ ] Entity changed state between validation and commit
- [ ] Permission revoked mid-flow

### Actors

- [ ] Every actor in `01-actors.yaml` appears in at least one flow
- [ ] Support/ops: how do they diagnose and unstick a case? With what tool?
- [ ] Admin: who can override a rule, and is the override audited?
- [ ] New user: onboarding, empty state, first run
- [ ] Leaving user: offboarding, data export, account closure
- [ ] Delegated/deputy access — vacation, absence, agency, power of attorney
- [ ] Non-human actors: scheduler, partner system, importer

### Cross-cutting

- [ ] Permissions expressed per rule, not only per endpoint
- [ ] Audit trail: who changed what, when, and why
- [ ] Notifications: who must be told, when, on which channel — and what if delivery fails
- [ ] Money: rounding, currency, tax, partial refunds, reconciliation
- [ ] Time: timezone, business calendar, cutoffs, expiry, backdating, DST
- [ ] Volume: limits, quotas, throttling, and behavior at the limit
- [ ] Compliance, consent, retention, and jurisdiction-specific variation
- [ ] Migration and backward compatibility for data created under older rules
- [ ] Observability: can anyone tell this rule fired, or that it failed?

### Journey level

- [ ] Every backbone column has at least one viable step
- [ ] Walking-skeleton test passes end to end
- [ ] Pain points visible in support data map to a rule or a gap
- [ ] Steps performed outside the system are recorded as gaps
- [ ] Every hotspot from the event timeline is resolved

## 3. Requirement smells

Scan all written rules, requirements, tickets, and your own drafted rule statements. These patterns derive from the natural-language quality criteria in ISO/IEC/IEEE 29148 and reliably mark defects; the scan is cheap and gives feedback before any human review.

| Smell | Wording | Why it is a defect |
|-------|---------|--------------------|
| Vagueness | sufficient, appropriate, adequate, user-friendly, quickly | Not testable; every reader interprets differently |
| Loophole | as far as possible, if practical, where appropriate | Removes the obligation; unresolvable at acceptance |
| Superlative | fastest, best, maximum | No measurable target |
| Subjective | intuitive, seamless, easy | No acceptance criterion possible |
| Negative-only | the system shall not allow X | Leaves the positive behavior undefined — what happens instead? |
| Ambiguous pronoun | it, they, this with unclear antecedent | Multiple valid readings |
| Comparative w/o baseline | faster than before | Baseline unrecorded |
| Open-ended list | etc., and so on, including but not limited to | Scope unbounded |
| Passive w/o actor | the record is approved | No responsible actor |
| Compound requirement | and / or chains in one statement | Untestable, unsliceable |
| Incomplete reference | per the standard process | Reference not resolvable |

Automate this as a regex/lint pass over `03-rules.yaml`. A `confirmed` rule must be smell-free.

## 4. Conflict triangulation

Compare these pairs systematically. Record every mismatch as a finding; do not resolve silently.

- code ↔ tests
- code ↔ docs / tickets / comments
- code ↔ SME statement
- SME ↔ SME (different roles disagreeing marks a bounded-context or authority gap)
- UI wording ↔ computed behavior
- client-side validation ↔ server-side rule
- rule ↔ regulation or contract
- assumed flow ↔ analytics (do users actually do what the flow assumes?)
- current code ↔ git history (a rule that was deliberately removed is a question, not a bug)

## 5. Prioritization

Score each gap:

```
severity = impact × likelihood × blast_radius
effort   = cost_to_clarify
```

- **Blocking** — a wrong answer changes the design, or the gap touches money, safety, compliance, or data loss
- **Material** — affects real users regularly but has a workaround
- **Cosmetic** — worth recording, not worth a question this round

Only blocking gaps generate questions in the current round (see `questioning.md` §2 for the budget). Material and cosmetic gaps stay in `05-gaps.yaml` with `status: open`.

Sort the delivered register by severity, not by discovery order.
