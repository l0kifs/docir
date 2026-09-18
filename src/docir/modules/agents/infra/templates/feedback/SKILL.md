---
name: docir-feedback
description: Report a docir defect or a missing docir capability back to the docir project instead of working around it. Load when a docir command fails, answers wrongly, or cannot do what the task needs — and especially before you write a wrapper script, a local rule, a pinned old version or a hand-edited file to route around docir. Drafts the report as a local file; a human reviews, redacts and files it. This skill never sends anything anywhere.
---

# docir — Reporting Upstream

docir is someone else's project. You are working in a repository that *uses* it, so
when docir misbehaves or cannot express what the task needs, the durable fix is a
report to the docir project — not a patch to this repo's habits.

This skill produces a **draft on disk**. It does not file anything, and neither do
you: a human reads the draft, decides what leaves the machine, and runs the one
command that publishes it. Nothing in this skill is a reason to send data anywhere.

## Unblock them first, then report it

Your job does not change because the fault is docir's. Give the user the working answer
they came for — the wrapper, the flag, the rule — and then say what it is. Withholding
a workaround helps nobody: the person in front of you stays blocked, and no maintainer
is better off for your refusal.

What you must not do is ship it **silently**. A workaround nobody reports keeps working
for this repo, keeps failing for everyone else, and deletes the evidence — the next
person meets the same defect with nothing written down.

So when you catch yourself writing one of these, write it *and* flag it as a **report
trigger**:

- writing a shell wrapper, alias or script that fixes up docir's output
- hand-editing `.docir/docs/*.md` because a flag is missing (already forbidden)
- adding a line to `CLAUDE.md` / `AGENTS.md` / a project rule saying "docir gets X
  wrong, so always do Y instead"
- pinning an older docir, or avoiding a command, because of a regression
- reading or rewriting `index.db`, or rebuilding your own index beside it
- keeping a second source of truth (a scratch markdown file, a spreadsheet)
  because docir cannot hold something
- retrying a command with different wording because it "sometimes fails"

The workaround is also evidence: the feature-request form asks for it by name — "what
you do today instead".

## Four gates — on the filing, never on the helping

These decide whether a report is worth a maintainer's time. They gate what you *file*;
they never gate the answer you owe the user. If you cannot run them here — no shell, no
network, or the user only asked a question — name the ones still outstanding, hand over
the draft anyway, and let the human close them. "I could not verify it, so I will not
help" is never the right answer.

1. **You are on the current build.** `docir self status --refresh | cat`. If a newer
   release exists, say so and do not file — a bug fixed two releases ago is not a
   report. After an upgrade, reproduce again.
2. **You reproduced it twice, once with `--no-daemon`.** A daemon holding old code
   answers from it, and a stale answer looks exactly like a correct one.
3. **docir cannot already do it.** `docir --help | cat` lists every command and
   each command's own help does the same for its flags (`docir context --help | cat`);
   both return JSON. Read them before claiming something is missing — most "missing"
   capabilities are a flag under another name.
4. **It is not already reported or already decided.** Search the tracker
   (`gh issue list --repo l0kifs/docir --state all --search "<terms>"`, or the issues
   page), and check docir's published decisions at
   <https://l0kifs.github.io/docir/index.html> — docir records what it deliberately
   did *not* build, and re-proposing it without answering the recorded reasoning is
   noise.

## Reproduce on a scratch store, never on this corpus

The report leaves this machine; your corpus must not. Rebuild the failure in a
throwaway store with synthetic documents:

```bash
export DOCIR_HOME=$(mktemp -d)/scratch     # a throwaway store, outside every repo
docir add --type decision --title "Alpha" --description "First." --body "Text."
docir context "alpha" --min-score 0.5      # the failing command, here, with its output
unset DOCIR_HOME                           # back to this project's store
```

There is no `init` step, and adding one is a mistake with teeth: the store is
created by the first write, while `init` resolves against the *current directory*
and would re-initialize the store you are working in.

If the failure needs the *shape* of your real data, reproduce the shape, not the
data: "a body with two `##` sections of ~4,000 characters and three `[[...]]` links",
built from synthetic text. If it will not reproduce on a scratch store, that is a
finding worth reporting too — say exactly that, and describe the shape you could not
recreate. Keep the default embedder unless the bug is *about* the embedder; it
changes ranking.

## Which channel

| What you have | Where it goes |
|---|---|
| A reproducible defect | Issue, bug report form |
| A capability that blocked a real task, with the workaround it cost | Issue, feature request form |
| An idea, a preference, a "would be nice" with no blocked task | Discussions → Ideas |
| A question about using docir | Discussions → Q&A |
| Anything exploitable | **Private advisory only** — never a public issue, never a reproduction in chat |

One report is one defect. Seven findings are seven reports, or — more often — one
report and six things you have not verified yet.

## Draft the file

Write the body to `<store>/feedback/<YYYY-MM-DD>-<slug>.md`. Read `<store>` from
`store.home` in `docir doctor | cat` — with `DOCIR_HOME` unset, so it names this
project's store and not the scratch one. (`doctor` answers in an empty store, which
is why it is the source here and a `store` field on a result list is not: a query
that matched nothing carries no path.) That directory is gitignored by stores created
with this release, and `docir self upgrade` adds the entry to an older store without
touching the lines already in the file. If the draft still shows up in `git status`,
say so to the human before writing anything else into it — it is the one thing in the
store nobody has reviewed for redaction.

The file holds the **issue body and nothing else** — no title line, no shell command,
no notes to the human — so it can be filed verbatim. Mirror the form's fields as `##`
sections, because filing from a file bypasses the web form and the maintainer still
needs every field:

````markdown
## What happened

```console
$ docir context "alpha" --min-score 0.5 | cat
[]
```

## What you expected instead

The two graph neighbours to survive `--min-score`, which filters `similarity`.

## docir version

0.26.0

## How docir is installed

```json
{"method": "uv-tool", "version": "0.26.0", ...}
```

## Does it still happen with `--no-daemon`?

Yes — same result.

## Which embedder / which store / OS and Python

Default model · a scratch store created for this report · macOS 15.6, Python 3.12.4

## What `docir check` reports

```json
[]
```

## Reproduction

<the exact scratch-store commands above, runnable top to bottom>

---
Drafted by an AI coding agent from a reproduction on a scratch store, and reviewed by the person filing it before submission.
````

That last line is part of the body, not decoration — see "Disclose that an agent wrote
it" below.

For a feature request the sections are: **The problem** (the task docir blocked,
not the feature you want), **What you do today instead** (the workaround and what it
costs), **What you would like docir to do** (written as you would type it, if you
have a shape in mind).

Include a localization cue — a file, a function — only if you read the installed
source and checked it. If you did not, write "not investigated". A guess dressed as
analysis is the single fastest way to get reports from this repo ignored.

## Redact before you hand it over

Go through the draft line by line. Remove or replace:

- **Corpus content** — document titles, descriptions, bodies, tags, ids, filenames,
  headings. Replace with the synthetic equivalents from the scratch store.
- **Paths** — `~/` for home, and nothing below it that names a client, a product or a
  person. `docir self status`, `docir doctor` and every error message print store
  paths; scrub them.
- **People** — owners, reviewers, authors, emails, handles. "the owner", not a name.
- **Your project** — repo names and URLs if the repo is private, hostnames, internal
  service names, ticket ids and their URLs.
- **Config** — a customised `docs-schema.yaml` names your internal vocabulary in its
  types, statuses and tags; reduce it to the minimum that reproduces. `stores.yaml`
  names peer stores — drop it unless federation is the bug.
- **Environment** — variable values, tokens, anything that looks like a credential
  even if you believe it is inert.

Then reread it as a stranger: could anyone tell which company, product or person this
came from? If yes, keep cutting. Screenshots are not accepted anyway — paste JSON.

## Disclose that an agent wrote it

End every body with one line, verbatim:

```text
---
Drafted by an AI coding agent from a reproduction on a scratch store, and reviewed by the person filing it before submission.
```

Maintainers are drowning in unverified machine-written reports and several projects
now require this disclosure. It is also the honest description of what happened.

## Hand it over, and stop

Tell the human, in this order: what the defect is in one sentence, the draft's path,
what you redacted, and the exact command they can run:

```bash
gh issue create --repo l0kifs/docir \
  --title "context: --min-score drops graph neighbours" \
  --label bug \
  --body-file .docir/feedback/2026-09-14-min-score-neighbours.md
```

Without `gh`: open <https://github.com/l0kifs/docir/issues/new/choose>, pick the form,
and paste each section into the matching field.

Then stop. **The human runs that command.** If they explicitly ask *you* to run it,
you may — but only after they have read the draft file, and you run exactly the
command you showed them, with no edit to the title or body after their approval.
Approval is for the text they read, not for a text you improved afterwards.

If they say no, or say nothing: the report is not filed. Delete the draft or leave it,
as they prefer, and do not raise it again this session.

## What is not a report

- Something you have not reproduced, or reproduced only once.
- Behaviour you believe is wrong because the docs suggest otherwise — read that
  command's own `--help` first; if the help is wrong, *that* is the report.
- "Slow" without two timings and the corpus size.
- A wish with no blocked task behind it. That is a Discussion.
- A defect in this repo's own use of docir — a bad schema, a broken edge, a stale
  document. Those are yours to fix, and `docir check --fix` closes most of them;
  `docir doctor` covers the environment half.
