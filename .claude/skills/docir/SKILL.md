---
name: docir
description: Use docir to read and write this project's git-backed design docs — decisions/ADRs, issues, architecture notes — instead of editing markdown by hand. Trigger whenever the repo uses docir (a `docir` command is available, a `.docir/` store exists in the repo or `~/.docir`, or docs carry docir frontmatter) and you are about to implement a feature (pull relevant decisions first), record or resolve a decision/issue/ADR, search project knowledge, or restructure/migrate existing markdown docs into docir. Covers the read path (`docir context/get/search/query`) and the write path (`docir init/add/update/archive`) — every doc write MUST go through the CLI.
---
<!-- docir:v0.17.0 — generated file, do not edit by hand; refresh with `docir agent update` after upgrading docir -->

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

## When to use

Use docir whenever this repo manages design docs with it (a `docir` command, a
`~/.docir` dir, or `docs/*.md` with docir frontmatter are present):

- **Before implementing** a feature — pull the relevant decisions/issues first.
- When **recording** a new decision/ADR or issue you discovered.
- When **resolving or updating** an existing doc.
- When **searching** project knowledge.

docir is the ONLY sanctioned way to read/write these docs — **never edit the
markdown files by hand.** (A human may; see *What a human may edit by hand*
below, and re-run `docir reindex && docir check` after they do.)

## Set up in a project

docir keeps docs in **one store**. By default that is the global `~/.docir`
store (shared by every project). To scope docs to *this* repo, run **`docir
init`** once — it creates a `.docir/` store in the repo that every `docir`
command auto-discovers by walking up from the working directory (the way git
finds `.git`):

```
docir init                       # create ./.docir (default profiles: software)
docir init --profiles research   # software | research | ops | qa | legal (CSV)
```

Commit `.docir/docs/` and `.docir/docs-schema.yaml`; the derived index is
gitignored for you. Re-running `docir init` is safe — it writes only what is
missing. `--force` regenerates the `.gitignore` and an *unedited* schema; a
schema you have customised is kept and reported (`schema_preserved`), because it
cannot be rebuilt from the documents. Never reach for `--force-schema` unless
you intend to throw that file away. If you skip `docir init`, docs go to the global `~/.docir`
store — fine for personal notes, but **not** what you want for a repo whose docs
should live with the code.

If your client reaches tools over MCP rather than a shell, `docir mcp serve`
exposes this same vocabulary as MCP tools (`docir_context`, `docir_get`,
`docir_add`, …) through the same dispatcher — everything below still applies,
one name per command. This guide is written for the CLI.

**Every write reports the `store` it landed in.** Check it: `path` is relative to
the store, so it reads as repo-local wherever the store actually is. If `store`
points at a home directory while you are working in a repo, the docs are going
somewhere nobody else will see — `docir` also warns on stderr in exactly that
case. Run `docir init` first.

## Core loop

1. **Discover** before coding: `docir context "<task>"` → minimal ranked set.
2. **Read** the ones that matter: `docir get <id>`, or one section of a long
   one with `docir get <id> --section "<heading>"`.
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
| `docir get <id> --section "<heading>"` | Just that heading and the text under it. Architecture docs here run to tens of thousands of characters and docir ranks a document on its best-matching *section*, so this is usually the part that answered you. An unknown heading errors listing the real ones. |
| `docir search "<text>"` | Full-text over **title, description and body only** — *not* tags. `docir search auth` will not find a doc merely tagged `auth`; use `docir query --tag auth`. Supports `--limit`/`--offset`. |
| `docir query --type decision --status accepted --tag auth` | Structured filter; repeatable `--type/--status/--tag`. Pages with `--limit`/`--offset` — a page shorter than `--limit` means the end. |
| `docir query --code src/auth/login.py` | Which docs declared they govern this file. Repeat `--code` for several paths (any match counts) — run it over the files you are about to change, *before* changing them. A deleted path still finds its docs. |

**Two-tier read (skeleton → body).** `context` / `query` / `search` return
*skeletons* — id, title, description, tags, typed `related`, `owner`,
`verified`, `stale` — **but not the body**. Scan those to judge relevance, then
pull only the bodies you need with `docir get <id>`. This is the cheap path;
never dump every body. On a long document prefer `--section`: each `##` section
is embedded separately, so a hit often means one section matched, and that
section is a fraction of the file.

**A hit that matched through a section names it.** `matched_section` on a
`context` result is the heading whose vector earned the rank — pass it straight
to `docir get <id> --section "<heading>"` instead of pulling the body. Absent
means the match is not addressable as a section (the document's own vector, a
full-text hit, a graph neighbour), not that nothing matched.

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

**When a result looks wrong, ask why with `--explain`.** `docir context "<task>" --explain`
attaches the trace behind each hit: where it placed in the full-text and vector rankings, each
RRF term, the raw cosine, and — for a graph-reached document — the seed it came from and
whether that edge was a `successor`, an ordinary `related` or a `mention`. `docir search
"<text>" --explain` gives the thinner version: rank and BM25.

It answers the question `--min-score` cannot: not "is anything relevant here" but "why did *this*
outrank *that*". A hit with a `semantic_rank` and no `lexical_rank` shares no vocabulary with
your wording and was found by meaning alone; the reverse means the embedder contributed nothing.
Off by default — it is a diagnostic, and a skeleton read is meant to be cheap.

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
- **Do not verify inside the task that moved the code.** If you edited
  `src/auth.py` this session, stamping `--verified` on the decision that governs
  it certifies your own change and turns the signal into "the check is green".
  Report the finding instead and let the next reader — or the human — clear it.
- **Naming a document's id in a body links to it.** `docir check` reads those
  mentions, so a document you cite in a paragraph is not reported as an orphan,
  and `docir get` shows both directions (`mentions`, `mentioned_by`) — including
  the useful one, who cites *this* document. It is derived: it never appears in
  frontmatter, and `docir reindex` rebuilds it. Use `--related` when the link is
  a claim worth typing (`supersedes`, `refines`); prose is enough when you are
  simply referring to something.
- **If a test enforces the decision, govern that test.** docir has no rule
  engine and will not gain one: the test already fails when the code
  contradicts the decision, and `--code tests/test_x.py` records which decision
  it enforces, so `check` notices when that test is deleted.
- `--type` retypes a document. Its **id never changes**, prefix included — the id
  is the only address every `related` edge has for it, so `adr-3f9a2b1c` stays
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
- When a body edit changes what the doc is about, update `--set-description`
  in the same call; it drives search quality.

## Migrating existing docs into docir

To restructure a repo's existing markdown (design notes, ADRs, RFCs) into docir,
work in this order — the constraints below make any other order fail:

1. **Init first** and pick a fitting profile (see *Set up in a project*). Default
   types are `decision`/`issue`/`architecture`/`release_note`; enable
   `research`/`ops`/`qa`/`legal` in `docs-schema.yaml`, or add inline `types:`
   (see *Editing the schema*), for docs that don't fit — a doc whose `type` isn't
   in the schema is a Tier 0 error. Confirm with `docir schema show`.
2. **Register tags** you'll apply: `docir tag add <key> --description "..."`
   (every `--tags` key must exist first).
3. **Read each source file, then add it — one at a time.** There is deliberately
   no bulk import: adoption is a *judgement* task, not a conversion task, and a
   command that turned N files into N documents would look finished while being
   wrong. Read the file first and decide:
   - **Is it one document, or several?** A `decisions.md` holding six decisions
     is six `docir add` calls, not one. This is the most common shape in an old
     corpus and the easiest to miss.
   - **Is it still true?** Drafts, superseded decisions and abandoned proposals
     should be added with the right `--status` (or not added at all). A file's
     text may say "superseded by #7" while nothing in its structure does.
   - **What is the real description?** It drives retrieval. The opening
     paragraph is usually context, not a summary — write a better one.
   - **What type is it?** A single bulk-import pass would force one type; a real
     corpus mixes decisions, issues and architecture notes.

   Then add it, stripping any existing YAML frontmatter from the body:
   ```
   docir add --type decision --title "..." --description "..." \
     --status accepted --stdin < old/adr-001.md
   ```
   **Never invent an id.** You may *preserve* one: if the source file already
   carries a number other documents cite, pass it with `--id` so the historical
   cross-references keep resolving.
   ```
   docir add --type decision --id adr-0007 --title "..." --description "..." \
     --status accepted --stdin < old/adr-007.md
   ```
   `--id` is refused if the id is taken or its prefix does not match the type, and
   the next allocation lands past it. It only helps a store using
   `--id-style sequential`; a `random`-style store has no numbering to preserve,
   so let docir assign. Either way, record the returned id for each source file.
4. **Wire relationships in a second pass**, after every doc exists and has an id:
   `docir update <id> --set-related <other-id>:supersedes`. Links can't be set in
   step 3 because every `--related` target must already exist.
5. **Validate**: `docir check` — it flags dangling links, duplicate ids, unknown
   types, and stale docs. Fix those. `orphan` findings just mean a doc has no
   relations yet, which is normal; don't force links to silence them.

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

## Staleness (`owner` / `verified`)

For docs that need periodic re-confirmation, set an `--owner` and, when you
(or a human) confirm a doc is still correct, run `docir update <id> --verified`.
A type's review cadence (`review_days` in the schema) drives a non-blocking
`stale` warning in `docir check` and a `stale` flag on read views. Editing the
body does not equal verifying it — `--verified` is the explicit signal.

Pull the review queue rather than reading `check` output for it:

```
docir query --stale                          # everything overdue
docir query --owner platform-team --stale    # one steward's queue
```

`--stale` is applied before `--limit`, so the limit counts overdue docs. Work the
queue by reading each one (`docir get <id>`), then either fixing it or, if it is
still correct, `docir update <id> --verified`.

**Stale is not the same as wrong.** It means nobody has vouched for the doc
within its cadence. Never mark `--verified` on a doc you have not actually read —
that is the one signal the whole mechanism rests on, and stamping it blind makes
the corpus look reviewed when it is not.

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

## Editing the schema

`docs-schema.yaml` is the one file you edit by hand (no CLI write path). Prefer
adding a **profile** over inline types; add inline `types:` only for something
no profile covers. Run `docir schema validate` after every edit.

`schema validate` answers two questions: whether the file loads, and **what it
costs the corpus** — how many documents carry a type, status, required field or
relation kind the schema no longer accepts, with a sample of their ids. Check
that number before you commit a schema edit; it is the one thing `git diff`
cannot show you, since the core and profiles merge in at load. It never changes
the exit code — the schema is valid, and the documents are what moved.

Three keys are **required** on every type — omitting any is a `SchemaError`:

| key | type | notes |
|---|---|---|
| `prefix` | str | mints ids (`tp` → `tp-0001`). **Unique across the whole merged schema**, so check `docir schema show` first. |
| `statuses` | **mapping** | `status: [targets it may transition to]`, *not* a list. Terminal status → `[]`. |
| `default_status` | str | must be a key in `statuses`. |

**Every status name you write must be a key in that type's `statuses`** — a
transition target, `default_status`, and each `inactive_statuses` entry. A typo
(`open: [closd]`) is rejected at load with the declared names listed, so it fails
on the next command rather than surviving until a write. That check runs on
*every* command, not only `schema validate`: a broken schema stops the store.

Optional: `required` (extra frontmatter fields), `inactive_statuses` (hidden from
default reads), `level` (int; see below), `review_days` (staleness cadence; 0 =
never stale), `id_style` (`sequential` | `random`), `allowed_relations`.

`level` only bites on **dependency** edges: a `depends_on` or `refines` edge from
a higher-level type to a lower-level one is a Tier 1 `layering` warning. Ordinary
`relates_to` links never are — linking a decision to the issue that motivated it
is normal and silent.

```yaml
relation_types: [governs, blocks]   # extra kinds on top of the core six
types:
  test_plan:
    prefix: tp
    default_status: draft
    statuses:
      draft: [active]
      active: [deprecated]
      deprecated: []
    inactive_statuses: [deprecated]
    level: 3
    review_days: 180
```

`relation_types` also takes a **mapping**, which is how you declare what a kind
*means*. Three optional properties, all defaulting to false:

| property | effect |
|---|---|
| `symmetric` | the edge says the same thing both ways, so a mutually-referencing pair is not a `cycle` finding |
| `dependency` | the source *relies on* the target — the only claim the Tier 1 `layering` check reads |
| `successor` | the *incoming* direction answers "is this still current?", so `docir context` follows it backwards |

```yaml
relation_types:
  governs:     {dependency: true}
  duplicates:  {symmetric: true}
  replaced_by: {successor: true}
  blocks:      {}                  # registered, all defaults
```

Defaults are asymmetric on purpose: a kind you do not describe is still
cycle-checked (so a `blocks` loop is reported) but adds no layering warning and
changes no traversal. The core six carry their meaning without being listed —
`relates_to` and `contradicts` are symmetric, `supersedes`/`contradicts` are
successors, `depends_on`/`refines` are dependencies. `docir schema show` prints
the resolved properties of every kind.

Merging only **adds** types: the core is always merged, and an inline block can
only override a type by its own name. `disable_types:` is how you give one up —
and it is what frees that type's `prefix`, so your own type can claim it and the
corpus keeps the ids it already has.

```yaml
profiles: [software]
disable_types: [decision]        # the name stops resolving, and `adr` is free
types:
  product_decision:
    prefix: adr                  # every existing adr-... id stays valid
    default_status: draft
    statuses: {draft: [active], active: []}
```

Then move the documents over — one at a time, because only you know what each old
status becomes:

```bash
docir query --type decision --limit 500 | jq -r '.[].id' \
  | xargs -I{} docir update {} --type product_decision --status active
```

Until they are moved, `docir check` reports them as `unknown-type` (a warning, so
nothing is blocked) beside the `schema-drift` finding naming the change. Disabling
a name nothing declares, or one the same file declares inline, is refused.

`allowed_relations` is a **whitelist trap**: absent/empty means permissive (any
kind, any target), but listing one kind restricts the type to *only* the listed
kinds — re-list every kind you still want, including `relates_to`.

```yaml
    allowed_relations:
      relates_to: []                  # [] = any target type
      depends_on: [runbook, decision] # only these target types
```

## What a human may edit by hand

You must not — every write goes through the CLI. A human working in the repo
will, though, and the rules differ per field. If you are asked to reconcile a
hand-edited corpus, this is the contract:

| file / field | by hand? | why |
|---|---|---|
| a document's **body** (below the `---`) | ✅ yes | Prose. `reindex` picks it up; nothing else depends on it. |
| `docs-schema.yaml` | ✅ yes | No CLI write path exists — this is the intended way. |
| `docs/tags.yaml` | ✅ yes | A `key: description` mapping; `reindex` loads it. `docir tag add` is easier. |
| `title` / `description` | ⚠️ prefer CLI | Works, but they drive retrieval — `--set-description` also re-embeds. |
| `tags` | ❌ use `docir update --set-tags` | An unregistered tag is a Tier 0 error the CLI would catch; by hand it silently isn't (`check` reports `unknown-tag`). |
| `status` | ❌ use `docir update --status` | Bypasses the transition rules; a status the type doesn't declare leaves the doc with no legal exit (`check` reports `unknown-status`). |
| `related` | ❌ use `docir update --set-related` | Targets must exist and kinds must be registered; by hand you get `dangling` or `unknown-relation-kind` instead. |
| `type` | ❌ | Must be in the schema, and the id prefix already encodes it (`check` reports `unknown-type`). |
| `id` | ❌ **never** | It is the primary key. Changing it orphans every inbound link and can duplicate a live id. |
| `created` / `updated` | ❌ | `updated` is the staleness clock's fallback. |
| `verified` | ❌ **never** | It means "somebody re-read this and it is still true". Nothing can check that, so writing it by hand is simply a false statement. Use `docir update <id> --verified`. |

**After any hand-edit: `docir reindex` then `docir check`.** Reindex reports
`documents_skipped` for files whose frontmatter will not parse — those are
*absent from every read path*, not merely flagged. `check` then catches
`unknown-tag`, `unknown-status`, `unknown-type`, `unknown-relation-kind`,
`missing-required`, `dangling` and `duplicate-id`.

It cannot catch everything: a plausible-but-wrong `verified` date, or edited
`created`/`updated`, are indistinguishable from real ones. Those are the fields
to leave alone.

## Checks & maintenance (non-blocking)

- `docir check` — Tier 1 warnings: cycles, orphans, layering, **dangling** `related` links, **duplicate ids**, **stale** docs (past their review cadence), **unknown type/status/tag** (a `type` not in the active schema, a `status` the type doesn't declare, a tag not in the registry — all three mean a file was edited outside the CLI), **missing-required** (a field the type requires that the document lacks), **unknown-relation-kind** (an edge whose kind the schema no longer registers), and **schema-drift** (the schema itself changed since the index was built) and **stale-index-build** (the index was built by a docir that is no longer installed). Run before finishing.
- **`unblocked`** — a live document whose every `depends_on` target has closed. The one
  finding that is good news: it means the work is ready to start. Act on it by starting the
  work or by dropping an edge that is no longer true; nothing clears it mechanically.
- `docir check --strict` — exits nonzero on **error**-severity findings only (`duplicate-id`, `dangling`, `malformed` — the corpus is broken). Use as a **CI / pre-merge gate**. Warnings (`orphan`, `cycle`, `layering`, `stale`, `unknown-type`, `unknown-status`, `unknown-tag`, `missing-required`, `unknown-relation-kind`, `schema-drift`, `stale-index-build`) are reported but never fail the build; `--strict-all` makes them fatal too.
- **Recovering from `missing-required`**: the schema now requires a field the document was
  written without — usually because `docs-schema.yaml` gained a `required:` entry, or an upgrade
  brought one in through a profile. Supply it (`docir update <id> --set-owner ...`) or drop the
  requirement from the schema. Until then **every** write to that document is refused, including
  one that touches nothing else — so fix these before editing an old document.
- **Recovering from `unknown-type`** (a doc whose `type` isn't in the active schema, usually
  because a profile was disabled): re-enable the profile in `docs-schema.yaml`, or change the
  doc's `type` to one the schema knows — then `docir reindex`. `check --fix` deliberately will
  not guess which you meant. Until it is resolved the doc cannot be validated, is never
  reported stale, and is skipped by the layering check.
- `docir check --fix` — repair what can be repaired without guessing: re-issue duplicate ids (the oldest file keeps the id, so existing links stay valid) and drop `related` edges pointing at nothing. It reports every change, then lists what it could not fix. `malformed` and `unknown-type` are left alone — those need you to decide what the file or the schema should say. **This is the supported way to recover; do not hand-edit markdown to fix these.**
- **Recovering from `schema-drift`**: the active schema differs from the one the index was built
  against — usually an upgrade, since the types, statuses and cadences come from the installed
  docir as much as from `docs-schema.yaml`. Each finding names one change (`+type test_plan`,
  `type decision: required [] -> ['owner']`). Deal with the consequences it explains — the
  `unknown-type`, `unknown-status` and `missing-required` findings beside it — then `docir
  reindex`, which is what records the new baseline. Set `DOCIR_SCHEMA_NOTICE=1` to have every
  command print the drift on stderr instead of waiting for a `check`.
- **`docir self upgrade` — upgrade docir and resync this store, in one command.** It
  installs the newest docir where docir owns its environment (a uv tool, a pipx install, a
  virtualenv), re-executes as the new build, then reindexes (the index is derived and
  gitignored, and a rebuild is what records the schema baseline *and* the version that built
  it), refreshes any installed agent instruction file, and reports what `check` still finds.
  Where docir does *not* own its environment — a checkout, a project whose lockfile pins it,
  an ephemeral `uvx` run — it says so on stderr and does the rest; the package is that
  project's to upgrade. Pass `--no-package` to skip the install and only resync the store.
  **`stale-index-build`** is the finding that asks for this: the index was built by a docir
  that is no longer installed. A warning, never a `--strict` failure — every store is in that
  state between an upgrade and the next rebuild.
- `docir self status` — what is installed, how, and whether a newer release exists. A file
  read: it reports the answer the daemon last cached, and an absent `latest` means *nobody
  has checked*, not "up to date". `--refresh` asks PyPI now (docir's only network call, and
  it is skipped if the answer is already from today). Set `DOCIR_UPDATE_CHECK=1` to have the
  daemon keep it fresh and every command say on stderr when a newer docir is out.
- `docir lint --deep` — Tier 2 advisories: duplicate content, oversized documents,
  **oversized sections** (a section the chunker has to split, so part of it is text no
  heading can address), **ambiguous headings** (used twice in one document, so a section
  read reaches only the first), and **unqualified section references** (prose naming a
  section that lives in another document). All advisory — a long reference table is often
  right as it is.
- `docir bench <fixture.yaml>` — score this store's retrieval against tasks whose answers you
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
- `docir reindex [--changed]` — after a doc file was hand-edited, merged, or freshly cloned.
  `--changed` only skips re-saving files whose content is unchanged; deleted files are swept
  from the index either way, so both modes leave the index agreeing with the filesystem.
  **Read `documents_skipped` in the output.** A file whose frontmatter does not parse is
  skipped, not indexed — it exists on disk and is invisible to every read path. Non-zero
  means run `docir check` and fix the named file before trusting a search.

## Other repositories' decisions

If `.docir/stores.yaml` exists, this store reads peers alongside its own, and
`context`, `query`, `search` and `get` already cover them — every row carries a
`store` field naming where it came from. Add one for a single command with
`--store ../platform/.docir`.

Writes never federate: `add` and `update` always land in this repo's store, and
so does everything `check` reports. Neither does `docir build` — a published
site is this store's corpus, because a copy of a peer's decision goes stale the
moment that repo edits it. If a peer is unreadable docir says so on
stderr and answers from the rest — treat that as information, not as a failure
to retry.

## Publishing for humans

`docir build --out site/` renders the whole store as a self-contained static
site — one page per document, no external requests, publishable to GitHub Pages
unchanged. Reach for it when someone asks for the decisions in a reviewable
form; it shows the relation graph in both directions and flags stale documents.

```bash
docir build --out site/ --title "<project> — design docs"   # heading, tab, wordmark
docir build --out site/ --logo assets/logo.svg              # mark + favicon
docir build --out site/ --mermaid vendor/mermaid.min.js     # draw mermaid fences
docir build --out site/ --include-archived                  # archived docs too
```

Always pass `--title`: it is what the site calls itself, and the default is the
word "Documentation" on every page. `--logo` sets the top-left mark *and* the
favicon — pass it when the repo has its own logo, otherwise the site carries
docir's. Archived documents are left out unless you ask for them. `--out` is
regenerated each build, and a directory docir did not build is refused unless
you pass `--force`.

A ` ```mermaid ` fence in a body publishes as its own source unless you pass
`--mermaid` pointing at a **UMD** mermaid bundle — mermaid 11 ships only ES modules and docir
loads the runtime as a classic script, so 10.x is the last line that has one. Fetch it once:

```bash
curl -o mermaid.min.js https://cdn.jsdelivr.net/npm/mermaid@10.9.3/dist/mermaid.min.js
docir build --out site/ --title "<project>" --mermaid mermaid.min.js
```

An `.mjs` runtime is refused with that URL in the error; docir writes it beside the
pages and loads it from there, so the site still opens from `file://`. docir
does not ship the bundle — it is megabytes — and writes it only when a document
actually draws something.

## Working across git branches

Only `docs/*.md` + `tags.yaml` are committed; the index is derived and gitignored.
After any merge/pull, and on a fresh clone: `docir reindex` then `docir check`.
The reindex is what rebuilds the index *and* resyncs the id counter from the
files — skip it on a fresh clone and the next `docir add` will refuse to write,
telling you to run it.

`docir init` writes `id_style: random` by default, which mints collision-resistant
ids (`adr-3f9a2b1c7d4e`) so two branches never allocate the same id. A store
created with `--id-style sequential` (or an older schema with no `id_style:` key)
mints readable numbers (`adr-0007`) that are collision-free *within one store* —
but two branches each have their own index and can mint the same number, which
`docir check` reports as `duplicate-id` after the merge. Set `id_style` at the top
of `docs-schema.yaml` for the whole schema, or per type to override it.

## When the answers look wrong

A long-lived daemon serves your reads, and it loads docir once. After an upgrade or a change to
docir's own source it can keep answering from the code it started with — a stale answer imitates
a correct one, so nothing looks broken.

- `docir daemon status` — whether it is running and **which build it is serving**.
- Re-run the command with `docir --no-daemon <cmd>` to answer in-process from the installed
  code. Two different answers to the same command means the daemon is the stale half; it is
  disposable, so `docir daemon stop` and let the next command respawn it.

Reach for this when results contradict what you can see in the files, not as a routine step.

## Notes

- Errors print `error: <message>` to **stderr** with a nonzero exit code (2=validation, 4=not-found, 5=conflict, 6=stale), so a captured stdout stays clean JSON.
- Vectors are computed async; add `--wait-embeddings` to a write (or `docir embed --flush`) if you must `context`-search immediately after.
- `docir context` matches on meaning, not just wording, so describe the task in your own words rather than guessing the documents' vocabulary. (If the store runs `DOCIR_EMBEDDER=deterministic` — a light, model-free fallback — matching is vocabulary-based instead; when a query under-retrieves there, retry with the terms the codebase actually uses.)
- All state lives under `~/.docir` (override `DOCIR_HOME`); the index is disposable and rebuildable from files.
