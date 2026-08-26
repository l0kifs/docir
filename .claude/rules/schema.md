---
paths:
  - "src/docir/modules/documents/domain/schema.py"
  - "src/docir/modules/documents/domain/services/schema_shape.py"
  - "src/docir/modules/documents/infra/schema_loader.py"
  - "src/docir/modules/documents/infra/profiles.py"
  - "src/docir/modules/documents/infra/default_schema.py"
  - "**/docs-schema.yaml"
---

# The schema — core, profiles, and what the loader refuses

The schema resolves as core -> profiles -> inline on every command, so it can change without anyone editing a file. Every loader check below reports at load time and names what would have worked; the alternative is a failure much later that blames the write.

- **The schema is core + profiles (adr-2a3f625bb2f8).** `infra/profiles.py` holds a frozen domain-agnostic
  core (the `decision` type + relation registry + cadences) and bundled profiles (software/research/
  ops/legal). A `docs-schema.yaml` with a `profiles:` key merges `core -> profiles -> inline`; a file
  with no `profiles:` key parses inline-only (fully backward compatible). The default is
  `profiles: [software]`, which resolves to exactly `decision`/`issue`/`architecture`. The core is
  always merged when a `profiles:` key is present (you can't disable it that way); disabling a
  profile after its docs exist leaves them with a type the schema no longer knows — `docir check`
  flags those as `unknown-type`, beside the `schema-drift` finding naming the cause (schema
  resolution does not re-key or migrate existing files — there is no document migration and
  deliberately so: every change class needs somebody to decide, which is what `check --fix`
  already refuses to guess at).

- **Merging only adds, so `disable_types:` is how a schema subtracts (adr-f8cce745d0d5).**
  It is applied *after* core+profiles+inline resolve, and the reason it exists is not the
  name but the **prefix**: `Schema.__post_init__` refuses two types sharing one, so while
  the core declares `decision`/`adr` no other type can claim `adr` — which is exactly what a
  corpus renaming its types while keeping its `adr-...` ids needs (issue-ab138501abfd). The
  unused name staying addable was the second half: two names for one concept, shipped in the
  default schema. Two loader rules hold it up, both the "reported at load, naming what would
  have worked" shape the `required:`/status checks already use: the name must be in the
  resolved set (a typo that silently does nothing forever is the failure mode), and it may
  not be one the same file also declares inline (a contradiction with no reading worth
  guessing). It deliberately does **not** consult the corpus — schema resolution knows
  nothing about documents, and stranding documents on a disabled type is a supported move
  reported as `unknown-type` + `schema-drift`, exactly as disabling a profile already was.

- **The schema loader also rejects a `required:` name no document can carry** — the allowed set is
  `REQUIRABLE_FIELDS`, derived from the `Document` dataclass (minus `path`, which the file store
  assigns *after* Tier 0 runs, so requiring it would reject every create). `required` is checked
  with `getattr` on the entity, so an unsatisfiable name used to load fine and then fail every
  write of that type forever, naming the write rather than the schema (issue-e3c4dfad4f7b). The
  paired rule: "empty" in that check covers an empty **collection**, not only a blank string —
  otherwise `required: [tags]` loads, reads as enforced and enforces nothing. `False` stays a
  value, not an absence.

- **The schema loader rejects a status name no type declares** — a transition target, an
  `inactive_statuses` entry, or `default_status`. Without it a typo loaded fine and failed much
  later as `invalid transition 'open' -> 'closed'`, naming a status that *is* declared and
  pointing at the write rather than the schema. A **dead-end check** ("a live status with no
  outgoing transitions") was built and dropped: it fires on 5 of the 15 shipped types
  (`release_note.published`, `postmortem.published`, `experiment.complete`,
  `hypothesis.supported`, `obligation.breached`), all correct terminal states for documents
  that stay live. "Terminal" and "closed" are different properties, and nothing in the schema
  distinguishes an intended dead end from a missing transition — do not rebuild it.

- **Relation edges are typed (adr-599055502f0e).** `related` entries carry a `kind` (`RelatedRef{target,
  kind}`); the on-disk form is a bare id for the default `relates_to` (so pre-typed files round-trip
  unchanged) or a `{to, kind}` mapping. `relations.kind` is a **non-key** column — one kind per
  ordered `(source, target)` pair — added by migration `0002`. The `relation_types` registry is
  **permissive when empty** (schemas predating typed edges accept any kind). Per-type
  `allowed_relations` is a whitelist enforced at Tier 0.

- **`docir schema validate` reports what the schema costs the corpus, and never gates on it
  (issue-3678c897295f).** The command run immediately after a schema edit used to answer only
  "does this file parse?", so it said `valid: true` while a corpus left the type system.
  Four properties are load-bearing. It runs **`GraphChecker.check_schema_conformance`**, which
  `check` also calls — the four findings a *schema* edit can cause; a second list of check
  names is the `is_absent` failure again, one command calling a document conforming that the
  other refuses. It reads the **files, not the index**: a schema edit is a hand edit, which is
  when the index is behind, and a fresh clone has none at all. It opens **no database**, which
  is what preserves `schema validate`'s existing property of being reachable for a store too
  broken to start — do not "simplify" it through `build_container`. And the **exit code does
  not move**, for the reason README gives: gating here would
  red-build every repo mid-migration — the state a correct migration passes through. The graph
  findings are deliberately excluded: `orphan` fires for every unlinked document, which would
  bury the answer under the default state of a healthy corpus. `affected` counts distinct
  documents, not findings — summing per-kind counts printed "14 of 8 document(s)".
