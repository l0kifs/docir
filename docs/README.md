# docir's own documentation

docir maintains its own docs **in docir**. The ADRs, the architecture documents, the
runbooks and the gap register all live in the project store at
[`.docir/docs/`](../.docir/docs/) and are read through the CLI:

```bash
docir query --type decision                 # every ADR, newest schema-valid metadata
docir get adr-d3e3616400bf                  # one document in full
docir context "why is the index shared across modules"   # ranked, body-less skeletons
docir query --type issue                    # the open gap backlog (resolved ones are hidden)
docir query --owner maintainer --stale      # the review queue
docir check --strict                        # the pre-merge integrity gate
```

The markdown files are still the source of truth and still diff in git — the SQLite
index beside them is derived and gitignored. Editing those files by hand is what the
CLI exists to prevent; use `docir update`.

## Ids are random, so this table is the stable map

The store mints collision-resistant random ids (`--id-style random`), which is what lets
two branches add documents without minting the same id — but it means `adr-0002` is no
longer an address. The **ADR number is preserved in each document's title**, so
`docir search "ADR-0002" --include-inactive` finds it, and this table maps the paths that
existed before the migration:

| was | id | now |
|---|---|---|
| `docs/adr/ADR-0001-adopt-modular-ddd-with-tach.md` | `adr-d87a60ee4ece` | [decisions/…adr-0001…](../.docir/docs/decisions/adr-d87a60ee4ece-adr-0001-adopt-modular-ddd-enforced-by-tach.md) |
| `docs/adr/ADR-0002-shared-derived-index.md` | `adr-d3e3616400bf` | [decisions/…adr-0002…](../.docir/docs/decisions/adr-d3e3616400bf-adr-0002-keep-the-shared-derived-index-and-single-unit-of-wo.md) |
| `docs/adr/ADR-0003-no-authorization-concern.md` | `adr-90e994d931cc` | [decisions/…adr-0003…](../.docir/docs/decisions/adr-90e994d931cc-adr-0003-authorization-and-cross-cutting-concerns-are-not-in.md) |
| `docs/adr/ADR-0004-central-test-tree.md` | `adr-909fc2a170d0` | [decisions/…adr-0004…](../.docir/docs/decisions/adr-909fc2a170d0-adr-0004-keep-a-central-test-tree-organized-per-module.md) |
| `docs/adr/ADR-0005-typed-relation-edges.md` | `adr-599055502f0e` | [decisions/…adr-0005…](../.docir/docs/decisions/adr-599055502f0e-adr-0005-typed-relation-edges-per-type-allowed-relations.md) |
| `docs/adr/ADR-0006-staleness-as-data.md` | `adr-bd7c4f3c5764` | [decisions/…adr-0006…](../.docir/docs/decisions/adr-bd7c4f3c5764-adr-0006-staleness-as-data-owner-verified-review-cadence.md) |
| `docs/adr/ADR-0007-core-plus-profiles.md` | `adr-2a3f625bb2f8` | [decisions/…adr-0007…](../.docir/docs/decisions/adr-2a3f625bb2f8-adr-0007-a-frozen-core-schema-swappable-domain-profiles.md) |
| `docs/adr/ADR-0008-agent-instruction-scaffolding.md` | `adr-3a2d5ee7bc84` | [decisions/…adr-0008…](../.docir/docs/decisions/adr-3a2d5ee7bc84-adr-0008-agent-instruction-scaffolding-as-a-self-contained-m.md) |
| `docs/adr/ADR-0009-per-project-store.md` | `adr-20eec6e2e2ca` | [decisions/…adr-0009…](../.docir/docs/decisions/adr-20eec6e2e2ca-adr-0009-per-project-store-discovery-docir-init.md) |
| `docs/adr/ADR-0010-qa-profile-and-schema-introspection.md` | `adr-c0ce6f347f3e` | [decisions/…adr-0010…](../.docir/docs/decisions/adr-c0ce6f347f3e-adr-0010-a-qa-profile-a-release-note-type-and-schema-introsp.md) |
| `docs/adr/ADR-0011-semantic-embeddings-by-default.md` | `adr-ab9c454b760c` | [decisions/…adr-0011…](../.docir/docs/decisions/adr-ab9c454b760c-adr-0011-semantic-embeddings-on-by-default.md) |
| `docs/architecture-rules.md` | `arch-322e5f992ad2` | [architectures/…architecture-rules…](../.docir/docs/architectures/arch-322e5f992ad2-architecture-rules-modular-ddd.md) |
| `docs/doc-index-architecture.md` | `arch-1cfb1b212237` | [architectures/…doc-index-cli…](../.docir/docs/architectures/arch-1cfb1b212237-doc-index-cli-architecture.md) |
| `docs/PUBLISHING.md` | `run-30aceb4eacc6` | [runbooks/…publishing-to-pypi…](../.docir/docs/runbooks/run-30aceb4eacc6-publishing-to-pypi.md) |
| `docs/ai-code-check-checklist.md` | `run-22e0a6ce6ae1` | [runbooks/…ai-code-check-checklist…](../.docir/docs/runbooks/run-22e0a6ce6ae1-ai-code-check-checklist.md) |

## The discovery bundle (`analysis/`) also moved in

All eight files are documents now, so the directory holds nothing unique. Verified
field-by-field: 751 values across the actor / rule / glossary registers and every one of
the 16 keys on all 50 gaps are present in the store, and the five flow documents plus the
frame and probe log are embedded verbatim.

| was | became | id |
|---|---|---|
| `analysis/02-flows/FLOW-001-authoring.md` | `architecture` | `arch-3e305bc76ff0` |
| `analysis/02-flows/FLOW-002-retrieval.md` | `architecture` | `arch-f220a644d654` |
| `analysis/02-flows/FLOW-003-integrity.md` | `architecture` | `arch-0a3c2d6d54a6` |
| `analysis/02-flows/FLOW-004-store-and-onboarding.md` | `architecture` | `arch-90c90751344f` |
| `analysis/02-flows/FLOW-005-tags.md` | `architecture` | `arch-ccfcceeb35eb` |
| `analysis/00-frame.md` | `reference` | `ref-9e4cce368b80` |
| `analysis/01-actors.yaml` | `reference` | `ref-301bcc84b75c` |
| `analysis/03-rules.yaml` | `reference` | `ref-32cb4f874fbe` |
| `analysis/04-glossary.yaml` | `reference` | `ref-cbf147832c37` |
| `analysis/99-log.md` | `reference` | `ref-1509d5dbb4c3` |
| `analysis/05-gaps.yaml` | 50 `issue` documents | title carries `GAP-0NN` |
| `analysis/06-questions.yaml` | 17 `issue` documents | title carries `Q-0NN` |

`reference` is an inline type added to `docs-schema.yaml` for descriptive registers — the
glossary, the actor catalog, the rule register, the frame and the probe log. They record
what *is*, so they are `active` until superseded rather than proposed/accepted. Its `level`
is 5, matching `architecture`: reference material is what everything else is written
against, and the Tier 1 layering check warns when a document `depends_on`/`refines`
something of a *lower* level.

Prose citations became typed edges. Each gap issue links to the flow it belongs to and, for
the 16 that were proved by an executed probe, to `ref-1509d5dbb4c3`. Each question links to
the gap it came from. That took `docir check`'s orphan count from 25 to 0.

Two documents still contain `analysis/...` paths — the frame and the probe log describe
where the discovery run wrote its output in 2026-07. Rewriting that would falsify a
historical record, so each carries a trailing "Note on paths" section instead.

GAP-051, found by the migration itself, was filed and resolved through `docir add` /
`docir update` — the store is the live register now.

## What deliberately stayed outside the store

| file | why |
|---|---|
| `README.md` | the PyPI long description — `pyproject.toml` names the path |
| `CHANGELOG.md` | root convention; a release log is append-only history, not a reviewed document |
| `CLAUDE.md` | the agent contract Claude Code loads by path |
| `LICENSE` | tooling reads it from the root |
| `docs/AGENT_GUIDE.md` | a pointer to the packaged template, whose job is to be a stable path |

## Schema

The store runs the `software` + `ops` profiles — `decision`, `issue`, `architecture`,
`release_note`, `runbook`, `incident`, `postmortem` — plus the frozen core. Inspect the
merged result with `docir schema show`.
