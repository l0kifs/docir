---
created: '2026-08-24'
description: Where docir stands against the retrieval, agent-memory, ADR and spec-driven
  markets on 2026-08-24, and the six gaps still open.
id: ref-a3f4d3140e4e
owner: maintainer
related:
- kind: supersedes
  to: ref-a6db21f52427
- issue-9b2d2ab09060
- adr-7316abc6be93
- adr-27c63ad02695
- rel-0c8d261640f6
status: active
tags:
- docs
- retrieval
- agents
title: Competitive landscape — docir vs. the alternatives (2026-08-24)
type: reference
updated: '2026-08-25'
---

*A fresh compile, not an edit of ref-a6db21f52427. That document is the 2026-08-03 snapshot and
stays readable for its gap history — eleven gaps closed with the analysis that produced the
work. This one carries the state of the market on 2026-08-24 and the gaps still open.*

## Method

Repository metadata read from the GitHub API on 2026-08-24. Feature claims come from each
project's own README and docs, not from hands-on use — where a claim rests on their
documentation being accurate, it is a documentation claim. Where a source is silent a cell
reads `?` rather than `no`. docir's own column was read from the 0.17.0 working tree and
re-read at **0.18.0** on 2026-08-25; the competitor columns are unchanged from the dates above.
Re-verifying docir's own cells in place is this document's standing practice — they are the one
column its author can check against a working tree, and freezing them would make the comparison
wrong in the only direction it is able to correct.

## What moved since 2026-08-03

Three things, and only one of them is about features.

**The decision-record category has gone quiet.** Log4brains — the tool docir's publishing story
was measured against — last pushed **2024-12-17**, twenty months ago. DocHub last pushed
2026-03-18. Neither is dead, but neither is moving, and the gap analysis that treated them as
pacing competitors was pricing a race nobody is running.

**The spec-driven category has exploded.** GitHub's Spec Kit is at **131k stars** and OpenSpec
at **66k**, both pushed within the last three days. That is where the attention in this space
now is, and it is the one adjacent market whose growth docir should have an answer for — see
*The gap that is not a feature*.

**The retrieval lane keeps filling.** qmd is at 29.1k stars. Three entrants appeared since the
last compile — `kbx` (SQLite + LanceDB + FTS5, Python), `memweave` (markdown + SQLite, no
vector DB) and `mjm.local.docs` (.NET, markdown ADRs behind a Blazor UI *and* an MCP server) —
none with traction yet, all with the same shape. The idea is not scarce; the execution is.

## Table A — the closest technical competitors

*docir 0.17.0, qmd 2.8.3 and Basic Memory re-read on 2026-08-24; sqlite-memory's cells date
from the 2026-08-03 compile and are marked `?` where a row postdates them.*

| | **docir** | **Basic Memory** | **qmd** | **sqlite-memory** |
|---|---|---|---|---|
| Stars / last push | — | 3.7k · today | 29.1k · 2026-08-18 | 111 · 2026-07-21 |
| Language / install | Python, `uv tool install docir` | Python, pip/uvx | Node/Bun, npm | C ext + Go CLI |
| License | MIT | AGPL-3.0 | MIT | NOASSERTION |
| Index | SQLite (metadata + FTS5 + graph + vectors) | SQLite **or Postgres** + vectors | SQLite (FTS5 + sqlite-vec) | single SQLite |
| Lexical + vector + fusion | ✅ RRF | ✅ hybrid | ✅ RRF, weighted | ⚙️ weighted blend |
| Embedding model | ✅ **swappable** (`embed_model:`, any fastembed model) | ✅ FastEmbed | ✅ swappable per role | ? |
| Query expansion / HyDE | ⚙️ **the caller supplies them** (`context --also`); docir generates none, by decision (adr-27c63ad02695) | ❌ | ✅ fine-tuned 1.7B | ? |
| Score explainability | ✅ `--explain`: ranks, RRF terms, cosine, graph provenance | ? | ✅ `--explain` | ? |
| Expression over the corpus | ✅ `query --expr` (JMESPath over fields + resolved edges) | ❌ | ❌ | ❌ |
| Reranking | ❌ **measured worse, rejected** (adr-d657a09b8c4a) | ⚙️ cross-encoder, **default off for latency** | ✅ LLM cross-encoder | ❌ |
| Retrieval unit | ✅ document **+ every `##` section** | note | chunk (~900 tok, overlapped) | chunk |
| Passage citation | ✅ `matched_section`, feeds `get --section` | ❌ | ✅ passage + location | ⚙️ |
| **Benchmark an adopter can run** | ✅ `docir bench <fixture>` | ❌ | ✅ `qmd bench` | ❌ |
| Typed relation graph | ✅ typed, successor-aware traversal | ✅ typed (single-token kinds) | ❌ | ❌ |
| Schema enforced **at write** | ✅ hard Tier-0 gate | ⚙️ `schema_infer`/`validate`/`diff` (advisory) | ❌ | ❌ |
| Staleness / review cadence | ✅ `owner` + `verified` + `review_days` | ❌ | ❌ | ❌ |
| Integrity checks | ✅ `check --strict` CI gate, `--fix` | ⚙️ `doctor` | ❌ | ⚙️ content-hash |
| MCP server | ✅ 20 tools | ✅ ~15 tools | ✅ 4 tools, stdio + HTTP | ✅ |
| Import from existing docs | ❌ **by decision** (issue-20933967697b) | ✅ Claude/ChatGPT/memory-json | ✅ any directory | ✅ |
| Team / device sync | git only | ✅ Cloud, $15/mo | ❌ | ✅ CRDT |

Two cells flipped **toward** docir since the last compile, and both were this month's work: the
embedding model became swappable (issue-a24f404dd106), and `docir bench` closed the row where
qmd had pulled ahead. One cell is worth watching: Basic Memory ships cross-encoder reranking
and **defaults it off for latency**, which is the same answer docir reached by measurement.

## Table B — decision-record & governance tooling

*Cells from the 2026-08-03 compile except where dated. Activity re-checked 2026-08-24, and
activity is the story here.*

| | **docir** | **Log4brains** | **DocHub** | **Spec Kit / OpenSpec** |
|---|---|---|---|---|
| Activity | active | **last push 2024-12-17** | last push 2026-03-18 | 131k / 66k ★, pushed this week |
| ADR creation | ✅ | ✅ interactive | ⚙️ entities, not decisions | ✅ agent commands |
| Search over the corpus | ✅ lexical + semantic | ⚙️ site search | ⚙️ JSONata over the model | ❌ |
| Validation | ✅ schema, status, tags, edges | ❌ | ✅ user-written validators | ⚙️ structure |
| Static site | ✅ `docir build` + constellation graph | ✅ Pages/S3 | ✅ portal | ❌ |
| Freshness | ✅ owner/verified/cadence | ❌ | ❌ | ❌ |
| Workflow phases | ❌ | ❌ | ❌ | ✅ propose→spec→task→archive |

## What docir has that nobody else does

Unchanged from the last compile, and now better evidenced:

1. **A hard validation gate on write.** Basic Memory can *infer* and *validate* a schema, and
   now *diff* one; docir refuses the write. Everyone else stores what the agent typed.
2. **Staleness as data.** `owner` + `verified` + `review_days` + a review queue, still unique
   across every tool in both tables.
3. **Corpus integrity as a CI gate, with repair.** `check --strict` fails a merge; `check --fix`
   repairs what needs no guess.
4. **Skeleton reads as a contract.** No list path returns a body.
5. **Published *and reproducible* retrieval numbers.** docir was the only tool publishing any;
   it is now one of two whose users can reproduce them on their own corpus.

## Open gaps

Five of the eighteen in ref-a6db21f52427 remain open or deliberately unbuilt, and one of those
five is half-closed. The rest closed — that document holds the analysis that produced the work,
and rel-0c8d261640f6 links what 0.18.0 did about the two below.

### 14. No expression language over the corpus

**Half-closed on 2026-08-25, and the open half is the one that carries the risk.**

`docir query --expr '<JMESPath>'` ships: an expression over each document's own fields plus its
edges resolved in both directions, applied before the limit (adr-7316abc6be93). Three of the
four questions this gap was opened with are now askable —
`stale && owner == null`, `related[?status=='superseded']`,
`length(related_by[?kind!='relates_to']) == 0`. The fourth is an aggregate across documents and
is out of reach of a per-document predicate.

What DocHub still has and docir does not is the *second* use of the same grammar: an expression
a store **declares** and the tool runs unasked, which is what turns a query language into a
validator. That half is deliberately unbuilt, because it is where adr-b2cfed9d5888's refusal
actually gets tested — an expression docir runs on your behalf is much closer to a rule than one
you type — and because the grammar should be exercised by hand before anything runs it
unattended. Tracked in issue-9b2d2ab09060, with the severity question it needs settled first.

So this is no longer the most credible open gap. It is a gap with its risky half left, on
purpose.

### 16. No query expansion and no HyDE

**Closed on 2026-08-25, in both halves and neither the expected way.**

The model-free half was built and measured and lost: pseudo-relevance feedback cost 0.13
recall@5 on docir's own corpus, because the first pass is already right 88% of the time and
rewriting from its own top hits mostly amplifies the 12% where it was not (adr-46b69a581c65).

The generative half is closed by adr-27c63ad02695, and the reason is positional rather than
about cost. docir's caller is already a frontier model that has read the code; shipping a
0.5-1.5B rewriter underneath it would add a weaker generator below a stronger one and ask it to
guess at context the caller had and did not send. So docir generates nothing, and `context
--also` accepts the rewrite instead — which is HyDE done by the better model, measured at
recall@5 0.88 -> 1.00 for a correct hypothetical.

The cell against qmd stays ⚙️ rather than ✅ and that is honest: qmd expands a query the caller
never has to think about, and docir requires the caller to do it. Which is right depends on
whether the caller is a model, and for qmd it may be a shell.

### 10. Packaging weight

~240 MB of dependencies. Unchanged, and now with a second edge: a multilingual model is 220 MB
on top of the default's 67 MB, so the swappable-embedder work made the ceiling higher rather
than the floor lower.

### 9, 11, 12 — correct omissions

No conversation capture, no wikilink compatibility, no sync beyond git. Each is a deliberate
consequence of the "curated corpus, git canonical" thesis. Listing them is scope-awareness.

## The gap that is not a feature

The spec-driven category is at 131k and 66k stars while the ADR category has stopped moving.
Read plainly: far more people want an agent *workflow* than want a decision *archive*.

docir has no workflow phases and should not grow them — that is Spec Kit's product, with more
attention behind it than docir will ever have. But the adjacency is real in one direction: a
spec-driven workflow produces decisions, and nothing in either tool keeps them once the task
archives. The question worth holding is not "should docir have phases" but "what should docir
be to a repo that already runs one" — and the answer is probably the `code:` glob and
`docir context`, not a second workflow.

Nothing here is a decision. It is the one thing in this compile that changed enough to deserve
one later.

## Sources

- GitHub API metadata, 2026-08-24: [tobi/qmd](https://github.com/tobi/qmd) ·
  [basic-memory](https://github.com/basicmachines-co/basic-memory) ·
  [sqlite-memory](https://github.com/sqliteai/sqlite-memory) ·
  [log4brains](https://github.com/thomvaill/log4brains) ·
  [DocHub](https://github.com/DocHubTeam/DocHub) ·
  [OpenSpec](https://github.com/Fission-AI/OpenSpec) · [Spec Kit](https://github.com/github/spec-kit)
- READMEs re-read 2026-08-24: qmd (2.8.3), basic-memory
- New entrants: [kbx](https://github.com/tenfourty/kbx) · memweave · mjm.local.docs
- The superseded compile and its gap history: ref-a6db21f52427
