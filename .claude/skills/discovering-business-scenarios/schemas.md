# Artifact Schemas

All artifacts are YAML, append-oriented, one record per item. Patch records in place; never regenerate a whole file from context.

Common field conventions:

- `status` — see per-schema enums
- `evidence` — list of `path:line`, ticket IDs, log queries, or `interview:<id>`
- `confidence` — `observed` | `inferred` | `assumed`
- IDs are stable and never reused: `BR-###`, `GAP-###`, `Q-###`, `ACT-###`, `FLOW-###`

---

## 01-actors.yaml

```yaml
- id: ACT-003
  name: fulfillment operator
  type: human            # human | system | scheduler | external_partner
  goal: "Get paid orders shipped the same day"
  authority: "Can cancel a line item; cannot issue refunds"
  frequency: "continuous during business hours"
  flows: [FLOW-002, FLOW-005]
  evidence: [src/auth/roles.py:44, interview:ops-lead-2026-07]
  confidence: observed
```

## 02-flows/&lt;flow&gt;.md

Free-form markdown per flow, but must contain these sections:

```markdown
# FLOW-002 checkout

## Backbone
browse → configure → pay → fulfill → deliver → after-sales

## Event timeline
| # | Event | Actor | Trigger | Evidence |
|---|-------|-------|---------|----------|
| 1 | CartSubmitted | customer | POST /checkout | src/api/checkout.py:22 |

## Hotspots
- H1: no defined behavior when stock drops between reservation and capture

## Off-system steps
- Ops edits `orders` table directly to unstick PAID orders (runbook §4)

## Rules
BR-041, BR-042, BR-050

## Gaps
GAP-009, GAP-012
```

## 03-rules.yaml

```yaml
- id: BR-042
  statement: >
    While the account is suspended, when a withdrawal is requested,
    the system shall reject the request and notify the account owner.
  pattern: complex          # ubiquitous | event | state | unwanted | optional | complex
  flow: FLOW-007
  actor: account owner
  evidence: [src/billing/withdraw.py:118, tests/test_withdraw.py:64]
  confidence: observed
  status: assumed           # assumed | confirmed | disputed | superseded
  owner: head of billing
  decision_table: null      # required when >2 conditions; see modeling.md §6
  examples:
    - given: "suspended account, balance 500"
      when: "withdraw 100 requested"
      then: "rejected with code ACC_SUSPENDED, owner notified by email"
  boundaries: ["balance = 0", "amount = balance", "amount = balance + 0.01"]
  open_questions: [Q-017]
```

Decision table form when needed:

```yaml
  decision_table:
    conditions: [account_state, amount_over_limit, has_approval]
    rows:
      - [active,    false, any]  → allow
      - [active,    true,  true] → allow
      - [active,    true,  false] → reject:NEEDS_APPROVAL
      - [suspended, any,   any]  → reject:ACC_SUSPENDED
      - [closed,    any,   any]  → UNDEFINED       # → GAP
```

## 04-glossary.yaml

```yaml
- term: account
  definition: "A billing relationship with one payment method and one balance."
  owner: head of billing
  used_in: [billing, reporting]
  conflicts:
    - context: auth
      definition: "A login identity."
      gap: GAP-014
  evidence: [src/billing/models.py:12, src/auth/models.py:9]
```

## 05-gaps.yaml  — primary deliverable

```yaml
- id: GAP-009
  class: missing            # missing | misleading | incorrect | unusual | unstated
  flow: FLOW-002
  step: post-payment fulfillment
  finding: >
    No defined behavior when a line item becomes unavailable after payment capture.
  actual_today: >
    Order remains in PAID indefinitely; ops resolves manually via direct DB edit.
  actors_affected: [customer, fulfillment operator, support]
  evidence: [src/orders/fulfill.py:203, "support tickets tag=stuck-order", runbook.md:88]
  confidence: observed
  severity: blocking        # blocking | material | cosmetic
  impact: "Customer charged, nothing shipped, no automated notice"
  frequency: "~40/month (support tag volume)"
  proposed_default: "Partial fulfillment + automatic partial refund within 24h"
  question: Q-023
  status: open              # open | asked | resolved | accepted | superseded
  resolution: null
```

## 06-questions.yaml — primary deliverable

```yaml
- id: Q-023
  gap: GAP-009
  audience: head of fulfillment
  blocking: true
  rank: 1
  question: >
    When an item becomes unavailable after payment, should we partially fulfil
    and refund the difference, hold the whole order, or substitute?
  today: "Order stays PAID; resolved manually (src/orders/fulfill.py:203)"
  proposed_answer: "Partial fulfilment + automatic partial refund within 24h"
  context: "~40 occurrences/month based on support tags"
  asked: 2026-07-26
  answered: null
  authority: null
  answer: null
  assumption_if_unanswered: >
    Proceeding on partial fulfilment + refund; review before any release that
    touches fulfilment.
```

## 00-frame.md

```markdown
# Frame
- Business outcome: <...>            [confidence]
- Success metric: <...>
- Payers / users / affected parties: <...>
- Core vs supporting vs generic: <...>
- In scope: <bounded contexts>
- Out of scope: <...>
- Decision owners: <role → area>
- Budget: <passes, subagents, question cap>
- Definition of done: quality gates in SKILL.md §9
```

## 99-log.md

Append-only. One line per unit of work:

```
2026-07-26T10:02Z  P1 structural  src/billing/**        → 14 entities, 9 endpoints
2026-07-26T10:31Z  P4 semantic    src/billing/withdraw  → BR-040..BR-044
2026-07-26T10:33Z  SKIPPED        src/legacy_import/**  → no test coverage, out of scope per frame
```

The `SKIPPED` lines are as important as the rest — they are the coverage report.
