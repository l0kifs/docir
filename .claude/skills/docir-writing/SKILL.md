---
name: docir-writing
description: How to write the documents themselves — name each concept the same way everywhere, give one document one purpose, state each fact once and link to it instead of repeating it, and keep sections short enough to retrieve. Load whenever you are about to write, restructure, split or review a docir document's title, description or body. It governs the content; the docir skill governs the CLI.
---
<!-- docir:v0.13.1 — generated file, do not edit by hand; refresh with `docir agent update` after upgrading docir -->

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

## 3. State each fact once, link to the rest

Duplication is what goes stale: two copies, and only one gets updated. docir's
alternative to a copy is a typed edge.

- Link rather than restate: `docir update adr-0007 --set-related adr-0001:depends_on`.
  A reader following an edge gets the current text; a quoted passage freezes on
  the day you pasted it.
- Copy only what you would still keep if the source changed — a name, a number,
  a status. Anything you would then have to go and fix belongs behind a link.
- The kinds carry meaning. `supersedes` marks a replacement, `depends_on` a
  reliance, `refines` a narrowing. `docir context` follows `supersedes`
  *backwards* to answer "is this still current?", which prose cannot do.
- Two documents that are nearly the same document are a `docir lint --deep`
  finding (high cosine, no edge between them). Merge them or link them; do not
  leave both.

## 4. Keep sections retrievable

This is the one hard number, and it comes from the index rather than from taste.
docir embeds every `##` section separately, and the model reads about 1,900
characters. A longer section is split mid-paragraph, and the pieces retrieve
worse than either would alone.

- Keep a section under ~1,200 characters — roughly 200 words, or three short
  paragraphs. That is the size docir chunks at.
- Give it a heading that names its subject: the heading is what a reader passes
  to `docir get adr-0007 --section "Context"`. "Notes" is not a subject.
- Prefer several short sections to one long one. Short ones are separately
  retrievable; a long one competes with itself.

## 5. Length follows purpose, not a word count

There is no word limit, and round numbers like "under 1,000 words" do not
survive a real corpus — the topic-based documentation standards are explicit
that a topic runs as long as its subject requires and no longer. What is true:
readers scan, and shorter, split pages measure better than long ones.

So bound length with rule 2, not with counting. A document is too long when it
has started doing two jobs. `docir lint --deep` warns past ~8,000 characters —
read that as "check whether this is still one document", not as a ceiling.

## 6. Write the description for a stranger

The `description` is what every search result shows and what ranking reads. It
is not the opening paragraph of the body.

- One sentence saying what this document decides, reports or describes.
- Do not restate the title, and do not open with context — a reader scanning ten
  results needs the answer, not the setup.
- Move it whenever the body's subject moves:
  `docir update adr-0007 --set-description "..."`.

## Before you finish

- One purpose, and the `type` says which.
- Every concept named the way the rest of the corpus names it.
- No fact stated here that another document owns — linked instead.
- Every `##` section under ~1,200 characters, under a heading worth reading.
- A `description` written for someone who has not read the body.
- `docir check` and `docir lint --deep` run, and every finding understood.
