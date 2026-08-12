# Retrieval benchmark

docir makes two load-bearing claims: it finds the right documents, and it is cheap for an
agent to read. Neither was measured anywhere in this repo, so every retrieval constant —
the 25-candidate FTS pool, the RRF `k=60`, the 0.9 similarity threshold, the default
`--limit 5` — was chosen without evidence, and there was no way to tell whether a change
helped. This is that evidence.

```bash
uv run python benchmarks/run.py                                  # default: the real model
DOCIR_EMBEDDER=deterministic uv run python benchmarks/run.py     # model-free fallback
```

It builds a throwaway store from `corpus.yaml` (26 documents from a plausible payments
service), runs the 20 tasks in `tasks.yaml` through each retrieval strategy, and reports
recall, precision, MRR and the size of the payload an agent receives.

**It is a measurement, not a test.** It prints numbers and exits 0. Do not wire a
threshold around it until the numbers below are understood and stable.

## Results

`recall@5`, 26 documents, 20 tasks. Confirmed 2026-08-06 on docir 0.10.0.

| strategy | `deterministic` fallback | default (`fastembed`) |
|---|---|---|
| `context` | 0.80 (MRR 0.76) | **0.97 (MRR 0.97)** |
| `context --expand 0` | 0.78 | 0.88 |
| `search` (lexical only) | 0.86 (MRR 0.79) | 0.86 (MRR 0.79) |

Split by how the task is worded — the "paraphrased" tasks deliberately share **no
vocabulary** with the documents they need:

| strategy | same words | paraphrased |
|---|---|---|
| `context`, `deterministic` fallback | 0.95 | 0.65 |
| `context`, default (`fastembed`) | 1.00 | **0.95** |
| `search` | 0.92 | 0.80 |

> **Re-based 2026-08-03 — do not compare against figures printed between 2026-07-27 and
> that date.** The corpus grew to 26 documents and 20 tasks when per-section embedding
> landed: the old one had almost nothing longer than the model's window, so the change it
> was written to measure was invisible in it. The previous baseline (23 documents, 14
> tasks) read `context` 0.96 / `search` 0.83. Not wrong — a different denominator.
>
> The paraphrased column moved most, and that is the point of the growth: the fallback
> drops to **0.65** there against the model's 0.95, where the old corpus had them at 0.93
> apiece. A corpus where the two embedders tie on paraphrase was not testing paraphrase.

> **Re-based 2026-07-27 — do not compare against figures printed before this date.**
> The corpus gained a superseded decision pair and a closed issue (23 documents, 14
> tasks); the previous baseline was 20 documents and 12 tasks. The old numbers were
> `context` 0.88 / 0.96 recall@5, `search` 0.85. They are not wrong, they are a
> different denominator. The reason for the change is in §2 below.
>
> Separately: every run before this date printed `embedder: deterministic (default)`
> regardless of what it used. The label was a hardcoded fallback string that was not
> updated when the default flipped to `fastembed` in 0.3.0, so the runs recorded as
> "default" were in fact `fastembed`. The harness now prints the resolved model id.

### 1. This is why the model is now the default

Compare at `--expand 0`, which removes graph expansion and leaves only the ranking:

| `context --expand 0` vs `search` (0.86 recall, 0.79 MRR) | recall@5 | verdict |
|---|---|---|
| `deterministic` fallback | 0.78 | **worse than plain full-text search** |
| default (`fastembed`) | 0.88 | +0.02 |

The fallback does not merely fail to add meaning — it ranks *below* the lexical index it
is supposed to be complementing, because it is measuring the same signal with less
precision. That is what moved `fastembed` from an optional extra to a hard dependency;
the hashing embedder remains available as `DOCIR_EMBEDDER=deterministic` for installs
that cannot carry ~240 MB of dependencies and a ~64 MB model.

Full `context` numbers understate this, because graph expansion lifts both embedders —
quote the `--expand 0` row when the question is about embedders. On the current corpus it
no longer matters which row you quote: the fallback's full `context` (0.80) is *below*
plain `search` (0.86), so expansion is not enough to rescue it.

That is not a surprise once you read `DeterministicEmbedder`: it is signed feature
hashing over tokens, so it scores similarity by *shared vocabulary*. Two sentences that
mean the same thing in different words score **0.000**:

```
0.000  'duplicate charges when the customer double-clicks pay'
       vs 'idempotency keys for payment capture'
```

So under that embedder both halves of the "hybrid" ranking measure the same lexical
signal — which is what the README used to promise as "retrieval by meaning".

### 2. Graph expansion earns its place — and it is why the corpus was re-based

`context` beats `context --expand 0` by **+0.09** recall under `fastembed` and **+0.02**
under the fallback, and it costs *fewer* tokens than expanding nothing (484 vs 512), since
a neighbour that fills a slot is a skeleton like any other. The relation graph is doing
real work, and the default `--expand 2` looks about right.

The fallback's margin is the one that moved — +0.13 before the 2026-08-03 re-base, +0.02
after. Expansion can only reach a document from a hit, and on a corpus with real
paraphrase the fallback produces too few hits to expand from. Graph traversal amplifies
ranking; it does not substitute for it.

The margins were +0.07 on the corpus before that, and the increase is the point. It had
**no `supersedes` edge and no document in an inactive status**, so the two behaviours
`context` depends on most were invisible here: a change to either moved no number at all.
Two graph fixes landed on 2026-07-27 — graph-reached neighbours now obey the same
closed-work filter as ranked hits, and expansion follows `supersedes`/`contradicts`
*backwards* so a hit carries the decision that replaces it — and against the old corpus
both were unmeasurable. Against this one:

| `context` recall@5 (23-document corpus, 2026-07-27) | before the fixes | after |
|---|---|---|
| default (`fastembed`) | 0.93 (prec 0.37) | **0.96 (prec 0.39)** |
| `deterministic` fallback | 0.89 (prec 0.36) | **0.93 (prec 0.37)** |

Those two rows are kept at their original denominator on purpose: they measure a change
that was made and verified against that corpus, and re-running them here would compare a
fix to a corpus it never saw.

Recall *and* precision move together, which is what you would expect: the successor
arrives (recall) and the resolved issue stops taking a slot (precision).

`adr-sessions-redis` is deliberately left `accepted` rather than `superseded` — the case
where someone wrote the replacement and linked it but never went back to close the old
document. A correctly-superseded document is filtered from `context` by status anyway, so
it can demonstrate nothing about traversal.

### 3. The token claim holds, with a number

Mean payload an agent reads, per task (~4 chars/token):

| what the agent does | ~tokens | vs `context` |
|---|---|---|
| `docir context` | **484** | 1× |
| `docir query` (all skeletons) | 2 199 | 4.5× |
| read every document body | 6 625 | 13.7× |

On a 26-document corpus. The ratio grows with corpus size, since `context` is bounded by
`--limit` and the others are not — it went from 8.3× to 13.7× when the corpus gained three
long documents, which is the shape of the claim rather than a number to quote absolutely.

Of that, **12 tokens are `matched_section`** — measured by suppressing the field and
re-running on this same corpus (484 vs 472), not by comparing against the 464 printed
before the re-base, which would be reading a corpus change as a feature's cost. Recall,
precision and MRR are bit-identical with and without it, which is what you want from a
field that only names where the match was: a heading, against a body fetch saved.

> **Re-based 2026-07-30 — the token column only.** The harness used to build its store with
> the bare schema default (`sequential`, `adr-0007`), while `docir init` gives every real
> project `random` ids (`adr-3f9a2b1c7d4e`). It was pricing a configuration nobody runs and
> understating every token figure by four characters per id. Recall, precision and MRR are
> unaffected and unchanged.

### 3b. What the random-id entropy costs, and what it buys

issue-7a271eb0f21a: a random id is ~3× the length of a sequential one and appears in every skeleton
and every `related` edge of every result, and nothing measured the trade — so 48 bits was
chosen by default rather than deliberately. Both halves are now measured.

| what the agent does | ~tokens | id chars | share | as `adr-0007` | saving |
|---|---|---|---|---|---|
| `docir context` | 484 | 137 | 7.1% | 72 | 3.4% |
| `docir search` | 462 | 142 | 7.7% | 74 | 3.7% |
| `docir query` (all skeletons) | 2 199 | 698 | 7.9% | 362 | 3.8% |

Odds that any two ids collide, by suffix length:

| suffix | bits | 100 docs | 1 000 | 10 000 | 100 000 |
|---|---|---|---|---|---|
| 4 hex | 16 | 7.35% | 99.95% | 100% | 100% |
| 6 hex | 24 | 0.03% | 2.94% | 94.92% | 100% |
| 8 hex | 32 | 0.00% | 0.01% | 1.16% | 68.78% |
| **12 hex (current)** | **48** | <0.01% | 0.00% | 0.00% | 0.00% |
| 16 hex | 64 | <0.01% | <0.01% | <0.01% | <0.01% |

**48 bits stays.** Random ids cost 3.4% of a `context` payload over sequential ones — that
is the price of two branches never minting the same id, and it is small. Dropping to 32
bits would return about 1% of the payload and buy a 1.16% chance of a collision by ten
thousand documents; a duplicate id is the failure mode `docir check --strict` exists to
catch at merge time, and trading a permanent 1-in-86 risk for 1% of a result set is a bad
deal. The two tables have to be read together: the collision number is a one-off risk at
merge, the id cost is paid on every read.

One earlier measurement, kept because the *ratio* is what it says and that has not moved:
`context` grew from 428 to 448 tokens (+4.7%) when `similarity` was added to ranked hits —
the field that makes `--min-score` possible and lets an agent tell a real match from the
best of a bad set. Both figures are from the sequential-id baseline, so they sit below the
table above rather than contradicting it. The cost lands only where the field is set:
`search` and `query` did not move, because their results carry no similarity and trimming
drops it. `--expand 0` grew slightly more (+25) than full `context` (+20), since a
graph-reached neighbour has no similarity either — the more the graph contributes, the less
the field costs.

## Federation: what a split corpus costs (`federation.py`)

```bash
uv run python benchmarks/federation.py
```

A second harness, answering a different question: reads federate across stores
(adr-fb938175f72a), so what does splitting a corpus cost, and which merge should pay it?
It builds the same corpus three ways — whole, and alternately halved into two stores —
and asks every task of all three.

| strategy | recall@5 | MRR |
|---|---:|---:|
| single store (the ceiling) | 0.97 | 0.97 |
| split · merge on **similarity** | 0.91 | 0.93 |
| split · merge on rank (cross-store RRF) | 0.88 | 0.72 |

*26 documents, 20 tasks, k=5, `bge-small-en-v1.5`, 2026-08-12.*

**Cross-store RRF is round-robin, not a simplification of it.** RRF sums `1/(k + rank)`
over the lists a document appears in; each document lives in exactly one store, so every
sum has one term and the order is rank position alone. Ordering by `similarity` — the raw
cosine, the one number comparable across stores — wins on both metrics and by 21 points of
MRR, which is the number that says whether the right document arrived first.

The ~6 points of recall a split costs are mostly the *graph*, not the ranking: 8 of the
corpus's 17 edges cross the split, and an edge cannot cross stores because Tier 0
validates a `related` target locally. That is the price of federating at all.

## What this does not tell you

- **Single-annotator ground truth.** The judgments in `tasks.yaml` were written by the
  same author as `corpus.yaml`. It measures whether retrieval finds what that author
  considers relevant — weaker than judgments from someone who did not write the corpus.
- **Both rows come from the same corpus and judgments**, so they compare embedders, not
  absolute quality.
- **26 documents is small.** Differences of ±0.05 across 20 tasks are not significant.
  Treat the ordering as the signal, not the decimals.
- **The corpus is synthetic and coherent.** A real repository has half-written documents,
  duplicated decisions and inconsistent vocabulary. Expect worse numbers.
- **Stem overlap leaks into the "paraphrased" set.** FTS5 uses a Porter tokenizer, so
  `paying`/`payment` still match. The paraphrased tasks are harder for a lexical matcher,
  not impossible for it — which is why `search` scores 0.80 there rather than 0.
- **Nothing here measures whether retrieved context changed what an agent did.** That is
  the outcome the product actually exists for, and it needs a different instrument.

## Adding to it

Add a document to `corpus.yaml` (`key` is a stable handle; the real id is allocated at
load time, so judgments survive an id-style change). Add a task to `tasks.yaml` with the
keys a reader would genuinely need, and set `lexical:` honestly — a task that reuses the
document's wording belongs in the easy half.

Corpus documents can also carry:

- `related: [key, key:kind]` — a typed edge (`docir get adr-599055502f0e`).
  A bare key is `relates_to`.
- `status_path: [accepted, superseded]` — legal transitions walked in order, applied after
  the edges are written. It is a path rather than a value because the schema's state
  machine has to be traversed (`decision` starts at `proposed`), and walking it keeps the
  corpus one the real CLI would accept rather than one forced with `--override`.

**Adding either changes every number here.** Re-run both embedders, update the results
table and the date, and say in the same commit that the baseline moved — a reader
comparing across a silent re-base draws a conclusion about code from a change in the
denominator.
