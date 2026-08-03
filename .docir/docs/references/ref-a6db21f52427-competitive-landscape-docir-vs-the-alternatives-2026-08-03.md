---
created: '2026-08-03'
description: What the adjacent tools do, where docir is unique, and the ranked list
  of features it does not have.
id: ref-a6db21f52427
owner: maintainer
related:
- adr-354a4270ecd8
- arch-1cfb1b212237
status: active
tags:
- docs
- retrieval
- agents
title: Competitive landscape — docir vs. the alternatives (2026-08-03)
type: reference
updated: '2026-08-03'
---

# Competitive landscape — docir vs. the alternatives

*Compiled 2026-08-03 from public repositories and vendor documentation. docir at v0.9.0.
Sources are linked at the bottom; feature claims about competitors reflect their READMEs and
docs on that date, not hands-on testing. Where a source was silent, the cell reads `?` rather
than `no`.*

## Who is actually competing

docir sits at the intersection of three markets that mostly do not overlap with each other:

| Category | What they optimize for | Representative tools |
|---|---|---|
| **Agent memory over markdown** | Persistence across sessions; an agent writes and reads its own notes | Basic Memory, sqlite-memory (SQLiteAI), mem0ry4ai, projectmem, agentmemory |
| **Local markdown search for agents** | Retrieval quality over an existing pile of `.md` | qmd (`tobi/qmd`), qmd forks, Cognee/Supermemory (hosted, heavier) |
| **Decision-record & governance tooling** | Human-authored ADRs, publication, enforcement | adr-tools, Log4brains, archgate, adrkit, trackfw |
| **Spec-driven development** | A workflow (propose → spec → tasks → archive) an agent follows | OpenSpec, GitHub Spec Kit, Kiro, BMAD-METHOD |

**docir's actual position:** it is the only tool in the set that treats documents as a *compiled,
schema-validated corpus* — it takes the retrieval stack from category 2, the write-through-CLI
discipline from category 1, and the decision/ADR semantics from category 3, and adds a hard
validation gate none of them have.

---

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
| Reranking | ❌ | ✅ cross-encoder / LiteLLM | ✅ local LLM rerank | ❌ |
| Retrieval unit | **whole document** (skeleton) | note | **chunk** (heading/para) w/ citation | **chunk**, markdown-aware |
| Graph / relations | ✅ **typed** edges (`supersedes`, `depends_on`, …), bidirectional expansion | ✅ untyped-ish wikilinks + observations | ❌ | ❌ |
| Frontmatter schema enforced at write | ✅ **hard Tier-0 gate** | ⚙️ `schema_infer` / `schema_validate` (advisory) | ❌ | ❌ |
| Status grammar / transitions | ✅ per type | ❌ | ❌ | ❌ |
| Staleness / review cadence | ✅ `owner` + `verified` + `review_days`, review queue | ❌ | ❌ | ❌ |
| Corpus integrity checks | ✅ `check` (dup ids, dangling, cycles) `--strict` CI gate | ⚙️ health checks | ❌ | ⚙️ content-hash detection |
| Auto-repair | ✅ `check --fix` | ❌ | ❌ | ❌ |
| Collision-free id allocation | ✅ DB counter + random ids | permalinks | n/a | n/a |
| **MCP server** | ✅ `docir mcp serve`, 19 tools | ✅ 20+ tools | ✅ | ✅ |
| File watching / auto-sync | ❌ manual `reindex` | ✅ | ✅ | ✅ `watch` |
| Warm daemon | ✅ | server process | — | — |
| Token-aware output | ✅ skeletons + trimmed JSON when piped | ⚙️ | ⚙️ | ⚙️ |
| Import from existing docs | ❌ | ✅ Claude/ChatGPT/Obsidian importers | ✅ collections | ✅ add files |
| Team / device sync | git only | ✅ Cloud, $15/mo | ❌ | ✅ CRDT sync |
| Published retrieval benchmark | ✅ `benchmarks/` (recall@5 0.96, MRR 0.95) | ❌ | ❌ | ❌ |

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
| Enforce decisions against *code* | ❌ | ❌ | ❌ | ✅ `.rules.ts`, CI blocking | ❌ |
| Static site / human browsing | ❌ | ❌ | ✅ **publishes to Pages/S3** | ❌ | ❌ |
| Git-history metadata | ❌ | ⚙️ | ✅ from git log | ❌ | ❌ |
| Agent onboarding | ✅ `agent install` (skill/AGENTS.md) | ❌ | ❌ | ✅ | ✅ 20+ assistants |
| Workflow phases | ❌ | ❌ | ❌ | ❌ | ✅ propose→spec→task→archive |
| Multi-doc types beyond ADR | ✅ 15 types, 5 profiles | ❌ | ❌ | ❌ | ⚙️ specs/tasks |

Legend: ✅ yes · ⚙️ partial / different shape · ❌ no · `?` not documented

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

Ranked by how much they cost docir in adoption, highest first.

### ~~1. No MCP server~~ — **closed in 0.10.0**
`docir mcp serve` (FastMCP, shipped by default) exposes 19 tools over stdio or HTTP,
built on the existing `Dispatcher`, so an MCP tool and its CLI command cannot answer
differently. Reads carry `readOnlyHint`, results are trimmed exactly as the piped CLI's JSON
is, and requests go through the daemon by default, so the embedding model stays warm across
calls. Kept in the list because the gap analysis is what produced it. The remaining
distinction against Basic Memory is coverage of *clients*, not of protocol — see gap 11.

### 2. Document-level retrieval only; no chunking or passage citation *(qmd, sqlite-memory)*
docir embeds and ranks whole documents. qmd and sqlite-memory chunk on heading/paragraph
boundaries and return the passage plus its location, so an agent reads 40 lines instead of a
4,000-line architecture doc. docir's answer is `get <id>` — the whole body. For a long
architecture document that is a large token cost the skeleton contract was meant to avoid.

### 3. No reranking *(Basic Memory: cross-encoder; qmd: local LLM rerank)*
RRF fusion is the state docir stops at. A cross-encoder rerank over the top-N is the standard
next quality step and both close competitors already ship it.

### 4. No file watching / auto-reindex *(all three retrieval competitors)*
Hand-edit a body and the index is stale until someone runs `reindex`. Competitors watch the
directory. The daemon is already resident — it could watch.

### 5. No human-browsable output *(Log4brains)*
Log4brains' pitch is a published, timeline-browsable ADR site on GitHub Pages. docir has no
HTML export, no web UI, no `docir serve`. Decisions that only an agent can read are a hard sell
to the humans who must approve them.

### 6. No enforcement of decisions against the codebase *(archgate, trackfw)*
docir validates the *document graph*; archgate binds an ADR to an executable rule that fails CI
when code violates it. That is the "why is this doc worth writing" argument, and docir doesn't
make it. Related: trackfw enforces ADR → requirement → roadmap traceability.

### 7. No git/code linkage *(Log4brains, adrkit, scholia)*
No `commit`, `pr`, or `path` field; nothing connects a decision to the code it governs, and
nothing derives metadata from git log. This also blocks the natural AST-anchored staleness
signal already noted as deferred.

### 8. No import path for existing docs *(Basic Memory, qmd)*
A repo with 40 ADRs in `docs/adr/` has no `docir import`. `add --id` adopts one id at a time.
Adoption friction on exactly the brownfield repos most likely to want this.

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
docir's `related:` frontmatter is invisible to every markdown editor.

### 12. No team/multi-device sync story beyond git
Basic Memory Cloud (paid) and sqlite-memory (CRDT) both sell shared knowledge across agents and
teammates. docir's answer is "commit it", which is defensible for a repo-scoped tool and a
non-answer for personal/cross-repo knowledge.

## Recommended reading of these gaps

Gaps 1, 2, 3 and 4 are *table stakes* against the retrieval competitors and are all small next
to what already exists. Gaps 5, 6 and 7 are *strategic* — they change what docir is for. Gaps 9
and 12 are arguably **correct omissions** given the "curated corpus, git canonical" thesis;
listing them here is scope-awareness, not a to-do.

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
