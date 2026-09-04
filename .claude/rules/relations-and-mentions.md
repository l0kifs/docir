---
paths:
  - "src/docir/modules/documents/domain/entities/relation.py"
  - "src/docir/modules/documents/domain/value_objects/relations.py"
  - "src/docir/modules/documents/domain/value_objects/doc_ref.py"
  - "src/docir/modules/documents/application/services/document_service.py"
  - "src/docir/platform/naming/**"
---

# Relations and mentions

There are two graphs over the same documents. One is authored and gates merges; the other is derived from prose and must never gate anything.

- **There are two relation graphs, and only one of them is authored.** `related:` is typed,
  hand-written and policed by `dangling`/`cycle`/`layering` and the delete guard. **Mentions**
  are derived: `Document.mentioned_ids(prefixes)` scans the body for ids and
  `uow.mentions.replace` stores them (table `mentions`, migration `0008`), rebuilt by
  `reindex`, never written to frontmatter. **No Tier 1 check reads them.** `orphan` did, and
  adr-e98749aa457d took it away: an orphan triage is a list of orphan ids, so writing the
  diagnosis cleared every id it diagnosed — including the four of ten this corpus's author had
  just concluded were still unwired, and the triage document itself. "This id is fine standing
  alone" and "this id still needs an edge" are the same characters, so no filter over prose can
  separate them; the judgement had to become `isolated:` (below). The false positive that put
  mentions in the check — `orphan` on a document its author linked in a sentence — is real and
  is now answered by that field; removing prose from the check restored **zero** orphans on
  this store's 194 live documents, because every one of them carries an authored edge.
  `MentionRepository.all_resolved` went with the reader; the mention graph's remaining readers
  are `context` expansion, `get`'s `mentions`/`mentioned_by`, and Tier 2 `unresolved-mention`.
  Do not feed them to any check: a cycle nobody wrote is noise, a `dangling`
  *error* on a forward reference gates a merge, and a delete refused because a paragraph
  quotes an id is a corpus nobody can maintain. Load-bearing details: the grammar lives in
  `platform.naming` beside the tag-key rule (adr-289e788719a7) because `DocId` mints what the
  scanner must recognise, and `DocId` now uses it — two copies would let a document be
  addressable by one and invisible to the other. The scan is restricted to the **schema's
  prefixes**, or `sha-1beef` in a sentence about hashing is an edge. `target` carries **no
  foreign key** and resolution is a read-time join, so an ADR naming the issue it will produce
  starts resolving when that issue is written rather than when the ADR is next saved; a
  self-mention is excluded in the entity, where the id is known. Derivation sits in
  `domain`+`application`, not in the repository: `platform.persistence` may not import
  `platform.naming` (tach), and deriving meaning from prose is not a translation of rows.
  `tags` writes documents without recomputing — a rename never touches a body — and
  `test_a_tag_rename_does_not_disturb_it` fails if that stops being true.
  **An unresolved mention is deliberately not a finding, and that was measured** (adr-e86c5040d626):
  all 47 in this corpus are documentation *examples* (`adr-0007`, `adr-3f9a2b1c7d4e` — the ids
  the architecture documents use to explain the id format), not typos. Ignoring code spans
  makes it worse: 20 of the 47 sit outside code anyway, and 56 **resolved** mentions live only
  inside code spans, so the filter would delete 12% of the working graph. Naming an id without
  linking to it is a correct thing for a document to do. It *is* reported by `lint --deep` as
  `unresolved-mention`, one finding per document — Tier 2 is where opt-in, never-gating noise
  belongs, and "is this a typo?" is a real if low-yield question.
  **`isolated:` is the exemption, and it is a reason rather than a flag.** Free text, empty
  meaning not exempt, following `owner:`; a document carrying one is skipped by `orphan` and by
  nothing else. `true` would record that somebody silenced the warning without recording what
  they concluded, which leaves the next reviewer re-deciding from scratch — the state the
  triage was written to end. Writing one is an ordinary edit and stamps `updated`, as
  `--set-owner` and `--verified` do — the mechanical-rewrite rule covers the writes nobody
  asked for, not this. `check --fix` must neither grant nor withdraw one, though: deciding a
  document is meant to stand alone is exactly the guess `--fix` refuses to make. It lives in frontmatter, not the index, so a teammate
  reviews it in a diff; an older docir reads a file carrying it and ignores it, but a *write*
  through that build drops the key.
  **`context` expansion follows them, last and both ways, and that was measured before it
  shipped.** `benchmarks/run.py` could not decide it — that corpus allocates ids at load time,
  so its bodies cannot name one and the mention graph is empty there, the same wrong-instrument
  trap as issue-b1a6e57deeec — so `benchmarks/mentions.py` exists, with a corpus whose bodies
  carry `{key}` placeholders substituted after allocation. Result: recall@5 **0.84 -> 0.93**,
  precision 0.33 -> 0.37, MRR unchanged at 0.86, one task of fifteen regressing. **MRR holds
  because of the budget, not because of expansion**: `seed_budget = limit - expand`, so at the
  shipped `expand=2` the top three ranked hits keep their positions — the same sweep shows MRR
  falling to 0.83 at `expand=3`, where only two do. The sweep also found `expand=1` and
  `expand=2` identical on that fixture (0.93/0.37 both), so the shipped default is not
  evidenced *against*, merely not distinguished; do not read 2 as measured-optimal. Authored edges are still ordered first: a `supersedes` is a
  claim about correctness, a citation is a claim about nothing. Two details of that benchmark
  are load-bearing: it mints **sequential** ids (random ones move ranking ties, and the same
  code scored 0.79 and 0.81 on consecutive runs), and it **derives** the prose-vs-authored task
  grouping from the corpus rather than reading a hand-written label — the first version's
  labels were wrong in the direction that flattered the feature, hiding that mentions also
  restore *backwards* reachability for non-successor edges like `refines`.

- **`context` has exactly one visibility predicate, and expansion runs both ways.**
  `DocumentService._is_visible` (archived + inactive status) is called by the ranked fusion loop
  *and* by `_augment_with_related`; do not inline the check into either. They used to differ —
  expansion tested only `archived` — so a `resolved` issue the caller had excluded came back
  through a neighbour edge, and the filter that held on `query`/`search`/ranked `context` leaked
  on the fourth path. Expansion follows outgoing edges **and** incoming *successor* edges,
  successors first in each seed's edge list: a `supersedes` edge points from
  the new document to the old one, so before this the replacement sat one hop away *backwards* and
  the graph could not answer "is this decision still current?" — the question it exists for.
  **`dependency` and `blocking` are two properties, not one (adr-716c2eeb4e51).** `layering`
  asks a structural question — does the source sit above the target — and `unblocked` asks a
  temporal one: does the source wait for it. `depends_on` carries both; `refines` carries only
  the first. Reading `dependency` for both was the shipped behaviour for three days and
  announced a decision refining a *superseded* one as "ready to start", a problem reported as
  good news, latent across 34 edges in this corpus.
  **Which kinds count is schema data, not a hardcoded name set (adr-234b956a48d8).** Traversal
  reads `Schema.successor_relation_kinds()` and layering reads `is_dependency_relation`, so a
  custom kind declared `successor: true` / `dependency: true` behaves like the core ones; the
  frozensets these replaced (`_SUCCESSOR_KINDS`, `graph_checks._DEPENDENCY_KINDS`) are gone, and
  reintroducing one silently strands every custom kind with that shape.
  `DocumentRepository.incoming` takes an optional `kinds` filter
  for this; unfiltered it is still the delete integrity check.
