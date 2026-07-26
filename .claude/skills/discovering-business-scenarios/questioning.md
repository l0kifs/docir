# Asking the User (Phase 6)

- [1. Rules of engagement](#1-rules-of-engagement)
- [2. Budget and ranking](#2-budget-and-ranking)
- [3. Question shape](#3-question-shape)
- [4. Templates](#4-templates)
- [5. Human session formats](#5-human-session-formats)
- [6. Closing a question](#6-closing-a-question)

## 1. Rules of engagement

1. **Never ask what the evidence can answer.** Read the code first. A question that reveals you did not look costs credibility and burns the scarcest resource in the run — the SME's attention.
2. **Detect underspecification separately from acting on it.** Complete the extraction passes for a flow, collect all uncertainty, *then* decide what to ask. Interleaving question-asking with exploration produces questions about things you would have learned two files later.
3. **Over-asking is a failure mode, equal to not asking.** Human-in-the-loop evaluations penalize both excessive questioning and missed escalation. The target is few, high-value questions — measured work shows well-chosen question sets outperform larger ones.
4. **Rank by relevance × answerability.** A question the recipient cannot answer is wasted regardless of how important the gap is. Route it to someone who can, or convert it to an assumption.
5. **Batch by owner and by flow**, not by discovery order.
6. **Always propose a default.** Never send an open-ended "how should this work?" when you can send "today it does X; I believe it should be Y because Z."
7. **Ask about the exception, not the rule.** People narrate the happy path automatically. Ask "when does this *not* apply?" and "when did this last go wrong?"
8. **Record authority.** Who answered, when, and whether they are entitled to decide.
9. **Never invent an answer.** Unanswered stays `open`. If work must continue, record `assumed:` with an owner and a review trigger.
10. **Never block the whole run on one unknown.** Assume, mark, move.

## 2. Budget and ranking

Default: **≤7 blocking questions per bounded context per round.**

```
rank = severity(gap) × answerability(recipient) ÷ cost_to_answer
```

Send the top N within budget. Everything below the line:

- becomes a recorded assumption with an owner, or
- stays in `05-gaps.yaml` at `status: open` for the next round

If more than ~15 gaps qualify as blocking in one context, that is itself the finding: report it as *"this area is not specified"* rather than shipping a questionnaire.

**Timing.** Ask at the end of a flow's analysis, not mid-exploration. Asking too early risks querying about information inferable from context you have not yet read. Asking too late means you already built on a guess.

## 3. Question shape

Every question record carries:

- the gap it resolves
- what the system does **today**, with evidence
- a **proposed answer**
- why it is blocking (or not)
- who should answer it
- observed frequency/impact, if available

Prefer closed or multiple-choice form. Open questions get deferred; closed questions get answered.

## 4. Templates

**Missing scenario**
> In flow `<F>` at step `<S>`, if `<condition>` occurs, no behavior is defined. Today the system `<errors / does nothing / silently drops>` (`<file:line>`). What should happen? Who is affected, and how often does this occur?

**Unclear rule / unexplained constant**
> The code enforces `<rule in EARS>` (`<file:line>`). I found no stated reason for `<threshold / exception / special case>`. Is it intentional, what is the business justification, and does it vary by `<tenant / region / product>`?

**Conflict**
> `<Source A>` says `<X>`; `<Source B>` says `<Y>`. Which is authoritative today? When did the other become wrong? Do records created under the old rule still need it?

**Unusual behavior**
> `<Component>` special-cases `<case>` (`<file:line>`). It appears in no requirement and no test. Is it still needed? What breaks if it is removed?

**Actor need**
> When `<actor>` is doing `<activity>` and `<situation>` occurs, what do they need? What do they do today when the system does not provide it?

**Off-system workaround**
> `<Actor>` appears to use `<spreadsheet / email / manual DB edit>` at step `<S>` — evidence: `<runbook / ticket / admin endpoint>`. Why? What would have to be true for this to happen inside the system?

**Boundary**
> For rule `<R>`, what happens exactly at the limit, one below, one above, at zero, at negative, at null, at maximum, and across a timezone/period boundary?

**Ownership**
> Rule `<R>` has no identified decision owner. Who is entitled to change it?

**Assumption confirmation** (use when out of budget)
> I am proceeding on the assumption that `<A>`, based on `<evidence>`. Correct me if wrong; otherwise no action needed.

## 5. Human session formats

When a human is facilitating rather than an agent, or when the agent's questions warrant a live session:

| Need | Format |
|------|--------|
| Broad cross-silo domain discovery | Big-Picture EventStorming, 15–30 participants |
| One end-to-end process incl. variants | Process-modelling EventStorming, small mixed team |
| Clarify one flow before building | Example Mapping / Three Amigos, ~25 min timebox |
| Individual expert knowledge | Structured interview |
| How the work is *actually* done | Observation / shadowing — surfaces what interviews never do |
| Broad but shallow validation | Survey |
| Confirm the reconstruction | Walkthrough review of the flow map and rule register with SMEs |

Standard sequence: **prepare → conduct → confirm.** Elicitation results are not valid until the source agrees with your written version of them. An agent-produced rule register is a draft until an SME signs off on it.

Shadow **several** users across roles. One user's account covers one path through the system.

## 6. Closing a question

On answer:

1. Update the question record: `answered`, `authority`, `answer`.
2. Update the corresponding rule to `confirmed`, or write the new rule.
3. Update the gap: `resolved` (with the decision) or `accepted` (known and deliberately unaddressed).
4. Re-run the affected coverage checklist — a new rule usually opens new failure paths.
5. Add examples for the new rule, including boundaries.

An answered question that produces no artifact change means the question was not worth asking; note it and tighten the next round's ranking.
