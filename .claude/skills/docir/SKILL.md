---
name: docir
description: Use docir to read and write this project's git-backed design docs — decisions/ADRs, issues, architecture notes — instead of editing markdown by hand. Trigger whenever the repo uses docir (a `docir` command is available, a `.docir/` store exists in the repo or `~/.docir`, or docs carry docir frontmatter) and you are about to implement a feature (pull relevant decisions first), record or resolve a decision/issue/ADR, search project knowledge, or restructure/migrate existing markdown docs into docir. Covers the read path (`docir context/get/search/query`) and the write path (`docir init/add/update/archive`) — every doc write MUST go through the CLI.
---
<!-- docir:v0.23.0 — generated file, do not edit by hand; refresh with `docir agent update` after upgrading docir -->

# docir — Agent Guide

Git-backed markdown docs (decisions, issues, architecture) with a derived index
(full-text + relation graph + semantic search). Files are the source of truth;
every write goes through the `docir` CLI to keep frontmatter/schema valid.

Prefix all commands with `docir`. **When you capture a command's output it is
already compact single-line JSON** — stdout isn't a TTY, so you don't need
`--json` (it forces the same). To save tokens, fields that hold no value are
omitted: **an absent field means its default** — no `owner`/`verified`/`related`,
empty `tags` — and `score`/`similarity` are rounded. Pass `--no-trim` for the
full, unrounded payload, or `--pretty` to force the human table view.

## Where the rest of this guide lives

This file covers the everyday loop: discover, read, write. Everything else sits
in one file per task — open the one that matches what you are doing, and read it
whole. Each is self-contained; you never need to chain from one to another.

| file | open it when |
|---|---|
| [`reference/setup.md`](reference/setup.md) | putting a repo on docir: `docir init`, profiles, migrating existing markdown, branches and fresh clones |
| [`reference/retrieval.md`](reference/retrieval.md) | a plain `context` is not enough: `--expr` queries, hypothetical-answer `--also`, `--explain`, peer stores, scoring the corpus with `docir bench` |
| [`reference/schema.md`](reference/schema.md) | editing `docs-schema.yaml`: types, statuses, relation kinds, store-defined `checks:`, `allowed_relations` |
| [`reference/maintenance.md`](reference/maintenance.md) | `docir check` reported something, a human hand-edited the corpus, or a document is stale |
| [`reference/publishing.md`](reference/publishing.md) | someone wants the decisions as a browsable site (`docir build`) |
| [`reference/troubleshooting.md`](reference/troubleshooting.md) | a read contradicts the files, docir needs upgrading (`docir doctor`, `docir self upgrade`), or you need the exit codes |

## When to use

Use docir whenever this repo manages design docs with it (a `docir` command, a
`~/.docir` dir, or `docs/*.md` with docir frontmatter are present):

- **Before implementing** a feature — pull the relevant decisions/issues first.
- When **recording** a new decision/ADR or issue you discovered.
- When **resolving or updating** an existing doc.
- When **searching** project knowledge.

A human working in the repo *may* edit the files by hand; you may not.
`reference/maintenance.md` holds the per-field contract and what to run after.

## Core loop

1. **Discover** before coding: `docir context "<task>"` → minimal ranked set.
2. **Read** the ones that matter — all of them in one command:
   `docir get <id> <id> "<id>#<heading>"`.
3. **Implement** (outside docir).
4. **Record** new decisions/issues: `docir add ...`.
5. **Update** status when resolving: `docir update <id> --status resolved`.
6. **Commit** the changed docs under the store (`.docir/docs/*.md` in a project;
   the index is derived and gitignored).

## Read

| Command | Use |
|---|---|
| `docir context "<task>" [--limit N] [--expand N]` | Best first step: full-text and vector rankings fused, plus 1-hop related docs. Graph-pulled items marked `via_graph`. |
| `docir get <id>` | Full doc (body included); works for any status. |
| `docir get <id> --section "<heading>"` | Just that heading and the text under it. An unknown heading errors *listing the real ones* — that is where you learn the right name. |
| `docir get <id> <id> <id>` | Several docs in one command. Address a section inline: `docir get adr-3f9a2b1c7d4e "arch-0002#Decision"`. **Always batch** — a docir read costs mostly process start, so three separate `get` calls cost about three times one. |
| `docir search "<text>"` | Full-text over **title, description and body only** — *not* tags. `docir search auth` will not find a doc merely tagged `auth`; use `docir query --tag auth`. Supports `--limit`/`--offset`. |
| `docir query --type decision --status accepted --tag auth` | Structured filter; repeatable `--type/--status/--tag`. Pages with `--limit`/`--offset` — a page shorter than `--limit` means the end. |
| `docir query --code src/auth/login.py` | Which docs declared they govern this file. Repeat `--code` for several paths (any match counts) — run it over the files you are about to change, *before* changing them. A deleted path still finds its docs. |

**Two-tier read (skeleton → body).** `context` / `query` / `search` return
*skeletons* — id, title, description, tags, typed `related`, `owner`,
`verified`, `stale` — **but not the body**. Scan those to judge relevance, then
pull only the bodies you need; never dump every body. On a long document prefer
a section: docir embeds each `##` section separately and ranks a document on its
best-matching one, so a hit usually means one section answered you — and these
documents run to tens of thousands of characters.

With two or more ids the reply is `{"documents": [...], "missing": [...]}`
instead of a bare document. An id that no longer exists, or a heading that does
not, appears in `missing` as `{"ref", "error"}` beside the documents that did
resolve — a stale id costs you that one body, not the whole read.

**A hit that matched through a section names it.** `matched_section` on a
`context` result is the heading whose vector earned the rank — pass it straight
to `docir get "<id>#<heading>"` (or `--section` for a single document) instead
of pulling the body; one `docir get` mixes whole documents and sections of
others. Absent means the match is not addressable as a section (the document's
own vector, a full-text hit, a graph neighbour), not that nothing matched.

Default read path **hides** closed and archived docs. "Closed" means the type's
*inactive* statuses — `superseded`/`rejected` for a decision, `resolved` for an
issue, `deprecated` for architecture. Add `--include-inactive`
(query/search/context) or use `docir get` to see them. (`--include-resolved` is
the old spelling, still accepted; it named a status only two types have.)

**`--limit` is a hard ceiling** on what `context` returns — it is your token
budget, not a suggestion. Related docs are pulled *inside* it: `--expand N`
(default 2) reserves at most N of those slots for `via_graph` items, and slots
the graph does not use go back to ranked hits. `--expand 0` gives you ranked
hits only.

**Expansion runs both ways, and successors come first.** A `supersedes` edge
points from the *new* doc to the old one, so the replacement sits one hop
*backwards*. `context` follows that direction too and puts successors ahead of
ordinary links, which means: if a hit arrives with another doc marked
`via_graph` that supersedes it, **the newer one is the current decision** — check
before acting on the hit. It does not mean the old doc is wrong to read, only
that it is not the last word.

**Judge relevance by `similarity`, never by `score`.** `score` is a rank fusion:
it tells you the order and nothing else, so the top hit of a query nothing
matches scores about the same as a perfect match. `similarity` is the raw cosine
against your task (0.0-1.0) and is the number that means something.

- Roughly: **>0.7** on topic, **0.4-0.7** related, **<0.4** probably noise. Read
  the descriptions before trusting a low one — these are guides, not thresholds.
- `docir context "<task>" --min-score 0.5` filters for you, and **an empty result
  is a real answer**: nothing in the corpus is close enough. Say so and proceed,
  rather than treating the top-ranked document as relevant because it was
  returned.
- Two things it does not filter: `via_graph` items (they are there because a
  selected doc links them, not because they scored) and hits whose `similarity`
  is **absent** — that means no current vector, not zero. Run `docir embed
  --flush` if you need the floor to cover everything.

## Write

```
docir add --type decision --title "..." --description "..." \
  [--tags auth,api] [--related adr-0001,arch-0002:implements] [--status ...] \
  [--owner platform-team] [--code "src/auth/**,src/api/routes.py"] \
  (--stdin | --body "..." | --body-file f.md)

docir update <id> --status resolved             # metadata patch
docir update <id> --set-description "..."        # keep summary current on edits
docir update <id> --set-related adr-0001:supersedes   # replace typed edges
docir update <id> --set-owner platform-team     # assign a steward
docir update <id> --set-code "src/auth/**"      # what code this doc governs
docir update <id> --type architecture --status draft   # retype; the id never changes
docir update <id> --verified                     # stamp today as last-verified
docir update <id> --append-section "Resolution" --body "Fixed in PR 42"
docir update <id> --replace-section "Context" --body "..."
docir update <id> --remove-section "Notes"       # delete a heading and its text
docir update <id> --replace-body --force --body "..."   # full overwrite
docir archive <id> | docir unarchive <id>
docir delete <id> [--force]   # --force also unlinks it from referencing docs
```

- Prefer `--stdin` for multi-line markdown bodies (no shell-escaping).
- `--code` records the code a document governs, as repo-relative globs. Set it
  when you know which files a decision is about; only the shape is checked on
  write, so a pattern may name code that does not exist yet. It rides on every
  read view, so a later session can see which decisions concern the files it is
  editing, and `docir check` warns (`unmatched-code`) once a pattern stops
  matching — repoint it with `--set-code` when you move the code it names.
- **`docir update <id> --verified` records what that code looked like.** From
  then on `docir check` warns (`code-changed`) as soon as the governed files
  differ from what they were — the question a review cadence cannot answer.
- **Verifying is a judgement, and you may make it.** Read the document against
  the code as it now stands, decide whether it is still true, and stamp
  `--verified` only if it is. If it is not, fix the document first. Nothing
  mechanical clears the finding — `check --fix` deliberately leaves it, because
  a repair has nothing to read with.
- **Writing in a document does not clear `stale`.** Only `--verified` does. A
  doc nobody has stamped counts its cadence from the day it was written, so
  recording that an open question is *still* open leaves it in
  `docir query --stale` — where that note used to delete it.
- **Do not verify inside the task that moved the code.** If you edited
  `src/auth.py` this session, stamping `--verified` on the decision that governs
  it certifies your own change and turns the signal into "the check is green".
  Report the finding instead and let the next reader — or the human — clear it.
- **Naming a document's id in a body is a soft link, not an edge.** `docir get`
  shows both directions (`mentions`, `mentioned_by`) — including the useful one,
  who cites *this* document — and `docir context` follows them. It is derived: it
  never appears in frontmatter, and `docir reindex` rebuilds it. **It does not
  clear `orphan`**, deliberately: the body most likely to name a list of orphan
  ids is the triage of that list, so prose used to close the very queue it was
  diagnosing. Use `--set-related` when the link is a claim worth typing
  (`supersedes`, `refines`).
- **An orphan ends in an edge or in a recorded reason.** `orphan` means no
  `related:` edge in either direction. Close each one the honest way:

  ```bash
  docir update <id> --set-related <other-id>:refines            # it was unwired
  docir update <id> --set-isolated "scope deferred; nothing depends on it yet"
  ```

  `--set-isolated` is for the document that stands alone *by design*, and it
  records why — a reviewer reading `docir query --expr "isolated"` sees the
  judgement, not just the silence. Withdraw one with `--set-isolated ""`.
  Reach for it only when isolation is the conclusion; an edge is the usual
  answer.
- **If a test enforces the decision, govern that test.** docir has no rule
  engine and will not gain one: the test already fails when the code
  contradicts the decision, and `--code tests/test_x.py` records which decision
  it enforces, so `check` notices when that test is deleted.
- `--type` retypes a document. Its **id never changes**, prefix included — the id
  is the only address every `related` edge has for it, so `adr-3f9a2b1c7d4e` stays
  itself under a type whose prefix is something else. The file moves into the new
  type's directory. The status carries over if the new type declares it and the
  write is refused if it does not, so pass `--status` too when they differ.
- `delete` is blocked while another doc links to it. `--force` deletes anyway and
  **strips the edge from each referencing doc**, naming them in its output — so a
  forced delete never leaves a dangling link. Prefer `archive` when the document
  is merely no longer current: it keeps the history and the graph intact.
- Body edits, safest→riskiest: `--append-section` (default choice) →
  `--replace-section` → `--replace-body` (needs `--force`; fails "stale write"
  if the file changed on disk — `docir get` first).
- Name a section by its **text alone** — `"Resolution"`, not `"## Resolution"`.
  The `##` is written for you, and every section flag matches on the text.
- **`--body` is what goes *under* the heading, never the heading itself.**
  `docir get <id> --section "Notes"` returns the heading line too, so editing
  that and passing it straight back would write `## Notes` twice; docir refuses
  it and says so. Strip the first line, or pass only the replacement prose.
- **`--remove-section "<heading>"` deletes a heading and the text under it**, and
  takes no `--body` — passing one errors, because it would read as "delete this
  text" and do something else. Reach for it when a document carries a heading twice
  — `--replace-section` keeps the first heading line by contract and cannot undo
  one, `--append-section` only adds another. A repeated heading resolves to the
  first, so removing the second of two is the same command run twice.
  `docir lint --deep` reports which documents have one (`ambiguous-heading`).
- When a body edit changes what the doc is about, update `--set-description`
  in the same call; it drives search quality.

## Typed edges (`related`)

Each `related` entry is a **typed edge**: a target id plus a relation *kind*.

- Compact form: `<id>` (defaults to `relates_to`) or `<id>:<kind>` —
  e.g. `--related adr-0007:supersedes,issue-0003:depends_on`.
- Core kinds: `relates_to` (default), `supersedes`, `depends_on`, `implements`,
  `contradicts`, `refines`. An unknown kind is a Tier 0 error (like an unknown
  tag). Some types constrain which kinds/targets they allow.
- Prefer a typed edge over prose when a real relationship exists — traversal is
  exact and cheap. Model "A replaces B" as `A --supersedes--> B` (not only a
  status change on B).

## Tags (must exist before use)

```
docir tag add auth --description "Authentication, tokens, sessions."
docir tag list
docir tag rename auth authn         # rewrites every referencing doc
docir tag rename auth authn --merge # fold into an EXISTING tag (else refused)
docir tag rm auth [--force]         # --force strips it from docs; else blocked
```

## Hard rules (Tier 0 — these fail the write)

- Never edit `docs/*.md` directly. Always use the CLI.
- `id` is auto-assigned `<prefix>-NNNN`; never invent one. Prefixes: decision→`adr`, issue→`issue`, architecture→`arch`.
- Every `--tags` key must be registered first; every `--related` id must exist.
- `--status` must be a valid transition (see below). `--override` forces an illegal
  jump and **warns**, naming the rule it broke — a last resort for a document
  stranded by a schema change, not a way around the state machine. It cannot set a
  status the type doesn't declare. Nothing is written to the file, so prefer stepping
  through the legal statuses when a path exists.

## Types & statuses (default schema)

| type | statuses (→ = allowed transition) | hidden by default |
|---|---|---|
| decision | proposed → accepted / rejected; accepted → superseded / rejected | rejected, superseded |
| issue | open → resolved | resolved |
| architecture | draft → active → deprecated | deprecated |
| release_note | draft → published | — |

The default schema is the frozen **core** (`decision`) plus the **software**
profile (`issue`, `architecture`, `release_note`). Other bundled profiles add
domain types — `research` (hypothesis/experiment/finding), `ops`
(runbook/incident/postmortem), `qa` (test_plan/test_case), `legal`
(policy/contract/obligation) — enabled per install with `profiles: [..]` in
`docs-schema.yaml`.

**Never guess the active schema — read it:**

```
docir schema show        # the merged result (core + profiles + inline)
docir schema validate    # check docs-schema.yaml before it reaches a write
```

