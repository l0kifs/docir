# Modeling & Formalizing (Phases 3–4)

- [1. Event timeline](#1-event-timeline)
- [2. Journeys and the backbone](#2-journeys-and-the-backbone)
- [3. Service blueprint](#3-service-blueprint)
- [4. Glossary](#4-glossary)
- [5. EARS rule syntax](#5-ears-rule-syntax)
- [6. Decision tables](#6-decision-tables)
- [7. Examples](#7-examples)

## 1. Event timeline

Derived from EventStorming's Big Picture format, adapted for solo/agent use: you build the timeline from code evidence, then use it to interrogate humans.

Collect significant **business events** in past tense — `OrderPlaced`, `PaymentCaptured`, `RefundIssued`, `SubscriptionLapsed` — and order them on a timeline. In code, events surface as: state transitions, emitted domain events, audit log writes, outbound notifications, and rows appended to history tables.

Then annotate:

- **Actors** — who or what causes each event (human role, scheduler, external webhook)
- **External systems** — what the flow depends on
- **Hotspots** — every ambiguity, contradiction, unexplained branch, or "it depends". Do not resolve hotspots inline; mark them. They are your richest source of gaps and questions.

Two signals worth hunting explicitly:

**Language mismatch.** The same concept named differently in two modules, or one word meaning two things (`account` in billing vs `account` in auth). This marks a bounded-context boundary — and forcing one unified model across it creates friction rather than clarity. Record both meanings in the glossary and flag it.

**Timeline holes.** An event with no plausible predecessor or successor means a step is missing, or it happens outside the system — email, spreadsheet, a phone call, someone editing the DB. **Off-system steps are gaps by definition.** Look for them in support runbooks, admin-only endpoints, and manual DB fix-ups in the run log.

Once the big picture is stable, drop to process-modelling level for one end-to-end flow at a time, including its variants.

## 2. Journeys and the backbone

Per primary actor, lay activities left→right as a narrative (the **backbone**). Under each activity, stack the tasks and rules that serve it.

Then **walk the map** and ask at every column:

- Is a step missing without which the journey cannot complete?
- Is a step duplicated under a different name?
- What does the actor need here that the system does not serve?
- Can the actor **recover** when this step fails?

A column with nothing viable at the top of its stack is a break in the journey — a gap, not a backlog item.

**Walking-skeleton test:** if only the top row of every column existed, could the actor complete their job end to end? Anywhere the answer is no marks either a missing capability or a mis-modeled backbone.

## 3. Service blueprint

Use when the flow crosses teams or systems. Add the backstage layer beneath the journey: internal actors, supporting systems, handoffs, and the line of visibility separating what the user sees from what the organization does.

Most "each touchpoint scores well but customers still churn" problems live in the **handoffs**, not the touchpoints. In code these appear as: queue boundaries, cross-service calls without a compensating action, manual ops steps, and anything whose failure mode is "a human notices eventually."

## 4. Glossary

One term, one definition, one owner. Every synonym and every homonym is a finding.

Populate from: entity names, enum values, DB columns, API field names, UI labels, and SME vocabulary. Then diff them. Where the UI label and the computed value disagree, you have a `misleading` gap.

## 5. EARS rule syntax

Write every rule in constrained natural language. Clause order is fixed:

```
While <precondition(s)>, when <trigger>, the <system> shall <response>.
```

Ruleset: zero-or-many preconditions, zero-or-one trigger, exactly one system, one-or-many responses.

| Pattern | Template | Use for |
|---------|----------|---------|
| Ubiquitous | The `<system>` shall `<response>` | Always-true properties |
| Event-driven | When `<trigger>`, the `<system>` shall `<response>` | Reaction to an event |
| State-driven | While `<state>`, the `<system>` shall `<response>` | Behavior during a state |
| Unwanted behavior | If `<condition>`, then the `<system>` shall `<response>` | Errors, failures, abuse, timeouts |
| Optional feature | Where `<feature included>`, the `<system>` shall `<response>` | Configurable / per-tenant |
| Complex | Combination of the above | Rich conditional behavior |

**The unwanted-behavior pattern is the primary gap detector.** For every event-driven rule you write, force these:

- What if the trigger never arrives?
- What if it arrives twice, or out of order?
- What if the response fails partway?
- What if an external dependency times out?
- What if the actor lacks permission at that moment?
- What if the entity changed state between check and action?

Most systems have **zero** written rules here. Each unanswerable case is a gap, not a question about code.

## 6. Decision tables

Any rule with more than two conditions gets tabulated. Enumerate every combination of condition values; each row states the outcome.

- Rows with no defined outcome → gap (`missing`)
- Rows marked "cannot happen" → an unstated invariant; ask what enforces it
- Two rows with the same conditions and different outcomes → contradiction, high priority

Store alongside the rule in `03-rules.yaml` as `decision_table`.

## 7. Examples

Per rule, write concrete Given/When/Then examples with real names and real values. Abstractions hide disagreement; specifics expose it.

Card taxonomy (from Example Mapping — use as tags, not literal cards):

| Tag | Meaning |
|-----|---------|
| `story` | The flow under discussion |
| `rule` | An acceptance criterion / business rule |
| `example` | A concrete illustration of one rule |
| `question` | Nobody available can answer this |

**Readiness heuristics — apply them to your own output:**

- Many `question` items → the flow is not understood. Do not write a spec; go elicit.
- Many `rule` items under one flow → the flow is too big. Slice it.
- Many `example` items under one rule → the rule is over-complex. Split it into several rules.
- A rule needing no examples → genuinely unambiguous. Move on; do not manufacture examples.

Boundary examples are mandatory for numeric or temporal rules: at the limit, one below, one above, zero, negative, null, maximum, and the timezone/DST edge.
