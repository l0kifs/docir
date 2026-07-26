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

It builds a throwaway store from `corpus.yaml` (20 documents from a plausible payments
service), runs the 12 tasks in `tasks.yaml` through each retrieval strategy, and reports
recall, precision, MRR and the size of the payload an agent receives.

**It is a measurement, not a test.** It prints numbers and exits 0. Do not wire a
threshold around it until the numbers below are understood and stable.

## Results, 2026-07-26

`recall@5`, 20 documents, 12 tasks.

| strategy | `deterministic` fallback | default (`fastembed`) |
|---|---|---|
| `context` | 0.88 (MRR 0.78) | **0.96 (MRR 0.94)** |
| `context --expand 0` | 0.81 | 0.89 |
| `search` (lexical only) | 0.85 (MRR 0.81) | 0.85 (MRR 0.81) |

Split by how the task is worded — the six "paraphrased" tasks deliberately share **no
vocabulary** with the documents they need:

| strategy | same words | paraphrased |
|---|---|---|
| `context`, `deterministic` fallback | 0.92 | 0.83 |
| `context`, default (`fastembed`) | 1.00 | **0.92** |
| `search` | 0.94 | 0.75 |

### 1. This is why the model is now the default

With the hashing embedder, `context` beats plain `search` by **+0.03 recall and −0.03
MRR** — noise at this sample size. With the model it beats it by **+0.11 recall and
+0.13 MRR**. These numbers are what moved `fastembed` from an optional extra to a hard
dependency; the hashing embedder remains available as `DOCIR_EMBEDDER=deterministic` for
installs that cannot carry ~240 MB of dependencies and a ~64 MB model.

That is not a surprise once you read `DeterministicEmbedder`: it is signed feature
hashing over tokens, so it scores similarity by *shared vocabulary*. Two sentences that
mean the same thing in different words score **0.000**:

```
0.000  'duplicate charges when the customer double-clicks pay'
       vs 'idempotency keys for payment capture'
```

So under that embedder both halves of the "hybrid" ranking measure the same lexical
signal — which is what the README used to promise as "retrieval by meaning".

### 2. Graph expansion earns its place

`context` beats `context --expand 0` by +0.07 recall under both embedders, for
essentially no extra tokens (430 vs 439). The relation graph is doing real work, and the
default `--expand 2` looks about right.

### 3. The token claim holds, with a number

Mean payload an agent reads, per task (~4 chars/token):

| what the agent does | ~tokens | vs `context` |
|---|---|---|
| `docir context` | **430** | 1× |
| `docir query` (all skeletons) | 1 667 | 3.9× |
| read every document body | 3 240 | 7.5× |

On a 20-document corpus. The ratio grows with corpus size, since `context` is bounded by
`--limit` and the others are not.

## What this does not tell you

- **Single-annotator ground truth.** The judgments in `tasks.yaml` were written by the
  same author as `corpus.yaml`. It measures whether retrieval finds what that author
  considers relevant — weaker than judgments from someone who did not write the corpus.
- **Both rows come from the same corpus and judgments**, so they compare embedders, not
  absolute quality.
- **20 documents is small.** Differences of ±0.05 across 12 tasks are not significant.
  Treat the ordering as the signal, not the decimals.
- **The corpus is synthetic and coherent.** A real repository has half-written documents,
  duplicated decisions and inconsistent vocabulary. Expect worse numbers.
- **Stem overlap leaks into the "paraphrased" set.** FTS5 uses a Porter tokenizer, so
  `paying`/`payment` still match. The paraphrased tasks are harder for a lexical matcher,
  not impossible for it — which is why `search` scores 0.75 there rather than 0.
- **Nothing here measures whether retrieved context changed what an agent did.** That is
  the outcome the product actually exists for, and it needs a different instrument.

## Adding to it

Add a document to `corpus.yaml` (`key` is a stable handle; the real id is allocated at
load time, so judgments survive an id-style change). Add a task to `tasks.yaml` with the
keys a reader would genuinely need, and set `lexical:` honestly — a task that reuses the
document's wording belongs in the easy half.
