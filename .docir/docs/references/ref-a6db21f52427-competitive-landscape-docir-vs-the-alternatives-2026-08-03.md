---
created: '2026-08-03'
description: What the adjacent tools do, where docir is unique, and the ranked list
  of features it does not have.
id: ref-a6db21f52427
owner: maintainer
related:
- adr-354a4270ecd8
- adr-a343140d72e2
- adr-d657a09b8c4a
- arch-1cfb1b212237
- adr-927aa43d9635
- adr-307ba1f1a820
- issue-20933967697b
- issue-90aea6d1b891
- issue-afd25273ff1f
status: active
tags:
- docs
- retrieval
- agents
title: Competitive landscape — docir vs. the alternatives (2026-08-03)
type: reference
updated: '2026-08-13'
verified: '2026-08-13'
---

# Competitive landscape — docir vs. the alternatives

*Compiled 2026-08-03 from public repositories and vendor documentation. docir at v0.9.0.
Sources are linked at the bottom; feature claims about competitors reflect their READMEs and
docs on that date, not hands-on testing. Where a source was silent, the cell reads `?` rather
than `no`.*

## Who is actually competing

*Re-verified 2026-08-13 against docir 0.12.0+`Unreleased`. Two things changed since the
2026-08-06 pass: a fifth market entered the picture (architecture-as-code, below), and three
gaps it exposed were worked — one shipped, one narrowed, one closed as a decision. Only docir's
own cells have ever been re-checked; every competitor column still dates from the compile that
introduced it.*

docir sits at the intersection of markets that mostly do not overlap with each other:

| Category | What they optimize for | Representative tools |
|---|---|---|
| **Agent memory over markdown** | Persistence across sessions; an agent writes and reads its own notes | Basic Memory, sqlite-memory (SQLiteAI), mem0ry4ai, projectmem, agentmemory |
| **Local markdown search for agents** | Retrieval quality over an existing pile of `.md` | qmd (`tobi/qmd`), qmd forks, Cognee/Supermemory (hosted, heavier) |
| **Decision-record & governance tooling** | Human-authored ADRs, publication, enforcement | adr-tools, Log4brains, archgate, adrkit, trackfw |
| **Spec-driven development** | A workflow (propose → spec → tasks → archive) an agent follows | OpenSpec, GitHub Spec Kit, Kiro, BMAD-METHOD |
| **Architecture-as-code / EA modelling** | A queryable model of an organisation's systems, rendered as diagrams | DocHub, LikeC4, Structurizr, IcePanel |

**docir's actual position:** it is the only tool in the set that treats documents as a *compiled,
schema-validated corpus* — it takes the retrieval stack from category 2, the write-through-CLI
discipline from category 1, and the decision/ADR semantics from category 3, and adds a hard
validation gate none of them have.

### The fifth market, and why it is adjacent rather than competing

DocHub (378★, Apache-2.0 plus a "do not conceal your use" clause, first commit 2021) is the one
worth naming, because it is the most-developed thing in the category and because it publicly
targets *architecture for AI agents* — docir's own ground. It is a Vue SPA over a GitLab or
Bitbucket backend: YAML manifests describe components, contexts and entities in an extensible
metamodel, JSONata queries and user-written validators run over that model, and the portal
renders C4, PlantUML, BPMN, Mermaid, OpenAPI and AsyncAPI. Manifests federate across
repositories through a root manifest with semver-versioned `$package` dependencies.

The unit of description is the difference, and it is not a matter of degree:

| | **docir** | **DocHub** |
|---|---|---|
| Unit | a document — decision, issue, note | an entity — component, context, deployment unit |
| Reader | an agent, over CLI or MCP | a person, in a portal or IDE panel |
| Query | ranked lexical + vector fusion | JSONata over the model |
| Validation | a hard write-time gate + `check --strict` | user-authored validators, reported in the UI |
| Diagrams | the relation graph, plus `mermaid` fences (unreleased) | C4, PlantUML, BPMN, Swagger, AsyncAPI |
| Freshness | `owner`/`verified`/`review_days`, a review queue | not modelled |
| Federation | read-only across declared stores (unreleased) | manifests consolidated across repos |
| Runtime | one CLI, no server, offline | Docker + a Git backend, or an IDE plugin |
| Its AI story | MCP server, skeleton reads, local vectors | a community RAG example: Yandex embeddings, ChromaDB, Telegram |

Read it as: DocHub answers *what systems do we have and how do they connect*; docir answers
*what did we already decide about this code, and is it still true*. A team can plausibly want
both. What DocHub demonstrates that docir should take seriously is not a feature — it is that
"architecture as data" (a real query language over the corpus) and cross-repo consolidation are
what an organisation asks for once more than one team is involved. Gaps 14 and 15 are those.

## Table A — the closest technical competitors (retrieval over local markdown)

| | **docir** | **Basic Memory** | **qmd** | **sqlite-memory** |
|---|---|---|---|---|
| Language / install | Python, `uv tool install docir` | Python 3.12+, pip/uvx | Node/Bun, npm | C ext + Go CLI, single binary |
| License | MIT | AGPL-3.0 | MIT | MIT |
| Source of truth | git markdown | markdown files | markdown files | markdown files |
| Index | SQLite (metadata + FTS5 + graph + vectors) | SQLite + vectors | single SQLite (FTS5 + sqlite-vec) | single SQLite `.db` |
| Lexical search | ✅ FTS5 | ✅ | ✅ BM25 | ✅ FTS5 |
| Semantic search | ✅ local ONNX (`bge-small-en-v1.5`) | ✅ FastEmbed | ✅ local GGUF via node-llama-cpp | ✅ vector cosine |
| Fusion | ✅ RRF | ✅ hybrid | ✅ RRF | ⚙️ weighted blend |
| Reranking | ❌ **built, measured worse than fusion, rejected** (adr-d657a09b8c4a) | ✅ cross-encoder / LiteLLM | ✅ local LLM rerank | ❌ |
| Retrieval unit | ✅ document **+ every `##` section** embedded (adr-927aa43d9635); reads are skeletons, `get --section` returns one span | note | **chunk** (heading/para) w/ citation | **chunk**, markdown-aware |
| Passage citation in a result | ✅ `matched_section` names the heading that matched, and `get --section` takes it verbatim (issue-afd25273ff1f) | ❌ | ✅ passage + location | ⚙️ |
| Graph / relations | ✅ **typed** edges (`supersedes`, `depends_on`, …), bidirectional expansion | ✅ untyped-ish wikilinks + observations | ❌ | ❌ |
| Frontmatter schema enforced at write | ✅ **hard Tier-0 gate** | ⚙️ `schema_infer` / `schema_validate` (advisory) | ❌ | ❌ |
| Status grammar / transitions | ✅ per type | ❌ | ❌ | ❌ |
| Staleness / review cadence | ✅ `owner` + `verified` + `review_days`, review queue | ❌ | ❌ | ❌ |
| Corpus integrity checks | ✅ `check` (dup ids, dangling, cycles) `--strict` CI gate | ⚙️ health checks | ❌ | ⚙️ content-hash detection |
| Auto-repair | ✅ `check --fix` | ❌ | ❌ | ❌ |
| Collision-free id allocation | ✅ DB counter + random ids | permalinks | n/a | n/a |
| **MCP server** | ✅ `docir mcp serve`, 19 tools | ✅ 20+ tools | ✅ | ✅ |
| File watching / auto-sync | ✅ daemon watches `docs/`, debounced `reindex --changed` (`DOCIR_WATCH=0` opts out) | ✅ | ✅ | ✅ `watch` |
| Warm daemon | ✅ | server process | — | — |
| Token-aware output | ✅ skeletons + trimmed JSON when piped | ⚙️ | ⚙️ | ⚙️ |
| Import from existing docs | ❌ **by decision, not by omission** (issue-20933967697b) | ✅ Claude/ChatGPT/Obsidian importers | ✅ collections | ✅ add files |
| Team / device sync | git only | ✅ Cloud, $15/mo | ❌ | ✅ CRDT sync |
| Published retrieval benchmark | ✅ `benchmarks/` (recall@5 0.96, MRR 0.95) | ❌ | ❌ | ❌ |

Five docir cells moved between the 2026-08-03 compile and the 2026-08-06 re-verification:
reranking, retrieval unit, file watching, import, and a new passage-citation row — which the
same day's work then closed, so gap 2 has no residual left.

## Table B — decision-record & governance tooling

| | **docir** | **adr-tools** | **Log4brains** | **archgate** | **OpenSpec / Spec Kit** |
|---|---|---|---|---|---|
| Language | Python | shell | TypeScript/Node | TypeScript | Node / Python |
| License | MIT | MIT (fork archived) | Apache-2.0 | Apache-2.0 | MIT |
| ADR creation | ✅ `add --type decision` | ✅ | ✅ interactive | ✅ | ✅ via agent commands |
| Templates (MADR etc.) | ⚙️ profiles/types | ✅ | ✅ customizable | ✅ | ✅ |
| Supersede / link decisions | ✅ typed graph | ✅ text link | ✅ status only | ❌ | ⚙️ |
| Search over the corpus | ✅ lexical + semantic | ❌ | ⚙️ site search | ❌ | ❌ |
| Validation | ✅ schema, status, tags, edges | ❌ | ❌ | ✅ **code conformance** | ⚙️ structure |
| Names the code a document governs | ✅ `code:` globs, Tier 0 shape check, `check` warns when one stops matching, `query --code <path>` asks in reverse (issue-90aea6d1b891) | ❌ | ❌ | ⚙️ implied by an executable rule, not declared as data | ❌ |
| Enforce decisions against *code* | ❌ **by decision** — the rule is a test, and `--code` records which one (adr-b2cfed9d5888) | ❌ | ❌ | ✅ `.rules.ts`, CI blocking | ❌ |
| Static site / human browsing | ✅ `docir build --out site/` — self-contained pages, both edge directions, constellation graph (adr-a343140d72e2, adr-307ba1f1a820) | ❌ | ✅ **publishes to Pages/S3** | ❌ | ❌ |
| Timeline view / `serve` | ❌ | ❌ | ✅ | ❌ | ❌ |
| Git-history metadata | ❌ **not built, deliberately** | ⚙️ | ✅ from git log | ❌ | ❌ |
| Agent onboarding | ✅ `agent install` (skill/AGENTS.md) | ❌ | ❌ | ✅ | ✅ 20+ assistants |
| Workflow phases | ❌ | ❌ | ❌ | ❌ | ✅ propose→spec→task→archive |
| Multi-doc types beyond ADR | ✅ 15 types, 5 profiles | ❌ | ❌ | ❌ | ⚙️ specs/tasks |

Legend: ✅ yes · ⚙️ partial / different shape · ❌ no · `?` not documented

Neither remaining ❌ is now open work: gap 6 closed as a decision (the rule is a test), and
`Git-history metadata` is a deliberate ❌ — deriving `commit`
or `pr` from git log makes the index depend on repository history rather than on the files,
which the "files are canonical, index is derived" thesis does not cover.

---

## What docir has that nobody else does

These are defensible, not cosmetic — no competitor in either table offers them:

1. **A hard validation gate on write.** Tier 0 rejects an unknown status, an illegal transition,
   an unregistered tag, a dangling `related`, a disallowed relation kind. Basic Memory can
   *infer* and *validate* a schema; docir *refuses the write*. Everyone else stores whatever
   the agent typed.
2. **Typed relation graph + successor-aware expansion.** A `supersedes` edge is traversed
   backwards during retrieval, so "is this decision still current?" is answerable. Wikilink
   graphs (Basic Memory, Obsidian) cannot express *how* two notes relate.
3. **Staleness as data.** `owner` + `verified` + per-type `review_days` turns "is this still
   true?" into a checkable fact and a worklist (`query --owner X --stale`). Unique across all
   nine tools surveyed.
4. **Corpus integrity as a CI gate, with repair.** `check --strict` fails a merge on duplicate
   ids and dangling edges; `check --fix` re-issues and repairs. Only archgate has a CI story,
   and it checks *code*, not the document graph.
5. **Skeleton reads as a contract.** `query`/`search`/`context` never return bodies. Competitors
   return chunks or full notes; docir makes the token budget structural.
6. **A single write path with collision-free ids.** Parallel agents and branch merges cannot
   mint the same id — a failure mode every "agent writes markdown" tool has.

## Gaps — features competitors have that docir does not

Ranked by how much they cost docir in adoption, highest first. Numbering is stable: a gap that
closes is struck through and kept, because the analysis is what produced the work.

### ~~1. No MCP server~~ — **closed in 0.10.0**
`docir mcp serve` (FastMCP, shipped by default) exposes 19 tools over stdio or HTTP,
built on the existing `Dispatcher`, so an MCP tool and its CLI command cannot answer
differently. Reads carry `readOnlyHint`, results are trimmed exactly as the piped CLI's JSON
is, and requests go through the daemon by default, so the embedding model stays warm across
calls. Kept in the list because the gap analysis is what produced it. The remaining
distinction against Basic Memory is coverage of *clients*, not of protocol — see gap 11.

### ~~2. Document-level retrieval only~~ — **closed in 0.10.0, both halves**
docir embedded whole documents, and the model reads ~512 tokens, so 84 of its own 103
documents were partly absent from the semantic index while FTS5 hid it. It now embeds
**every `##` section beside the document** (adr-927aa43d9635) and `docir get --section
"<heading>"` returns exactly one span — the passage read, instead of a 4,000-line body.
Coverage on docir's own store went 44% → 100%; MRR 0.94 → 0.97 with recall@5 held at 0.97.

The citation half closed the same day (issue-afd25273ff1f): the collapse to one score per
document keeps the winning *candidate*, not just its score, so a hit carries
`matched_section` — the heading that matched, and exactly what `get --section` takes. Absent
still means "not addressable as a section" (the document vector won, or the hit was lexical or
graph-reached), never "nothing matched". qmd returns the passage itself; docir returns its
name and lets you ask, which is the skeleton contract holding.

### 3. No reranking *(Basic Memory: cross-encoder; qmd: local LLM rerank)*

RRF fusion is the state docir stops at, and a cross-encoder rerank over the top-N
is the standard next step both close competitors already ship. **docir built it
and rejected it on measurement** (adr-d657a09b8c4a, `adr-d657a09b8c4a`): three models
across two families (`ms-marco-MiniLM-L-6`, `-L-12`, `jina-reranker-v1-turbo`)
and three shortlist widths all ranked *worse* than plain fusion — recall@5 0.97
→ 0.90-0.93, MRR 0.97 → 0.85-0.89. These rerankers are trained on question →
web-passage relevance; docir's queries are imperatives against terse design
documents, and the model scored nearly every pair −8 to −11, where ordering is
noise. The gap is real — docir has no reranker — but "docir should add one" is
now measured false for the off-the-shelf option. An LLM reranker (what qmd
does) is a different cost class and remains untested.

### ~~4. No file watching / auto-reindex~~ — **closed in 0.10.0**

Hand-edit a body and the index was stale until someone ran `reindex`; competitors
watch the directory. The daemon now watches `docs/` and runs a debounced `reindex
--changed` within about a second of an edit. Automating it is safe because the files
are canonical and the index is derived — a reindex can only make the two agree, and
writes no markdown — so it is on by default (`DOCIR_WATCH=0` opts out). `--no-daemon`
runs still never watch, so CI runs the command explicitly.

### ~~5. No human-browsable output~~ — **closed in 0.10.0**

Log4brains' pitch is a published, timeline-browsable ADR site on GitHub Pages.
Closed by `docir build --out site/` (adr-a343140d72e2): one self-contained HTML page
per document plus a filterable index, no external requests, publishable to Pages or S3
unchanged. It renders what Log4brains cannot — the typed relation graph **in both
directions**, with an inbound `supersedes` surfaced as a banner above the body rather
than a line in a list, plus staleness, owner and tags; the graph also has its own
interactive constellation page (adr-307ba1f1a820). docir still has no `serve` command
and no timeline view; the static artifact was chosen over a live UI because it is a
derived projection of the files, which is the architecture's own thesis, and because a
URL can be linked in a pull request.

### ~~6. No enforcement of decisions against the codebase~~ — **closed as a decision**
archgate binds an ADR to an executable rule (`.rules.ts`) that fails CI when the code violates it;
trackfw enforces ADR → requirement → roadmap traceability. docir will not: a decision that can be
mechanically enforced is enforced by a **test**, in the project's own language and runner, and
`--code tests/test_x.py` records which decision that test enforces (adr-b2cfed9d5888). `check`'s
`unmatched-code` then covers the failure a rule file has too — the enforcement was deleted and
nothing said so.

The review-time half is a notice, never a gate: CI prints the decisions a branch's changed files
declare they govern (`query --code $(git diff --name-only origin/main...HEAD)`). Failing a build
because you touched governed code punishes the ordinary case, and a check cleared by clicking is a
ritual rather than a human reading a decision — the same argument that made staleness delivery a
pull. What docir refuses to own: a rule DSL, a sandbox for user-supplied rules, and per-language
static analysis; archgate is TypeScript-only for exactly that reason.

So the cell stays ❌ against archgate's ✅ and that is honest — docir does not fail CI on a code
violation. The gap is *answered*, not deferred, and the trigger for reopening it is evidence: a
governed decision violated in a branch whose notice listed it. "A competitor has it" never was one.

### ~~7. No git/code linkage~~ — **closed for code, deliberately open for git history**
`code:` frontmatter now names the code a document governs, in three steps that shipped together
(issue-90aea6d1b891): the data (Tier 0 validates the *shape*, so a decision may precede the code
it decides), a Tier 1 `unmatched-code` warning once a pattern stops matching, and
`docir query --code <path>` for the reverse question. Matching is textual rather than a
filesystem walk, because the branch that *deletes* a file is exactly when its decisions must be
re-read. Backfilled across docir's own corpus on 2026-08-06: 28 documents, `check` clean.

Two halves stay open, and only one of them is wanted. **Git-history metadata** — deriving
`commit`/`pr` from git log, as Log4brains does — is a deliberate no: it would make the index
depend on repository history rather than on the files, which the "files are canonical, index is
derived" thesis does not cover, and a shallow clone would rebuild a different index from the same
documents. **AST-anchored staleness** (adr-bd7c4f3c5764) is still deferred, but it is no longer
blocked: it now has an anchor to hang on.

### ~~8. No import path for existing docs~~ — **closed as a decision, not a command**
`docir import` was built on 2026-07-27 and removed the same day, before committing
(issue-20933967697b). With random ids the default, the one thing import could do that `add`
cannot — preserve the number a filename implies — went away, and what remained was inference:
title, description and status guessed from prose. Every guess is one the agent must verify, and
verifying a guess is not cheaper than making the judgement, because the guess must first be
noticed as wrong. The agent reads every source file either way. The sanctioned path is `add`
per document, with `--id` where a historical number must survive its cross-references.

### 9. No conversation/session capture *(mem0ry4ai, agentmemory, projectmem)*
Competitors index past agent transcripts and warn when an agent repeats a failed approach.
docir stores only curated documents. Arguably correct — but it means docir does not compete
for "agent memory" spend at all.

### 10. Python-only distribution, ~240 MB of deps
qmd is npm, sqlite-memory is a single Go binary, adr-tools is a shell script. `pipx`/`uv` limits
docir to teams that tolerate a Python tool; the default fastembed install is heavy for CI images
(the `DOCIR_EMBEDDER=deterministic` escape hatch exists but degrades ranking below plain FTS).

### 11. No wikilink compatibility / editor integration
Basic Memory's `[[Target]]` links render in Obsidian, so a human gets a graph view for free.
docir's `related:` frontmatter is invisible to every markdown editor. Less pressing since 0.10.0:
the published site renders the graph both ways, so the human reader has somewhere to go.

### 12. No team/multi-device sync story beyond git

Basic Memory Cloud (paid) and sqlite-memory (CRDT) both sell shared knowledge across agents and
teammates. docir's answer is "commit it", which is defensible for a repo-scoped tool and a
non-answer for personal/cross-repo knowledge.

### ~~13. No diagrams beyond the relation graph~~ — **narrowed in the unreleased section, deliberately not closed**
*(DocHub: C4, PlantUML, BPMN, Swagger, AsyncAPI, SmartAnts)*

The single most visible difference to a human evaluating both in ten seconds. Half of it was
never real: the site has drawn the typed relation graph as an interactive per-type constellation
since 0.10.0 (adr-307ba1f1a820), plus a 1-hop map on every document page — generated SVG, no
runtime. The half that was real is *author-drawn* diagrams, and the unreleased section draws `mermaid` fences
(adr-9c7c1ab8acef) — with the runtime supplied by the publisher rather than vendored, because
the bundle is megabytes and most corpora draw nothing.

The rest stays unbuilt on purpose. C4, BPMN and contract rendering are the *modelling* tool's
job: they need an entity model docir does not have and should not grow (gap 13's sibling,
below). Link out to the tool that owns the contract.

### 14. No expression language over the corpus *(DocHub: JSONata; also its validators)*

docir has rich structure — typed edges, staleness, `code` globs, a schema — and exactly one way
to interrogate it: the filters `query` ships with. "Which decisions are older than their cadence
and govern code nobody owns?" is not expressible, and every new question of that shape is a
feature request. DocHub's answer is a real query language over the model, which also doubles as
its rule engine: a validator *is* a JSONata expression that must return empty.

This is the most credible open gap in the list, and it has a shape that fits: an expression over
document metadata and edges (JMESPath is the small, well-specified choice), plus named checks a
store declares in its own `docs-schema.yaml` and `check` evaluates. That keeps adr-b2cfed9d5888
honest — docir still ships no opinions about anyone's architecture; the rules would be the
user's — while removing the reason most of those feature requests exist. Not started.

### ~~15. Single-store: no cross-repo reads~~ — **closed in the unreleased section**

The decision governing the service you are editing lives in the platform repo, and an agent
reading `context` in the service repo could not see it, so it re-decided. adr-fb938175f72a
supersedes the exclusion adr-20eec6e2e2ca wrote: a store declares peers in a committed
`stores.yaml`, and `context`/`query`/`search`/`get` answer from all of them, with `--store` and
the MCP `stores` argument for one-off peers.

Writes never federate and neither does `build`; peers open `mode=ro` so SQLite refuses a write
rather than docir promising not to attempt one; an unreadable peer is skipped with a warning,
because its index is gitignored and a colleague's fresh clone must not be everyone's outage. The
merge sorts on `similarity`, and that is measured rather than argued: on the benchmark corpus
split in two, similarity-merge scores recall@5 0.91 / MRR 0.93 against rank-merge's 0.88 / 0.72
(`benchmarks/federation.py`). Cross-store RRF over the returned lists *is* rank-merge — each
document appears in exactly one list, so its fused score has one term.

What docir still does not do is DocHub's version of this: versioned package dependencies between
stores, and a consolidated *model*. It reads peers; it does not compose them.

## Recommended reading of these gaps

Of fifteen, **eleven are settled**: 1, 2, 4, 5, 7 and 15 shipped (2 in both halves, 13 in half);
3, 6 and 8 closed as decisions — built, measured or reasoned against, and removed rather than
deferred; 9 and 12 are correct omissions given the "curated corpus, git canonical" thesis, so
listing them is scope-awareness rather than a to-do. What is left is one open gap, one standing
constraint, and one thing not to build:

1. **Gap 14 (an expression language) is the only real open work.** It is what "architecture as
   data" means in practice, it is the honest version of a rules engine (the rules are the
   user's, so adr-b2cfed9d5888 still holds), and it removes the reason most future filter
   requests will exist. Nothing else in either table is open.

2. **Gap 10 is packaging, not a feature.** `fastembed`/`onnxruntime` is the weight, and the
   documented escape hatch ranks *below* plain full-text search (`benchmarks/` §1), so "make it
   lighter" and "keep it good" are the same decision, not two.

3. **Do not grow an entity model.** Components, contexts, deployment units and C4 are the
   adjacent market's product, with five years of work behind them; chasing them makes a worse
   DocHub. The `code:` glob is already the version of that idea that fits docir's unit — it
   binds a *document* to the system without modelling the system.

**Gap 11 is not worth building.** It buys a graph view in a human's editor, and 0.10.0 already
publishes the graph both ways in the site — for docir's actual reader, an agent, `related:`
frontmatter is the better-typed form and `[[wikilinks]]` would be a second, weaker one to keep in
sync.

Two things the work behind this list taught that no table row would have. A document that governs
everything answers every question: `arch-1cfb1b212237` carries `src/docir/**` and so appears in
every `--code` result — *true*, and still a cost to the reader, which is the tension to watch as
more documents adopt the field. And a capability reaches further than the command that introduced
it: federating reads silently federated `build`, which published a peer's decisions into this
repo's site while the summary line named this store (adr-fb938175f72a's amendment). When
something becomes true of "reads", check every path that is built from one.

## Sources

- [tobi/qmd](https://github.com/tobi/qmd) · [qmd write-up](https://knightli.com/en/2026/05/01/qmd-markdown-search-for-ai-agents/)
- [basicmachines-co/basic-memory](https://github.com/basicmachines-co/basic-memory) · [docs](https://docs.basicmemory.com/start-here/what-is-basic-memory)
- [sqliteai/sqlite-memory](https://github.com/sqliteai/sqlite-memory)
- [thomvaill/log4brains](https://github.com/thomvaill/log4brains)
- [archgate/cli](https://github.com/archgate/cli)
- [Fission-AI/OpenSpec](https://github.com/Fission-AI/OpenSpec) · [GitHub Spec Kit](https://github.blog/ai-and-ml/generative-ai/spec-driven-development-with-ai-get-started-with-a-new-open-source-toolkit/) · [OpenSpec vs Spec Kit](https://hashrocket.com/blog/posts/openspec-vs-spec-kit-choosing-the-right-ai-driven-development-workflow-for-your-team)
- [architecture-decision-records topic](https://github.com/topics/architecture-decision-records) · [agent-memory topic](https://github.com/topics/agent-memory)
- [riponcm/projectmem](https://github.com/riponcm/projectmem) · [jayzeng/agentmemory](https://github.com/jayzeng/agentmemory)
- [ADR complete guide 2026](http://docs.align.tech/blog/architecture-decision-records-complete-guide/) · [Best spec-driven tools 2026](https://www.augmentcode.com/tools/best-spec-driven-development-tools)
- *(2026-08-13)* [DocHubTeam/DocHub](https://github.com/DocHubTeam/DocHub) · [rpiontik/DocHubExamples](https://github.com/rpiontik/DocHubExamples) · [dochub-manual](https://github.com/DocHubTeam/dochub-manual) · [dochub.info](https://dochub.info/docs/dochub). Repository metadata read from the GitHub API on that date; feature claims from the READMEs, the manual and the 16 worked examples, not from hands-on use.
