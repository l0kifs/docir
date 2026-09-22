"""A `file.py:line` in docir's own prose points where it says it points.

Reading the corpus against its code turned up five documents whose citation
columns had shifted *wholesale*: an architecture note on the **write** path
pointing `IndexProjected` into `_ranking_trace`, a read-path helper; a tag note
pointing `TagRenamed` at the `TagService` class header while `rename` sat eighty
lines below. Nothing caught any of it, because a stale line number is a
well-formed string and a checker with only the number cannot tell.

Two rules, and the split is the point (`scripts/code_citations.py` argues it).
Every citation must resolve to a real file at an existing line — checkable
today, and twelve of this store's failed it. And every *new* citation must name
the symbol it points at, so the pair can disagree and the disagreement is caught
in the commit that causes it.

The 250 citations that predate the rule are grandfathered per document, by
count. A count rather than a list because the list is 250 entries and the
property is the same: a grandfathered document may not grow a new unpaired
citation, and fixing one must shrink its number. Editing such a citation changes
its line, which is exactly when the paired form should be adopted.
"""

from __future__ import annotations

import pathlib
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2] / "scripts"))

from code_citations import citations, problems

_REPO = pathlib.Path(__file__).resolve().parents[2]
_STORE = _REPO / ".docir" / "docs"

#: Documents carrying citations written before the paired form, and how many
#: each still has. **This table may only shrink.** Pair one and lower the
#: number; pair the last and delete the row.
GRANDFATHERED: dict[str, int] = {
    "arch-0a3c2d6d54a6-keep-the-corpus-trustworthy-maintenance-ci-staleness.md": 9,
    "issue-0783d236d565-override-bypasses-the-transition-rules-and-leaves-no-trace.md": 1,
    "issue-0a4ad65b8a70-should-the-corrupt-state-findings-have-a-repair-path-or-only.md": 3,
    "issue-0e3d1d9c81d3-docir-check-has-no-finding-for-an-edge-whose-relation-kind-t.md": 7,
    "issue-1ec2fd4a6798-should-tag-rename-advance-updated-on-every-referencing-docum.md": 2,
    "issue-20933967697b-no-import-path-a-repository-with-existing-adrs-must-re-creat.md": 1,
    "issue-2b28fd8b1dfa-should-schema-validate-check-that-transition-targets-name-de.md": 2,
    "issue-330738a57cb6-owner-is-captured-and-only-ever-interpolated-into-a-check-me.md": 2,
    "issue-34b4f0ca1e13-an-uninitialised-repository-silently-falls-back-to-the-globa.md": 4,
    "issue-3678c897295f-no-way-to-see-what-a-docs-schema-yaml-edit-will-change-befor.md": 1,
    "issue-389dc5dac58a-with-no-daemon-concurrent-add-invocations-all-receive-the-sa.md": 3,
    "issue-40d1792bc9f9-linking-a-decision-to-its-issue-is-a-permanent-layering-warn.md": 1,
    "issue-476b4e188fab-four-of-the-eight-finding-kinds-are-detected-with-no-way-to.md": 2,
    "issue-498cbbaeac2f-no-usage-counts-so-dead-tags-are-invisible.md": 2,
    "issue-5bfbc6f2699d-expansion-is-outgoing-only-so-the-document-that-supersedes-a.md": 3,
    "issue-5f979576ef7d-reindex-silently-skips-unparseable-files-and-reports-the-reb.md": 3,
    "issue-61b66ed696de-the-markdown-file-is-written-before-the-transaction-commits.md": 3,
    "issue-6817ed1851e2-agents-never-edit-markdown-directly-is-stated-for-agents-and.md": 1,
    "issue-7a271eb0f21a-a-random-id-is-3x-the-length-of-a-sequential-one-and-the-cos.md": 2,
    "issue-7d4fdccf8343-the-no-op-early-return-skips-staleness-so-a-no-op-update-rep.md": 3,
    "issue-7f2f73d6941c-a-test-asserts-a-phrase-against-rich-wrapped-stderr-so-it-pa.md": 2,
    "issue-87a27629f6a6-the-agent-guide-told-agents-to-run-docir-reindex-all-a-flag.md": 1,
    "issue-88dd653b9f39-should-reindex-restore-the-id-counter-or-is-the-index-not-fu.md": 2,
    "issue-8bcb6b7f8308-should-limit-bound-the-whole-context-response-or-only-the-ra.md": 1,
    "issue-8c37bf22ba3c-the-inactive-status-filter-is-enforced-on-three-read-paths-a.md": 2,
    "issue-8d5b5b45e2fc-an-edge-s-target-key-is-to-in-frontmatter-and-target-in-json.md": 1,
    "issue-8f6576cd7bc9-a-newly-required-field-is-invisible-to-docir-check-and-surfa.md": 7,
    "issue-90aea6d1b891-nothing-in-a-document-names-the-code-it-governs-so-a-decisio.md": 10,
    "issue-9152d83d9f78-should-graph-expansion-honour-the-inactive-status-filter.md": 1,
    "issue-93152f7b9213-no-relevance-floor-and-score-carries-no-absolute-meaning-so.md": 1,
    "issue-93dd537bbbbb-should-docir-context-be-able-to-return-nothing.md": 2,
    "issue-996b567e5131-limit-bounds-the-ranked-seed-set-but-not-the-response.md": 2,
    "issue-99afeec3a7ce-should-override-leave-a-trace-of-a-forced-illegal-transition.md": 1,
    "issue-9cb85759076d-check-strict-exits-1-on-any-finding-so-the-advertised-ci-gat.md": 1,
    "issue-9ed4905e0db8-tag-rename-sets-updated-today-on-every-referencing-document.md": 4,
    "issue-a40dbcc7a19a-home-store-and-data-root-name-one-concept-in-three-places.md": 2,
    "issue-a776b08ceaea-tags-are-in-neither-the-fts-index-nor-the-embedded-text-so-s.md": 3,
    "issue-b47a1203baa2-schema-validate-does-not-check-that-transition-targets-are-d.md": 4,
    "issue-b4f441c7210f-staleness-is-detected-and-never-routed-owner-reaches-one-che.md": 2,
    "issue-b7ddde3ce860-reindex-does-not-restore-the-id-counter-so-a-fresh-clone-re.md": 2,
    "issue-b8220546282c-an-unrecognised-agent-target-name-is-silently-ignored-no-err.md": 2,
    "issue-b86a75d656ea-should-docir-add-in-an-uninitialised-repository-succeed-agai.md": 2,
    "issue-bdb7330441e6-should-agent-install-agent-unknown-fail-instead-of-being-a-s.md": 1,
    "issue-be95d3e242a3-only-replace-body-has-a-stale-write-guard-the-other-four-edi.md": 2,
    "issue-c33edcf431fa-reindex-changed-skips-the-removal-sweep-so-deleted-documents.md": 2,
    "issue-cc61d038cf8f-renaming-a-tag-onto-an-existing-key-is-rejected-so-two-tags.md": 2,
    "issue-d69a47904478-tag-rm-reports-only-removed-key-never-how-many-documents-it.md": 2,
    "issue-d7767bef9399-nothing-recorded-which-model-produced-a-vector-so-changing-e.md": 2,
    "issue-d79dbf1075fa-the-client-s-connect-timeout-also-bounded-the-daemon-s-reply.md": 3,
    "issue-d8295c5c76d1-stale-names-three-unrelated-concepts-in-one-codebase.md": 3,
    "issue-d891ab5501e6-a-store-cannot-tell-that-its-schema-changed-under-it-on-upgr.md": 4,
    "issue-e19a2fde1805-search-fetches-limit-2-candidates-then-filters-so-it-under-r.md": 2,
    "issue-e3c4dfad4f7b-a-type-may-declare-a-required-field-no-document-can-carry-an.md": 8,
    "issue-e52de79d85ee-should-graph-expansion-follow-incoming-edges-too.md": 2,
    "issue-e71e1ad9b0ef-no-format-rule-for-tag-keys-any-non-empty-string-is-accepted.md": 2,
    "issue-ed49c1d03894-documented-as-leaving-unknown-type-documents-the-recovery-pa.md": 1,
    "issue-efc29234eb57-the-flag-is-include-resolved-but-the-concept-is-inactive-sta.md": 4,
    "issue-f01a7a585fc1-the-default-embedder-does-not-capture-meaning-it-is-the-sign.md": 1,
    "issue-f09fab3f5c36-restore-id-sequences-reads-an-all-digit-random-hex-suffix-as.md": 2,
    "issue-f2591bdbca13-should-linking-a-decision-to-its-motivating-issue-be-a-layer.md": 1,
    "issue-f6a5d0b86806-no-stated-corpus-ceiling-context-loads-every-active-embeddin.md": 6,
    "issue-fd547a293d01-delete-force-leaves-referencing-documents-pointing-at-a-docu.md": 2,
    "issue-fde9a7151bd1-init-force-overwrites-a-customised-docs-schema-yaml-along-wi.md": 3,
    "ref-1509d5dbb4c3-discovery-probe-log-probe-1-n-and-the-delta-pass.md": 2,
    "ref-301bcc84b75c-actor-catalog-who-and-what-drives-docir.md": 11,
    "ref-32cb4f874fbe-business-rule-register-47-rules-br-001-br-074.md": 55,
    "ref-9e4cce368b80-discovery-frame-docir-at-v0-2-1-run-2026-07-26.md": 1,
    "ref-cbf147832c37-glossary-one-term-one-definition-one-owner.md": 16,
}


def _documents() -> dict[str, str]:
    assert _STORE.is_dir(), (
        f"{_STORE} is missing — the suite runs from the checkout, so an absent "
        "store means this guard is scanning nothing rather than finding nothing"
    )
    found = {p.name: p.read_text(encoding="utf-8") for p in sorted(_STORE.rglob("*.md"))}
    assert found, f"{_STORE} holds no documents — see above"
    return found


DOCUMENTS = _documents()


@pytest.mark.parametrize("name", sorted(DOCUMENTS))
def test_every_citation_resolves_to_a_real_line(name: str) -> None:
    """The half a checker can judge without knowing what the author meant."""
    issues = problems(_REPO, DOCUMENTS[name], require_pair=False)
    assert not issues, f"{name}:\n  " + "\n  ".join(issues)


@pytest.mark.parametrize("name", sorted(DOCUMENTS))
def test_a_new_citation_names_what_it_points_at(name: str) -> None:
    """Unpaired citations may not outnumber what the document was grandfathered.

    Equality, not a ceiling: a document that drops below its number has had one
    fixed, and the table has to record that or the ratchet never tightens.
    """
    unpaired = sum(1 for _, _, named in citations(DOCUMENTS[name]) if named is None)
    allowed = GRANDFATHERED.get(name, 0)
    assert unpaired <= allowed, (
        f"{name} has {unpaired} unpaired `file.py:line` citation(s), "
        f"{allowed} grandfathered. A new one must name its symbol: "
        "``document_service.py:250`` (`DocumentService.update`)"
    )
    assert unpaired == allowed, (
        f"{name} is down to {unpaired} unpaired citation(s) from {allowed} — "
        f"set GRANDFATHERED[{name!r}] = {unpaired}"
        + (", or delete the row" if unpaired == 0 else "")
    )


def test_the_grandfathered_table_names_documents_that_exist() -> None:
    """A row for a deleted or renamed document is a rule that stopped applying."""
    gone = sorted(set(GRANDFATHERED) - set(DOCUMENTS))
    assert not gone, "these documents are gone — delete their rows:\n  " + "\n  ".join(gone)


def test_the_guard_sees_a_wrong_symbol() -> None:
    """Guard the guard: a checker that judges nothing passes everything."""
    text = "See `src/docir/platform/naming/slug.py:1` (`NoSuchSymbol`) for the rule."
    assert problems(_REPO, text, require_pair=True), "a wrong pairing must be reported"


def test_the_guard_accepts_a_correct_pair() -> None:
    from code_citations import symbol_at

    path = _REPO / "src/docir/modules/documents/application/dto.py"
    line = 170
    actual = symbol_at(path, line)
    text = f"See `src/docir/modules/documents/application/dto.py:{line}` (`{actual}`)."
    assert not problems(_REPO, text, require_pair=True), f"line {line} is in {actual}"
