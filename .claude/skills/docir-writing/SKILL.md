---
name: docir-writing
description: How to write the documents themselves — name each concept the same way everywhere, give one document one purpose, keep it to the current state instead of logging its history, state each fact once and link to it instead of repeating it, and keep sections short enough to retrieve. Load whenever you are about to write, restructure, split or review a docir document's title, description or body. It governs the content; the docir skill governs the CLI.
---
<!-- docir:v0.28.0 — generated file, do not edit by hand; refresh with `docir agent update` after upgrading docir -->

# docir — Writing Rules

These rules are about *what goes in the document*. The other docir skill covers
the commands; this one covers the prose they carry.

They come in two tiers, and both tiers hold the same rules. This skill is
**prevention**: it tells you the rule while you are writing. `docir check` and
`docir lint --deep` are **detection**: they find what slipped through. A finding
should be a rule you already knew, not news.

## 1. One name per concept

Pick one term per concept and use it everywhere — title, description, body,
tags. A concept with two names is two concepts to search: `docir search` matches
words and `docir context` matches meaning, so a synonym splits the results and a
reader finds half the corpus.

- Reuse the vocabulary the store already has. `docir tag list` and
  `docir query --tag auth` are cheaper than inventing a word for something that
  already has one.
- Prefer the name the code uses. A document calling it a "job" while the module
  calls it a "task" costs a translation on every read.
- Renaming is a real edit: title, description, body and tags together.
  `docir tag rename auth authn` rewrites every referencing document, so the
  registry is the cheap half — the prose is the half you have to do.
- Do not introduce a second name for contrast ("the queue, i.e. the buffer").
  Name it once, then describe it.

## 2. One purpose per document

A document's `type` states its purpose: a `decision` records a choice and its
reasoning, an `issue` records a problem, an `architecture` note describes how
something is built. Write that, and nothing else.

Mixing purposes is the most common failure and the most expensive to undo. A
decision that grows operational steps, an architecture note that argues for a
change — each half is then findable only under the other's name, and the two
halves go stale on different clocks.

- About to write "also" or "separately"? That is a second document. `docir add`
  it and link the two.
- Six decisions in one file are six documents. One `--type` cannot be true of
  all of them.
- `docir schema show` lists the types this store actually has. Use the one that
  fits rather than stretching one that does not.

## 3. One point in time

A document says what is true now. Git says what was true before, and says it
better than a body can: `git log -p` over the file shows what moved, when, and
with the commit message explaining why.

So when something changes, **edit the section that is now wrong**. Do not add a
dated section beside it recording the change. That leaves two answers where
there was one, only one of them current, and a reader has to date-sort prose to
work out which — while the stale half keeps being retrieved, because the index
does not know it was superseded.

- `--replace-section` is the edit for something that changed.
  `--append-section` adds a section the document was *missing*: reach for it
  when there is a new subject, not a new day.
- A **terminal state** is not a log entry. An issue's `Resolution` — what closed
  it — is part of what an issue is for, and so is a decision's `Consequences`.
  What is not: `Follow-up (2026-07-26)`, `Delta pass`, `Third round`,
  `What moved since <date>`, `Amendment: …`.
- **A date in a heading is the signal.** Dates *inside* prose are often the
  point — "measured on 2026-08-12" is a fact, and dropping it would weaken the
  claim. A date in the heading means the section is addressed to a moment
  rather than to a subject, and rule 5 says a heading names its subject.
- Replacing a whole document is an edge, not a section:
  `docir update <new> --set-related <old>:supersedes`. Rule 4 says what that
  edge then buys you.
- Superseded text is simply deleted. It is not lost — it is in git, under a
  commit that says why it went.

Measured on a 236-document corpus: 8 documents carried a dated `##` heading, and
the two worst were an open issue and an accepted decision, each about a third
over its type's ceiling. One had grown a section per working session — three
consecutive days of `Follow-up — …` — restating status that the issue documents
it named already owned. None of them had a purpose problem, which is what rule 2
would have caught. They were keeping a diary.

Read `docir lint --deep`'s `scope-creep` with the same care: the threshold is the
**type's** `max_body_chars`, not one number, and a type may set `0` for never. A
register of 47 rules is long because it holds 47 rules, and splitting it in half
gives two half-registers. Size is the symptom; a dated heading is the signal.

## 4. State each fact once, link to the rest

Duplication is what goes stale: two copies, and only one gets updated. docir's
alternative to a copy is a typed edge.

- Link rather than restate: `docir update adr-0007 --set-related adr-0001:depends_on`.
  A reader following an edge gets the current text; a quoted passage freezes on
  the day you pasted it.
- Cite inside the sentence with `[[adr-0001]]`. The published site shows it as
  that document's title as it stands today; `[[adr-0001|the retry budget]]`
  fixes the wording and `[[adr-0001#Consequences]]` points at a section. Write
  the id: a title or a filename resolves as well, but a retitle keeps the file
  and moves the name, and the id is the one spelling that follows both. Inside
  a code span the brackets are text, which is how this bullet exists.
- A prose link is navigation, not an edge. `docir context` follows `related:`
  and the graph checks read nothing else, so when the relationship is real the
  edge still has to exist. `docir check` reports a `[[...]]` that names no
  document as `unresolved-link`.
- Copy only what you would still keep if the source changed — a name, a number,
  a status. Anything you would then have to go and fix belongs behind a link.
- The kinds carry meaning. `supersedes` marks a replacement, `depends_on` a
  reliance, `refines` a narrowing. `docir context` follows `supersedes`
  *backwards* to answer "is this still current?", which prose cannot do.
- Two documents that are nearly the same document are a `docir lint --deep`
  finding (high cosine, no edge between them). Merge them or link them; do not
  leave both.

## 5. Keep sections retrievable

This is the one hard number, and it comes from the index rather than from taste.
docir embeds every `##` section separately, and the model reads about 1,900
characters. A longer section is split mid-paragraph, and the pieces retrieve
worse than either would alone.

- Keep a section under ~1,200 characters — roughly 200 words, or three short
  paragraphs. That is the size docir chunks at, and `docir lint --deep` reports
  each section it had to split, and how much of it no heading can address.
- Give it a heading that names its subject: the heading is what a reader passes
  to `docir get adr-0007 --section "Context"`. "Notes" is not a subject.
- Prefer several short sections to one long one. Short ones are separately
  retrievable; a long one competes with itself.

## 6. Length follows purpose, not a word count

There is no word limit, and round numbers like "under 1,000 words" do not
survive a real corpus — the topic-based documentation standards are explicit
that a topic runs as long as its subject requires and no longer. What is true:
readers scan, and shorter, split pages measure better than long ones.

So bound length with rules 2 and 3, not with counting. A document is too long
when it has started doing two jobs, or when it has started keeping a diary.
`docir lint --deep` warns past ~8,000 characters — read that as "check whether
this is still one document, about one moment", not as a ceiling.

## 7. Write the description for a stranger

The `description` is what every search result shows and what ranking reads. It
is not the opening paragraph of the body.

- One sentence saying what this document decides, reports or describes.
- Do not restate the title, and do not open with context — a reader scanning ten
  results needs the answer, not the setup.
- Move it whenever the body's subject moves:
  `docir update adr-0007 --set-description "..."`.

## Before you finish

- One purpose, and the `type` says which.
- Current state only — nothing dated into the body that git already records, and
  every section that changed *edited* rather than answered beside.
- Every concept named the way the rest of the corpus names it.
- No fact stated here that another document owns — linked instead.
- Every `[[...]]` names a document that exists, and every real relationship is an edge.
- Every `##` section under ~1,200 characters, under a heading worth reading.
- A `description` written for someone who has not read the body.
- `docir check` and `docir lint --deep` run, and every finding understood.
