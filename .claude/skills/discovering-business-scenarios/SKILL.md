---
name: discovering-business-scenarios
description: Reconstructs a project's business goals, actors, flows and rules from its code and artifacts, then identifies missing, misleading, incorrect or unusual scenarios and produces the clarifying questions a human must answer. Use when documentation is absent, stale or untrusted, when onboarding onto an unfamiliar system, before a migration or rewrite, or when asked to find business gaps rather than technical defects.
---

# Discovering Business Scenarios & Gaps

Reconstruct what a system actually does for the business, then find where it fails the people who use it.

**You are not documenting code.** A business rule survives a rewrite (`orders over 10 000 require manager approval`); an implementation detail does not (`OrderValidator.check() raises ValidationError`). If you cannot state the outcome in business terms, it is not a business rule.

**Primary output is a gap register and a question queue**, not a description of the system. A perfect description with no findings is a failed run.

---

## 1. Non-negotiables

These override everything else in this skill. Violating any one invalidates the run.

1. **No rule without evidence.** Every rule line carries `file:line` (or ticket ID, log query, interview ID). A rule you cannot point at is a *question*, not a rule.
2. **Tag every line `observed` / `inferred` / `assumed`.** Never let inference migrate into the observed set between passes.
3. **Never invent an answer to an open question.** Unanswered stays `open`. If you must proceed, write `assumed:` with an owner and a review trigger — never silently pick a plausible default.
4. **Do not prime your own search.** Query for what a module *enforces*, not for the rule you expect to find. Feeding an expected answer into a pass biases output toward that expectation rather than toward the code.
5. **Persist after every unit of work.** Artifacts live on disk (§3). Context is scratch; the files are the deliverable.
6. **Append and patch artifacts; do not rewrite them wholesale.** Repeated full rewrites erode detail — each rewrite trends shorter and drops domain specifics. Update line-items in place.
7. **Report coverage honestly.** State which modules/flows you did not examine. Silent partial coverage is the most damaging failure mode here.

---

## 2. The loop

```
0 Frame      → scope, decision owners, definition of done
1 Inventory  → rank evidence sources by trustworthiness
2 Extract    → 5 grounded passes, structural → intentional
3 Model      → actors, event timeline, journeys, glossary
4 Formalize  → EARS rules, decision tables, examples
5 Detect     → coverage checklists, smell scan, triangulation
6 Ask        → batched, budgeted, answerable questions
7 Verify     → adversarial self-review, gates, handoff
```

Phases 2→6 iterate per bounded context. Each answered question invalidates part of the model — re-enter at 4.

| Phase | Read before starting |
|-------|----------------------|
| 1–2 | `references/extraction.md` |
| 3–4 | `references/modeling.md` |
| 5 | `references/gap-checklists.md` |
| 6 | `references/questioning.md` |
| all | `references/schemas.md` for record formats |

Load reference files on demand, not upfront.

---

## 3. Artifacts on disk

Create `./analysis/` in the target repo (or a path the user specifies):

```
analysis/
  00-frame.md          scope, owners, done-criteria, coverage log
  01-actors.yaml       A2 actor catalog
  02-flows/<flow>.md   A3 per-flow event timeline + journey
  03-rules.yaml        A4 rule register
  04-glossary.yaml     A5 terms, one definition each
  05-gaps.yaml         A6 gap register          ← primary deliverable
  06-questions.yaml    A7 question queue        ← primary deliverable
  99-log.md            append-only run log: what you read, what you skipped
```

Schemas in `references/schemas.md`. Keep YAML machine-readable — these feed spec-driven work downstream.

Write `99-log.md` as you go. It is how the next run (or the next agent) resumes without re-reading the repo.

---

## 4. Phase 0 — Frame

Do not touch code until these are answered or explicitly recorded as unknown (an unknown here is finding #1):

- What outcome does this system produce for the business? How is it measured?
- Who pays for it, who uses it, who suffers when it breaks?
- Which parts are core domain vs supporting vs generic?
- What is out of scope for this run?
- **Who decides** on each ambiguous rule? No owner → the question can never close.

Set a budget: number of extraction passes, question cap (§7), and which bounded contexts are in scope. Record in `00-frame.md`.

---

## 5. Phase 2 — Extraction, briefly

Full detail in `references/extraction.md`. The rule that matters most:

**Run five separate passes; do not jump straight to "infer the business rules."** Abstraction without grounding produces confident fiction.

| Pass | Asks | Never does |
|------|------|-----------|
| P1 Structural | What exists? | Interpret |
| P2 Behavioral | What does each unit do? | Generalize |
| P3 Relational | What calls what, in what order? | Skip transaction boundaries |
| P4 Semantic | What rule does this enforce? | Assert without `file:line` |
| P5 Intentional | Why would a business want this? | Emit anything untagged `inferred` |

Cross-check P4 against P1–P3 before writing. A rule contradicting the schema or the call order is wrong.

---

## 6. Sub-agent decomposition

This task decomposes well: modules and flows are largely independent, which is exactly the condition under which orchestrator-worker beats a single agent. It also isolates context — one subagent per module keeps another module's details from polluting the reasoning.

**Cost check first.** Multi-agent runs cost roughly an order of magnitude more tokens than a single-agent pass. Use it when the repo exceeds what one context can hold with fidelity, not by default.

**Scale effort to scope** (adapt to your budget):

| Scope | Subagents |
|-------|-----------|
| Single flow clarification | 1 (no delegation) |
| One bounded context | 2–4, split by module or by actor |
| Full legacy system | 10+, split by bounded context, plus a synthesis pass |

**Every subagent contract must specify four things.** Omit any one and the subagent drifts, because it cannot tell what "done" looks like:

1. **Objective** — e.g. "extract enforced constraints in `billing/`, passes P1–P4"
2. **Output format** — the exact schema from `references/schemas.md`
3. **Tools and sources** — which paths, which search tools, what is off-limits
4. **Boundaries** — do not follow imports outside the assigned package; do not open questions to the user; return findings only

Subagents return artifacts, never prose summaries. The orchestrator merges into `03-rules.yaml`, de-duplicates by rule statement, and records conflicts as findings rather than resolving them silently.

**Reserve one subagent as adversary** (Phase 7): given the finished rule register and the code, its only job is to find rules with weak evidence, contradicted rules, and flows with no failure-path coverage.

---

## 7. Phase 6 — Asking, briefly

Full protocol and templates in `references/questioning.md`. Three points govern everything:

1. **Never ask what the evidence can answer.** Read first. Questions that reveal you did not look burn the SME's attention, which is the scarcest resource in the run.
2. **Over-asking is a failure too.** Benchmarks for human-in-the-loop agents penalize both excessive questions and missed escalation. Rank by *task relevance × answerability*, then cut to the budget. Fewer, better questions beat exhaustive ones.
3. **Timing: ask after extraction for a flow completes, never during.** Asking early risks asking about what you would have inferred from code you had not read yet.

Default budget: ≤7 blocking questions per bounded context per round. Everything else becomes a recorded assumption with an owner.

Every question ships with a **proposed default answer**. "Today the system does X; I believe it should be Y because Z — confirm or correct" gets answered far more often than "how should this work?"

---

## 8. Stop conditions

Stop and report — do not push through — when:

- Evidence for a bounded context is inaccessible (no repo access, external vendor system, binary-only dependency)
- Blocking questions exceed the budget and no decision owner exists
- Two authoritative sources conflict on a rule that governs money, safety, or compliance
- Your `assumed` lines outnumber your `observed` lines for a flow — you are writing fiction; go get evidence

## 9. Quality gates

Run is complete for a scope when all hold:

- [ ] Every actor in `01-actors.yaml` appears in at least one flow
- [ ] Every flow has ≥1 unwanted-behavior rule per external dependency and per failure point
- [ ] Every rule has an evidence pointer and a status
- [ ] Every rule with >2 conditions has a decision table with no undefined combinations
- [ ] Smell scan clean on all `confirmed` rules
- [ ] Every glossary term has exactly one definition
- [ ] Every hotspot from Phase 3 resolved into a rule, a gap, or a recorded assumption
- [ ] Coverage log lists what was not examined
- [ ] Adversarial pass run and its findings addressed

## 10. Anti-patterns

| Anti-pattern | Failure |
|--------------|---------|
| Single-pass "extract the business logic" | Plausible fiction |
| Priming the search with the expected answer | You find your expectation, not the code |
| Documenting functions instead of rules | A prose mirror of the code, no business meaning |
| Trusting existing docs | Stale docs are the most confident source of wrong answers |
| Holding the model in context instead of on disk | Detail erodes; the run is unresumable |
| Rewriting artifacts wholesale each turn | Domain specifics get compressed away |
| Silently defaulting an unanswered question | The gap disappears instead of closing |
| Asking everything you noticed | Human stops answering; blocking questions get lost in noise |
| Uniform depth everywhere | Depth belongs where risk and change concentrate |
| Shipping a map with no owners | Findings without decision owners are decoration |

---

Sources and further reading: `references/sources.md`.
Human-facilitated variants of each technique (workshops, interviews, session formats) are in `references/questioning.md` §5.
