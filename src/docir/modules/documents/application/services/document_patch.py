"""Staging one ``docir update`` against the document it edits.

Every field an update may touch is decided here, and the result is a ``changes``
mapping the caller applies in one :meth:`Document.with_updates` — so an edit is
validated whole before any of it is written, and a refusal halfway through
leaves the document exactly as it was.

Split out of :class:`DocumentService`, where these methods passed the same three
values — the request, the on-disk document, and the accumulating changes —
through nine signatures. They are the fields of this class instead, which is
what the clump was describing: delete any one of the three and the other two
mean nothing.

The **order** the fields are staged in is the part that is easy to get wrong and
is fixed in :meth:`stage`; each method's docstring says why it sits where it
does.
"""

from __future__ import annotations

from docir.modules.documents.application.dto import UpdateDocumentRequest
from docir.modules.documents.domain.entities.document import Document
from docir.modules.documents.domain.schema import Schema
from docir.modules.documents.domain.services.markdown_sections import (
    append_section,
    remove_section,
    replace_section,
)
from docir.modules.documents.domain.services.validation import Tier0Validator
from docir.modules.documents.domain.value_objects.relations import RelatedRef
from docir.platform.clock import Clock
from docir.platform.errors import InvalidStatusError, StaleWriteError, ValidationError
from docir.platform.filesystem.ports import CodeMatcher
from docir.platform.persistence.unit_of_work import UnitOfWork


def parse_related_refs(tokens: tuple[str, ...]) -> tuple[RelatedRef, ...]:
    """Parse ``<id>`` / ``<id>:<kind>`` CLI tokens into typed edges."""
    return tuple(RelatedRef.parse(token) for token in tokens if token.strip())


class DocumentPatch:
    """The staged result of applying one update request to a document.

    ``base`` is the document as it is **on disk**, not as the index remembers
    it — the files are the source of truth, so every edit composes with whatever
    is there.
    """

    def __init__(
        self,
        request: UpdateDocumentRequest,
        base: Document,
        *,
        schema: Schema,
        validator: Tier0Validator,
        clock: Clock,
        code_matcher: CodeMatcher | None,
    ) -> None:
        self._request = request
        self._base = base
        self._schema = schema
        self._validator = validator
        self._clock = clock
        self._code_matcher = code_matcher
        #: The staged edits, ready for ``base.with_updates(**changes)``. Empty
        #: means the request asked for nothing the document does not already say,
        #: which the caller returns as a no-op rather than a write.
        self.changes: dict[str, object] = {}
        #: Whether the edit moved the text a reader would have reviewed — the
        #: title, the description or the body. Drives both the embedding
        #: recompute and the automatic withdrawal of a verification.
        self.content_changed = False

    def stage(self, uow: UnitOfWork, *, disk_diverged: bool) -> None:
        """Decide every change this request makes, in the one order that is correct.

        The verification steps run **after** both the metadata and the body,
        because the body is half of what a verification covers: whether the
        content moved is not known until the section or body edit has been
        staged.
        """
        self.content_changed = self._apply_metadata(uow)
        self.content_changed |= self._apply_body(disk_diverged)
        if self.content_changed:
            self._revoke_verification()
        self._record_verified_content()

    def _apply_metadata(self, uow: UnitOfWork) -> bool:
        """Stage metadata changes; return whether embedding-relevant text moved.

        The type is resolved first, because it selects the grammar every other
        field is checked against — the status enum, the relation whitelist, the
        required fields. On a retype those are all checked against the *target*
        type, never the one the document is leaving, which is also what lets a
        retype run on a document whose current type the schema no longer
        declares (adr-f8cce745d0d5).
        """
        content_changed = False
        target_type = self._apply_type()
        if self._request.set_title is not None:
            self.changes["title"] = self._request.set_title
            content_changed = True
        if self._request.set_description is not None:
            self.changes["description"] = self._request.set_description
            content_changed = True
        self._apply_status(target_type)
        if self._request.set_tags is not None:
            self._validator.validate_tags(
                self._request.set_tags, [tag.key for tag in uow.tags.all()]
            )
            self.changes["tags"] = tuple(self._request.set_tags)
        self._apply_related(uow, target_type)
        if self._request.set_owner is not None:
            self.changes["owner"] = self._request.set_owner
        # Not an *embedding-relevant* change — no vector reads an exemption —
        # which is all `content_changed` tracks. It still stamps `updated`, like
        # every other flag `update` carries: the mechanical-rewrite rule governs
        # the writes nobody asked for (a tag rename, `check --fix`, a forced
        # delete's unlink), not an edit somebody typed.
        if self._request.set_isolated is not None:
            self.changes["isolated"] = self._request.set_isolated
        if self._request.set_code is not None:
            self._validator.validate_code(self._request.set_code)
            self.changes["code"] = tuple(self._request.set_code)
        self._apply_verification()
        self._apply_code_digests()
        return content_changed

    def _apply_verification(self) -> None:
        """Stage an explicit verification or an explicit withdrawal of one.

        The two are refused together rather than ordered: ``--verified
        --clear-verified`` is not a call with a winner, it is a caller that does
        not know which one it meant.

        Verifying clears ``revoked``. The clock reads ``verified`` first either
        way, so leaving it would change no behaviour — and would leave a date in
        the frontmatter asserting that this document's verification has been
        withdrawn, which is the opposite of what the file now says.

        Withdrawing needs a **standing** verification and is refused without
        one, so the flag cannot manufacture review state on a document nobody
        ever vouched for.

        It erases the stamp and **leaves no ``revoked`` date**, which is what
        separates it from the automatic revocation. The two answer different
        questions. An edit says "this was true and the content moved", so the
        cadence restarts from the edit. `--clear-verified` says "this was never
        true", and a claim nobody made buys nothing: the document falls back to
        ``created``, exactly where a never-verified one sits, and a bad stamp
        that had nearly run out reports overdue at once instead of being handed
        a fresh cadence by the act of withdrawing it (adr-f4e6ade4afd0).
        """
        if self._request.mark_verified and self._request.clear_verified:
            raise ValidationError(
                "--verified and --clear-verified say opposite things; pass one of them"
            )
        if self._request.mark_verified:
            self.changes["verified"] = self._clock.today()
            self.changes["revoked"] = None
        elif self._request.clear_verified:
            if self._base.verified is None:
                raise ValidationError(self._nothing_to_withdraw())
            self.changes["verified"] = None
            self.changes["revoked"] = None
            self.changes["verified_content"] = ""

    def _record_verified_content(self) -> None:
        """Record what the verified text looked like, for the check to compare against.

        Last, and outside :meth:`_apply_metadata`, because it digests the
        document the write is about to produce: a `--verified` passed with
        `--replace-section` covers the section as rewritten, and hashing ``base``
        would record the text the reviewer replaced.

        Only ``--verified`` writes it. The withdrawal paths clear it, and every
        other write leaves it exactly as it was — a status change must not be
        able to re-certify a document by refreshing the evidence.
        """
        if not self._request.mark_verified:
            return
        self.changes["verified_content"] = self._base.with_updates(
            **self.changes
        ).verification_digest()

    def _nothing_to_withdraw(self) -> str:
        """Why a ``--clear-verified`` was refused, in the caller's terms."""
        if self._base.revoked is not None:
            return (
                f"{self._base.id!r} carries no verification to withdraw: it was already "
                f"revoked on {self._base.revoked.isoformat()}"
            )
        return f"{self._base.id!r} carries no verification to withdraw"

    def _revoke_verification(self) -> None:
        """Withdraw a standing verification the edit has just invalidated.

        Fires when the write moved the **content** — title, description or body:
        exactly what somebody read when they vouched for the document, and
        exactly what ``content_changed`` already tracks for the embeddings. A
        status change, a retype, a tag or an edge does not: none of them changes
        a word of what was reviewed (adr-f4e6ade4afd0).

        Two calls are deliberately not revocations. ``--verified`` in the same
        command is the ordinary "rewrote it and re-read it" edit, and the
        explicit stamp wins over the inferred withdrawal. ``--clear-verified``
        has already withdrawn it.

        Only a *standing* verification is revoked. A document with none has
        nothing to withdraw, and stamping ``revoked`` on it anyway would hand
        every unverified document a fresh cadence on every edit — the review
        queue clearing itself the moment somebody writes in it, which is
        issue-6726eabcf871 arriving by a new door. So the clock can be moved
        forward at most once per verification, and moving it costs a
        verification first.
        """
        if (
            self._request.mark_verified
            or self._request.clear_verified
            or self._base.verified is None
        ):
            return
        self.changes["verified"] = None
        self.changes["revoked"] = self._clock.today()
        # The digest went with the verification. Keeping it would leave the file
        # asserting what the text looked like when somebody read it, under no
        # claim that anybody did — and `revoked` already records the move it
        # would be evidence of.
        self.changes["verified_content"] = ""

    def _apply_code_digests(self) -> None:
        """Stage the per-pattern evidence that goes with a verification.

        Runs after the code patterns are staged, and fingerprints the *resulting*
        set: `--set-code` and `--verified` in one call means the human read the
        document against the globs they just wrote, not the ones being replaced.

        Two rules, both instances of "absent means unknown":

        * With no matcher the digests are **dropped**, not carried over. A stale
          digest under a fresh ``verified`` date is the one combination that
          lies in the dangerous direction — it would report code as changed that
          the verification already covered, or hold evidence from a review two
          reviews ago.
        * Changing the globs without verifying **prunes** the digests of the
          patterns that went away and keeps the rest. Each surviving pattern was
          genuinely verified on the recorded date; a pattern just added was not,
          and gets no entry until someone verifies it.

        This is a mechanical field, so nothing here touches ``updated`` — the
        rule ``check --fix`` and the tag rewrites follow. It is deliberately not
        an embedding-relevant change either: no vector reads a digest.
        """
        patterns = (
            self._base.code if self._request.set_code is None else tuple(self._request.set_code)
        )
        if self._request.mark_verified:
            self.changes["verified_code"] = self._fingerprint_all(patterns)
        elif self._request.set_code is not None:
            kept = set(patterns)
            self.changes["verified_code"] = {
                pattern: digest
                for pattern, digest in self._base.verified_code.items()
                if pattern in kept
            }

    def _fingerprint_all(self, patterns: tuple[str, ...]) -> dict[str, str]:
        """Digest each pattern, dropping the ones that cannot be resolved."""
        if self._code_matcher is None:
            return {}
        digests = {}
        for pattern in patterns:
            digest = self._code_matcher.fingerprint(pattern)
            if digest is not None:
                digests[pattern] = digest
        return digests

    def _apply_type(self) -> str:
        """Stage a retype and return the type the rest of the write is checked against.

        The id is deliberately untouched. It is the corpus's only address —
        every ``related`` edge that points here spells it out, as does anything
        outside the store — so a document retyped from ``decision`` keeps its
        ``adr-`` prefix under a type whose prefix is something else. The prefix
        records which type *minted* the id, not which type owns it now.

        A retype is not marked as a content change: ``type`` is in
        ``content_hash`` (a write must not silently lose one) but not in
        ``embedding_text``, so the vectors are unaffected and re-embedding the
        corpus to rename it would be pure cost.
        """
        if self._request.set_type is None or self._request.set_type == self._base.type:
            return self._base.type
        # Unknown target: raises naming the types that exist. The *source* type
        # is never looked up, which is what keeps the retype available as the
        # exit from a type `disable_types` has just removed.
        self._schema.get(self._request.set_type)
        self.changes["type"] = self._request.set_type
        return self._request.set_type

    def _apply_status(self, target_type: str) -> None:
        """Stage the status, validated against ``target_type``.

        On a retype the check is *membership*, not transition: the type the
        document is leaving has its own transition graph, and that graph says
        nothing about a different type's. The current status is carried over
        when the new type declares it and the write is refused when it does
        not — never quietly reset to the new type's ``default_status``, which
        across a corpus rewrites every ``accepted`` to ``draft`` and reports
        success.
        """
        if target_type != self._base.type:
            status = self._base.status if self._request.status is None else self._request.status
            if self._request.status is None and not self._schema.get(target_type).is_valid_status(
                status
            ):
                valid = ", ".join(self._schema.get(target_type).statuses)
                raise InvalidStatusError(
                    f"cannot retype {self._base.id!r} to {target_type!r}: its status {status!r} "
                    f"is not one that type declares. Pass --status with one of: {valid}"
                )
            self._validator.validate_status(target_type, status)
            if status != self._base.status:
                self.changes["status"] = status
            return
        if self._request.status is not None and self._request.status != self._base.status:
            if self._request.allow_transition_override:
                self._validator.validate_status(self._base.type, self._request.status)
            else:
                self._validator.validate_transition(
                    self._base.type, self._base.status, self._request.status
                )
            self.changes["status"] = self._request.status

    def _apply_related(self, uow: UnitOfWork, target_type: str) -> None:
        """Stage the edges, and re-check the existing ones when the type moved.

        ``allowed_relations`` is a property of the *source* type, so a retype can
        carry a document under a whitelist its untouched edges do not satisfy.
        They are validated even though this call did not supply them, because
        this is the write that would persist them.
        """
        retyped = target_type != self._base.type
        if self._request.set_related is None and not (retyped and self._base.related):
            return
        id_to_type = {doc.id: doc.type for doc in uow.documents.all()}
        if self._request.set_related is None:
            self._validator.validate_relation_kinds(target_type, self._base.related, id_to_type)
            return
        refs = parse_related_refs(self._request.set_related)
        targets = [ref.target for ref in refs]
        self._validator.validate_related(targets, id_to_type, source_id=self._base.id)
        self._validator.validate_relation_kinds(target_type, refs, id_to_type)
        self.changes["related"] = refs

    def _apply_body(self, disk_diverged: bool) -> bool:
        """Stage a body edit (at most one mode); return whether the body moved.

        ``disk_diverged`` is consulted only by ``replace_body`` — see
        :meth:`DocumentService.update` for why that is the only mode it can
        apply to. The
        parameter is named for what it measures rather than "stale", which in
        this codebase means a document past its review cadence: a different
        concept on a different clock.
        """
        modes = [
            self._request.append_section,
            self._request.replace_section,
            self._request.remove_section,
            self._request.replace_body,
        ]
        if sum(mode is not None for mode in modes) > 1:
            raise ValidationError("only one body edit mode may be used per call")

        if self._request.append_section is not None:
            heading, body = self._request.append_section
            self.changes["body"] = append_section(self._base.body, heading, body)
            return True
        if self._request.replace_section is not None:
            heading, body = self._request.replace_section
            self.changes["body"] = replace_section(self._base.body, heading, body)
            return True
        if self._request.remove_section is not None:
            # A deletion composes with an out-of-band change like the other
            # section modes: it is resolved against the body as it is on disk,
            # so it never needs `disk_diverged`.
            self.changes["body"] = remove_section(self._base.body, self._request.remove_section)
            return True
        if self._request.replace_body is not None:
            if not self._request.force:
                raise ValidationError(
                    "--replace-body requires --force (it overwrites the whole body)"
                )
            if disk_diverged:
                raise StaleWriteError(
                    f"{self._base.id!r} changed on disk since it was indexed; "
                    f"refetch with `docir get {self._base.id}` before replacing the body"
                )
            self.changes["body"] = self._request.replace_body
            return True
        return False
