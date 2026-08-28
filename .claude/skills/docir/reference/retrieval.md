<!-- docir:v0.21.0 — generated file, do not edit by hand; refresh with `docir agent update` after upgrading docir -->
# Retrieval beyond `docir context`

The four read commands in [`SKILL.md`](../SKILL.md) answer most questions. This
file is for the ones they do not: structured queries, steering the ranking,
finding out why a result placed where it did, reading other repositories, and
measuring whether retrieval is any good on this corpus.

## Contents

- Structured queries (`query --expr`) — a JMESPath expression over a document and its edges
- Retrieving with a hypothetical answer (`--also`) — when it helps and when it costs you
- Explaining a ranking (`--explain`) — why this hit outranked that one
- Other repositories' decisions — peer stores, and why writes never federate
- Measuring retrieval (`docir bench`) — scoring this store against tasks you know the answers to

## Structured queries (`query --expr`)

**`query --expr` asks what the flags cannot.** A JMESPath expression over each document: its
own fields, plus its edges resolved in both directions with the other document's type and
status on each. A truthy result keeps the document, and it is applied before `--limit`, so the
limit counts matches.

```bash
docir query --expr "stale && owner == `null`"            # overdue and unowned
docir query --type issue --expr "related[?status=='superseded']"
docir query --expr "length(related_by[?kind!='relates_to']) == \`0\`"
```

Fields: `id type status title description tags owner verified created updated archived stale
code`, plus `related` (outgoing) and `related_by` (incoming), each entry
`{to, kind, type, status}`. Reach for it when a question needs two facts at once, or a fact
about a *neighbour*; the plain flags are cheaper for anything they already cover.


## Retrieving with a hypothetical answer (`--also`)

**You write the rewrites; docir writes none.** `--also` takes another phrasing of the same
need, repeatable, retrieved alongside the task and fused with it. docir ships no generative
model precisely because you are one and you have read the code (adr-27c63ad02695).

The case that pays is a hypothetical **answer**. A question and an answer do not look alike to
an embedder — "how do clients authenticate" sits nowhere near "clients present a short-lived
bearer token" — so searching with the answer's *shape* is what finds the document:

```bash
docir context "how do clients authenticate" \
  --also "Clients present a short-lived bearer token issued by the identity provider."
```

**Use it when you could defend the answer you are guessing.** Measured on docir's own corpus:
a *correct* hypothetical takes recall@5 from 0.88 to 1.00, a confident *wrong* one — fluent, in
the right register, about the wrong part of the system — takes it to 0.75. Queries take turns
filling the result rather than pooling their scores, so your task always holds its share and a
bad phrasing costs a bounded slice instead of the whole read (adr-4c21693aac55).

So: reach for it when you know roughly what the answer says and only its wording is uncertain —
you have read the code, or the topic is one you have already retrieved once. If you are
exploring and could not say what the document will claim, send the task alone. One or two
phrasings; five paraphrases of one question retrieve five times and fuse noise.


## Explaining a ranking (`--explain`)

**When a result looks wrong, ask why with `--explain`.** `docir context "<task>" --explain`
attaches the trace behind each hit: where it placed in the full-text and vector rankings, each
RRF term, the raw cosine, and — for a graph-reached document — the seed it came from and
whether that edge was a `successor`, an ordinary `related` or a `mention`. `docir search
"<text>" --explain` gives the thinner version: rank and BM25.

It answers the question `--min-score` cannot: not "is anything relevant here" but "why did *this*
outrank *that*". A hit with a `semantic_rank` and no `lexical_rank` shares no vocabulary with
your wording and was found by meaning alone; the reverse means the embedder contributed nothing.
Off by default — it is a diagnostic, and a skeleton read is meant to be cheap.

## Other repositories' decisions

If `.docir/stores.yaml` exists, this store reads peers alongside its own, and
`context`, `query`, `search` and `get` already cover them — every row carries a
`store` field naming where it came from, and a `store_description` when that
store says what it is. Read the description before you weigh the hit: it is what
tells you whether another repository's corpus governs the thing you are doing.
Add a peer for a single command with `--store ../platform/.docir`.

A store describes itself, once, in its own `stores.yaml` beside the peers it
reads. Write one for the repository you are in when it federates — every reader
pointing at it sees that line on every row it answers:

```yaml
description: Platform decisions every service must follow.
stores:
  - ../platform/.docir
```

Keep the `stores:` key even when the store reads no peers — write `stores: []`.
docir 0.20.0 and earlier refuse a `stores.yaml` without it, so a
description-only file takes `context`, `query`, `search` and `get` down for
anyone in that repository who has not upgraded.

Writes never federate: `add` and `update` always land in this repo's store, and
so does everything `check` reports. Neither does `docir build` — a published
site is this store's corpus, because a copy of a peer's decision goes stale the
moment that repo edits it. If a peer is unreadable docir says so on
stderr and answers from the rest — treat that as information, not as a failure
to retry.


## Measuring retrieval (`docir bench`)

`docir bench <fixture.yaml>` scores this store's retrieval against tasks whose answers you
  already know. Reach for it when someone asks whether `docir context` is any good on *this*
  corpus, when you have changed something that affects ranking, or before reporting that
  retrieval is underperforming — the answer should be a number you produced.

  **Collect the ids first.** A fixture judges document ids in this store, so run
  `docir query --limit 200` or `docir search "<topic>"` and read the real ids out of the
  result before writing anything. Never invent one that looks plausible: `bench` cannot find a
  document that does not exist, so it reports the id under `unresolved`, drops the task, and
  the run measures nothing.

  Then write a YAML file — a list of tasks, each naming the documents a reader would actually
  need. Ids, not paths, so it survives a retitle and a retype:

  ```yaml
  - id: T01
    task: how do clients authenticate against the API
    relevant: [adr-3f9a2b1c7d4e, issue-90aea6d1b891]
  - id: T02
    task: what happens when the payment gateway times out
    relevant: [adr-0a1b2c3d4e5f]
  ```

  Judge tightly: a document is relevant when *not* reading it would change what you write, not
  when it merely shares a topic. Pass the path — `docir bench fixture.yaml` — and read the
  three rows against each other. `context` is the shipped read path; `context --expand 0`
  removes graph expansion, which lifts every embedder and hides the difference between them,
  so the pair is what shows whether the *semantic* half is working; `search` is full-text
  alone, the floor anything semantic must beat.

  A measurement, not a check. It always exits 0, and a fixture is one annotator's opinion of
  what is relevant — do not gate CI on it.
