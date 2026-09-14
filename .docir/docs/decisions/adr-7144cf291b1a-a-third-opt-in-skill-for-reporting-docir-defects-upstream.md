---
code:
- src/docir/modules/agents/infra/templates/feedback/**
- src/docir/modules/agents/domain/targets.py
created: '2026-09-14'
description: Why upstream feedback ships as its own opt-in skill that only drafts
  a report, why it is suggested at every adoption moment but never installed by default,
  and why the agent never files it.
id: adr-7144cf291b1a
related:
- kind: refines
  to: adr-3a2d5ee7bc84
- adr-735ba7f6209b
- adr-6ed847e02fe5
status: accepted
tags:
- agents
- docs
title: A third, opt-in skill for reporting docir defects upstream
type: decision
updated: '2026-09-14'
---

## Context
docir's user is an agent, and when docir itself is the problem the agent's cheapest
move is a local workaround: a wrapper script around a wrong output, a line in
`CLAUDE.md` saying "docir gets X wrong, so always do Y", a hand-edited document, a
pinned older version. Each one is a private fix for a public bug — it keeps working
for that repository, keeps failing for everyone else, and deletes the evidence, so
the next person meets the same defect with nothing written down. Nothing in docir's
surface pushed back on that.

The two existing skills do not cover it. One teaches the CLI, one teaches the prose;
`reference/troubleshooting.md` ends at "upgrade" and "reindex", which is the right
answer only when the installation is the problem.

Reporting is not free for the receiving end either. Maintainers are drowning in
unverified machine-written reports: curl ended a six-year bug bounty in January 2026
after roughly a fifth of submissions were AI slop, Django added an AI-disclosure
clause to its security policy, and the OpenSSF working group's draft practice is two
rules — disclose the tool, and no autonomous agents. A skill that made filing easy
without making it expensive to file *badly* would be a net loss to the project it
reports to.

And the corpus is the user's. A report carries commands, outputs, paths and document
text; docir's security policy is that nothing leaves the machine.

## Decision
Ship a third, opt-in skill: target `claude-feedback` →
`.claude/skills/docir-feedback/SKILL.md`, from its own packaged template
`feedback/`. A catalogue entry plus a file — the shape adr-735ba7f6209b left behind
for exactly this.

**It drafts; it does not send.** The agent writes the issue body to
`<store>/feedback/<date>-<slug>.md` and prints one `gh issue create --body-file`
command. The human runs it. If they ask the agent to run it instead, it may — only
after they have read the draft file, and only the exact command already shown, with
no edit to title or body after approval, because approval is for the text they read.
docir gains no network write path and the module stays a filesystem leaf.

**Opt-in, and suggested at both adoption moments.** It stays out of
`DEFAULT_AGENTS`: a default that drafts reports about its user's corpus is one
nobody consented to, which is where the CLI telemetry-consent norm lands and where
`gh`'s 2026 opt-out flip was rejected. Instead it is suggested — one dim line from
`docir init` and one from `docir agent install`, both in the human renderer only, so
the JSON an agent parses does not move — plus the README quickstart.

**Four gates, and a scratch store.** Current build; reproduced twice, once with
`--no-daemon`; checked against `--help` in case the capability already exists;
checked against the tracker and the published decisions. The reproduction is built
in a throwaway store from synthetic documents, never on the user's corpus, and a
redaction checklist plus a mandatory AI-disclosure line follow.

**The counter-pressure ships even to repos that decline the skill.**
`reference/troubleshooting.md` in the default skill names the workaround signals and
points at `--agent claude-feedback`, so an unequipped agent still stops and tells the
human rather than papering over.

## Consequences
- Chosen cost: a repo that installs it pays a third skill description in every
  session. Same trade as the writing skill, and the same answer — opt-in.
- The suggestion lines are the only part of this that reaches outside the module,
  into `entry_points/cli/rendering.py`. They are deliberately in the Rich renderer
  only; a hint in the JSON would be an agent reading a suggestion meant for a human.
- `.docir/feedback/` joins the store `.gitignore`. A store created before this
  release shows the draft as untracked until `docir init --force` regenerates it.
- Scoped out: a `docir feedback` command. It would put docir in the business of
  composing and transmitting reports, which is exactly what the draft-only shape
  avoids; the CLI's one write path stays the store.
- Scoped out: machine-checking that a workaround was reported. Whether a script is
  a workaround is a judgement call, and a Tier 1 error on it would fail builds over
  prose — the argument the staleness and schema-drift rules already make.
