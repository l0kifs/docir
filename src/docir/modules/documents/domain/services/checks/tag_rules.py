"""The two findings that measure the corpus against the **tag registry**.

Apart from the schema checks on purpose: the registry is ``docs/tags.yaml``, a
different file that no schema change moves. Neither is reachable through the
CLI — Tier 0 refuses an unregistered tag on write and ``tag add`` refuses a
malformed key — so either one firing means a hand-edit or a merge.
"""

from __future__ import annotations

from docir.modules.documents.domain.entities.document import Document
from docir.modules.documents.domain.schema import Schema
from docir.modules.documents.domain.services.checks.findings import CheckIssue
from docir.platform.naming import TAG_KEY_RULE, is_valid_tag_key


class TagRegistryChecks:
    """The findings about the tag vocabulary itself."""

    def __init__(self, schema: Schema) -> None:
        self._schema = schema

    def run(self, documents: list[Document], known_tags: frozenset[str]) -> list[CheckIssue]:
        """Every tag-registry finding, in the order ``check`` reports them."""
        issues: list[CheckIssue] = []
        issues.extend(self._find_unknown_tag(documents, known_tags))
        issues.extend(self._find_tag_key_format(known_tags))
        return issues

    def _find_unknown_tag(
        self, documents: list[Document], known_tags: frozenset[str]
    ) -> list[CheckIssue]:
        """Flag tags that are not in the registry.

        Also unreachable through the CLI (Tier 0 rejects an unregistered tag on
        write), so it means a hand-edit or a merge. The tag still filters
        `query --tag`, but `tag list` does not know it and `tag rename` / `tag
        rm` cannot touch it — the registry has stopped describing the
        vocabulary actually in use.
        """
        issues: list[CheckIssue] = []
        for doc in documents:
            unknown = sorted(set(doc.tags) - known_tags)
            if not unknown:
                continue
            issues.append(
                CheckIssue(
                    kind="unknown-tag",
                    message=(
                        f"{doc.id!r} uses unregistered tag(s) "
                        f"{', '.join(repr(t) for t in unknown)}; "
                        "register them with `docir tag add` or remove them"
                    ),
                    doc_ids=(doc.id,),
                )
            )
        return issues

    def _find_tag_key_format(self, known_tags: frozenset[str]) -> list[CheckIssue]:
        """Flag registered keys the vocabulary grammar does not allow.

        A finding about the *registry*, not about any document, so ``doc_ids``
        is empty — the offending key is named in the message instead.

        A warning, and it has to stay one. `tag add` rejects a bad key now, so
        the only way to hold one is to predate the rule, and an existing corpus
        must not start failing a `--strict` build for something its author
        could not have avoided. Nothing repairs it either: the fix is a rename,
        and deciding whether `Auth` meant `auth` or `authn` is a reading of the
        corpus, not a transformation of it.
        """
        offenders = sorted(key for key in known_tags if not is_valid_tag_key(key))
        return [
            CheckIssue(
                kind="tag-key-format",
                message=(
                    f"registered tag {key!r} is not {TAG_KEY_RULE}; "
                    f"rename it with `docir tag rename {key} <new-key>` "
                    "(`--merge` if the target already exists)"
                ),
                doc_ids=(),
            )
            for key in offenders
        ]
