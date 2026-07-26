# Extraction (Phases 1–2)

- [1. Evidence inventory](#1-evidence-inventory)
- [2. Navigating the codebase](#2-navigating-the-codebase)
- [3. Where rules hide](#3-where-rules-hide)
- [4. The five passes](#4-the-five-passes)
- [5. Rule vs implementation detail](#5-rule-vs-implementation-detail)
- [6. Context discipline](#6-context-discipline)

## 1. Evidence inventory

Rank sources. Higher rank wins on conflict — and every conflict is itself a finding to record in `05-gaps.yaml`.

| Rank | Source | Notes |
|------|--------|-------|
| 1 | Observed production behavior / user work | What people actually do, including workarounds outside the system |
| 2 | Code, DB schema, migrations, constraints | The operational truth and the only complete record |
| 3 | Tests, especially acceptance/E2E | Encoded intent; stale tests still evidence past intent |
| 4 | Config, feature flags, cron and queue jobs | Where "hidden" rules live |
| 5 | Support tickets, logs, error rates, funnel analytics | Where the system hurts people |
| 6 | Stakeholder/SME statements | Intent, but memory- and role-biased |
| 7 | Written docs, tickets, code comments | Claims to verify, never truth |

**Coverage trap:** users typically exercise a small fraction of a system's capability. One user's account is one path. Rare-but-critical flows — year-end close, refund, dispute, chargeback, offboarding, bulk import — are the ones nobody demonstrates and nobody documented.

Log every source you consulted in `99-log.md`, and every one you *could not* consult.

## 2. Navigating the codebase

Two viable strategies. Pick by repo size and by whether the analysis will be repeated.

**Grep-first agentic search** — glob for structure, ripgrep for content, read specific files on demand. Zero setup, exact-pattern precision. Keyword search through agentic tool use has been measured at over 90% of retrieval-augmented performance without any vector store, so the absence of an index is not a reason to skip the work.

**Pre-computed structural index** — tree-sitter/AST symbol extraction plus a call graph, served from a local store. Materially cheaper per query on repeated passes (independent measurements report large tool-call and token reductions on multi-repo work). Worth building when: the repo exceeds a few hundred thousand lines, the analysis will re-run on a schedule, or you are fanning out to many subagents that would each re-grep the same paths.

Hybrid is the default in practice: index for structure and dependency navigation, grep for exact-token lookups, agentic exploration for task-specific discovery.

**Tactics that pay off regardless:**

- Start from the **schema and migrations**. Table names, constraints, enums and nullable columns encode more settled business truth than any service layer.
- Enumerate **entry points** before internals: HTTP routes, CLI commands, queue consumers, scheduled jobs, webhooks. Each is a business trigger.
- Grep for **state**: `status`, `state`, `stage`, `phase`, enums, and every place they are compared or assigned. State machines are where rules concentrate.
- Grep for **thresholds and magic numbers**: numeric literals in conditionals are unwritten business rules almost without exception.
- Read **acceptance/E2E tests as a specification draft**. Test names often state the rule in business language for free.
- Follow the **money and the clock**: currency/amount fields, tax, rounding, timezone conversion, expiry, cutoffs, retention.

## 3. Where rules hide

Rules are never in one place. Check all of these before declaring a flow understood:

- Controllers/handlers (authorization, input shape)
- Service/domain layer (the rules people expect)
- Repository queries, raw SQL, stored procedures, views
- DB constraints, triggers, defaults, unique indexes
- Validation schemas (Pydantic/JSON Schema/DTO annotations)
- Background jobs, cron, queue consumers, retry/dead-letter policy
- Feature flags and per-tenant configuration
- Middleware, interceptors, permission decorators
- Client-side validation that has no server-side counterpart *(always a finding)*
- Data fixtures and seed scripts
- Vendor/integration adapters — mapping code encodes the partner's rules

## 4. The five passes

Separate passes, each grounded in the last. Never collapse them into one prompt.

### P1 — Structural: *what exists?*
Entities, tables and columns, endpoints, jobs, modules, state fields, external integrations.
Output: inventory only. Verifiable line by line. No interpretation.

### P2 — Behavioral: *what does each unit do?*
One plain-language description per unit, describing mechanics.
Output: `unit → description`. No generalization across units yet.

### P3 — Relational: *what calls what, in what order?*
Call chains, data flow, transaction boundaries, ordering guarantees, retry semantics, integration points.
Output: chains + boundaries. Transaction boundaries matter: they define what can be half-done.

### P4 — Semantic: *what business rule does this enforce?*
Candidate rules, each with `file:line`.
Cross-check against P1–P3 before writing: a rule contradicting the schema or the call order is wrong.
Output: draft entries for `03-rules.yaml`, status `assumed`.

### P5 — Intentional: *why would a business want this?*
Hypotheses about purpose, and candidate questions.
Output: every line tagged `inferred`. This pass never produces `observed` content.

**Why the sequencing matters:** each pass is verifiable against the one below it. Jumping to P4/P5 directly removes the ground truth that constrains the abstraction, which is precisely where fabricated rules come from. Bounded, module-sized context per pass matters for the same reason — an overloaded window is where invention starts.

**Also record:**
- **Dead code.** Unreachable logic is not a live rule, but an abandoned rule is worth a question.
- **Special cases.** Per-tenant branches, hardcoded IDs, `if customer_id == …`. Each is a candidate `unusual` gap.
- **Missing counterparts.** Client validation with no server rule; a `create` with no `delete`; an enum value never assigned.

## 5. Rule vs implementation detail

Translate every candidate into this shape:

```
actor / trigger / precondition / decision / outcome / exception
```

If `outcome` cannot be stated in business terms, it is not a business rule — drop it or log it as a technical note. If `actor` is unknown, that is a question. If `exception` is empty, that is a gap (see `gap-checklists.md`).

## 6. Context discipline

- Write findings to `analysis/` after each module, not at the end of the run.
- Update artifacts **item by item**. Full-file rewrites compress detail away over successive turns; treat each artifact as an itemized list that grows and gets patched.
- When a subagent finishes, merge its file output — do not paste its raw transcript into your context.
- On compaction, preserve: the frame, open questions, and the coverage log. Everything else is reconstructible from `analysis/`.
