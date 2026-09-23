"""The findings driven by the review clock and the code tree.

What these four share is that **absent means unknown**, never *fine*: no date
supplied means staleness is not asked, no matcher means the ``code`` globs
cannot be resolved and are skipped rather than reported as missing, and a
pattern nobody has verified has no recorded value to differ from. Each guard
sits on the argument its own docstring makes.
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import date

from docir.modules.documents.domain.entities.document import Document
from docir.modules.documents.domain.schema import Schema
from docir.modules.documents.domain.services.checks.findings import CheckIssue


class VerificationChecks:
    """Staleness, code-glob reality, and verification evidence."""

    def __init__(self, schema: Schema) -> None:
        self._schema = schema

    def run(
        self,
        documents: list[Document],
        today: date | None,
        code_matches: Mapping[str, bool] | None,
        code_digests: Mapping[str, str] | None,
    ) -> list[CheckIssue]:
        """Every verification finding, in the order ``check`` reports them.

        Every one but the last is skipped when its input is ``None`` — the
        permissive-when-absent convention this whole group follows. A global
        store has no tree to resolve a repo-relative pattern against, so all
        four code findings go silent together rather than one of them guessing.
        """
        issues: list[CheckIssue] = []
        if today is not None:
            issues.extend(self._find_stale(documents, today))
        if code_matches is not None:
            issues.extend(self._find_unmatched_code(documents, code_matches))
            issues.extend(self._find_unwatched_code(documents, code_matches))
        if code_digests is not None:
            issues.extend(self._find_changed_code(documents, code_digests))
            issues.extend(self._find_drifted_code(documents, code_digests))
        issues.extend(self._find_outdated_verification(documents))
        return issues

    def _find_stale(self, documents: list[Document], today: date) -> list[CheckIssue]:
        """Flag documents past their type's review cadence (staleness as data).

        Staleness is honest re-verification, not a heuristic: a type opts
        in with a ``review_days`` cadence, and a document resets the clock by
        being ``--verified``. Types with no cadence are never flagged.

        The clock runs from :meth:`Document.stale_reference_date` — ``verified``,
        else ``revoked``, else ``created``, never ``updated``. Which of the three
        it read is in the message: without it the reader sees a document they
        edited yesterday reported as overdue and reads the finding as a bug
        rather than as the answer to "who has confirmed this is still true".
        """
        issues: list[CheckIssue] = []
        for doc in documents:
            if doc.archived or doc.type not in self._schema.types:
                continue
            cadence = self._schema.types[doc.type].review_days
            if cadence <= 0:
                continue
            overdue_by = (today - doc.stale_reference_date()).days - cadence
            if overdue_by > 0:
                owner = f" (owner: {doc.owner})" if doc.owner else ""
                since = _clock_read(doc)
                issues.append(
                    CheckIssue(
                        kind="stale",
                        message=(
                            f"{doc.id!r} is {overdue_by} day(s) past its "
                            f"{cadence}-day review cadence ({since}) — confirm it "
                            f"with `docir update {doc.id} --verified`{owner}"
                        ),
                        doc_ids=(doc.id,),
                    )
                )
        return issues

    def _find_unmatched_code(
        self, documents: list[Document], code_matches: Mapping[str, bool]
    ) -> list[CheckIssue]:
        """Flag ``code`` globs that no longer name anything in the repository.

        The Tier 1 half of the code linkage: the write path deliberately accepts
        a pattern that matches nothing, because a decision is often written
        before the code it decides — so the question "does it match *now*" has
        to be asked later, by the command that reports shape and age, and as a
        warning. It is not damage: the document is intact, the graph resolves,
        and the honest reading is "the code moved, or was never written, and
        somebody should look".

        Nothing repairs it either, which is why it stays out of ``check --fix``:
        the fix is a decision — repoint the pattern, or rewrite the document the
        moved code has outdated — and a repair has nothing to read *with*.
        Whoever drives the CLI makes that call, which is why the finding names
        the pattern rather than just the document.

        ``code_matches`` is the resolved answer per pattern, computed against
        the working tree by the caller — the domain stays pure and testable
        without a repository. A pattern *absent* from the map is unresolved
        rather than missing, and is not reported: the same rule ``similarity``
        follows on the read paths, where absent means "not scored" and never
        "scored zero". A finding invented for a question nobody answered is the
        failure mode this whole check has to avoid.
        """
        issues: list[CheckIssue] = []
        for doc in documents:
            if doc.archived:
                continue
            missing = [pattern for pattern in doc.code if not code_matches.get(pattern, True)]
            if not missing:
                continue
            joined = ", ".join(repr(pattern) for pattern in missing)
            issues.append(
                CheckIssue(
                    kind="unmatched-code",
                    message=(
                        f"{doc.id!r} governs {joined}, which matches nothing in the "
                        f"repository; update the pattern with `docir update {doc.id} "
                        f"--set-code ...` or re-verify the document"
                    ),
                    doc_ids=(doc.id,),
                )
            )
        return issues

    def _find_unwatched_code(
        self, documents: list[Document], code_matches: Mapping[str, bool]
    ) -> list[CheckIssue]:
        """Flag a glob that resolves and that no digest is watching.

        The blind spot the other three cannot report. `code-changed` and
        `code-drifted` both compare a recorded digest against the tree, and both
        treat *no recorded digest* as unknown and say nothing — which is right,
        because a comparison against nothing is not a change. `unmatched-code`
        covers the other half, a glob that names nothing. Between them sits a
        glob that names something real and carries neither digest: it is in no
        finding's scope, and no edit to the code it governs will ever be
        reported (GitHub #25).

        It is reachable two ways and both are ordinary. A glob declared while
        its path was absent — a decision written before the code, which the
        write path deliberately accepts — mints nothing, because there is
        nothing to hash; the file then arrives and `unmatched-code` stops
        firing, taking the last signal with it. And a glob declared by a build
        that minted no baseline at all keeps watching nothing until somebody
        verifies the document. Neither re-arms on its own: `mint_baseline` fills
        a missing entry, but only on a *write*, and `check` never writes.

        Reported only for patterns `code_matches` says resolve **now**. A glob
        naming nothing is `unmatched-code`'s to report, with the sharper
        sentence to say about it, and naming one problem twice is the noise that
        teaches a reader to skim. Absent from the map is unknown and silent, as
        everywhere else here — the default is `False` rather than
        :meth:`_find_unmatched_code`'s `True` because the two want silence from
        opposite answers.

        Unlike its siblings this one **is** repairable without a judgement, and
        `check --fix` already carries the repair: a baseline says *this is what
        the tree held when we started watching*, never *somebody read this*, so
        minting one crosses none of the lines `verified_code` is fenced by. What
        it cannot recover is the drift that already happened — watching starts
        at the next change, which is why the finding names `--fix` rather than
        being applied silently.
        """
        issues: list[CheckIssue] = []
        for doc in documents:
            if doc.archived or not doc.code:
                continue
            unwatched = [
                pattern
                for pattern in doc.code
                if code_matches.get(pattern, False)
                and pattern not in doc.verified_code
                and pattern not in doc.code_baseline
            ]
            if not unwatched:
                continue
            joined = ", ".join(repr(pattern) for pattern in unwatched)
            issues.append(
                CheckIssue(
                    kind="code-unwatched",
                    message=(
                        f"{doc.id!r} governs {joined}, which exists but has no recorded "
                        f"digest, so no change to it will ever be reported; start "
                        f"watching it with `docir check --fix`"
                    ),
                    doc_ids=(doc.id,),
                )
            )
        return issues

    def _find_changed_code(
        self, documents: list[Document], code_digests: Mapping[str, str]
    ) -> list[CheckIssue]:
        """Flag documents whose governed code has moved since they were verified.

        The evidence half of staleness. ``stale`` measures a calendar — a review
        cadence elapsed — and so fires on documents nothing has happened to
        while staying silent on the one that was rewritten underneath yesterday.
        This asks the other question, and it is the sharper one: the code this
        document describes is not the code somebody read.

        A warning, and it must stay one. It fires from a *comparison against the
        working tree*, so a branch that legitimately edits the code before
        updating the docs — the ordinary shape of a change — would fail its own
        CI, which is how a gate teaches people to stop reading `docir check`.

        Clearing it is a **judgement, not a rewrite**: somebody has to read the
        document against the code as it now stands and decide it is still true.
        That is why `check --fix` cannot touch it — a repair has nothing to read
        *with* — and it is the whole of the rule. Not "a human did it": docir's
        writer is an agent by design (thesis 2), so a signal only a human could
        emit is a signal nothing would ever emit. What the rule excludes is the
        writer that clears the finding *inside the task that moved the code*,
        certifying its own change; that degrades `verified` from "somebody read
        this" to "CI is green", which is the laundering adr-bd7c4f3c5764 guards
        against, arriving by a different door.

        The digests **outlive the verification they were taken with**. A
        withdrawn verification (``revoked``) leaves them in place, so this keeps
        answering the question it exists for — the code is not what somebody
        read — on exactly the documents whose calendar has just been reset. The
        combination the rule forbids is the opposite one: a digest from an older
        review carried under a *fresh* ``verified`` date, which claims a review
        covered code it never saw. Nothing here claims a verification stands.

        Three absences are all read as *unknown*, never as unchanged. A pattern
        missing from ``code_digests`` did not resolve (it matches nothing — the
        `unmatched-code` finding covers that, and reporting both would name one
        problem twice). A pattern with no recorded digest was never verified.
        And a document with no digests at all has never been verified with a
        matcher present. Silence about an absence is not silence about the
        *document*: a glob carrying neither digest while it resolves is
        :meth:`_find_unwatched_code`'s, which is what stops the third of those
        from being a permanent blind spot.
        """
        issues: list[CheckIssue] = []
        for doc in documents:
            if doc.archived or not doc.verified_code:
                continue
            moved = [
                pattern
                for pattern in doc.code
                if (current := code_digests.get(pattern)) is not None
                and (recorded := doc.verified_code.get(pattern)) is not None
                and current != recorded
            ]
            if not moved:
                continue
            joined = ", ".join(repr(pattern) for pattern in moved)
            if doc.verified is not None:
                verified_on = f" on {doc.verified.isoformat()}"
            elif doc.revoked is not None:
                verified_on = f" (a verification withdrawn on {doc.revoked.isoformat()})"
            else:
                verified_on = ""
            issues.append(
                CheckIssue(
                    kind="code-changed",
                    message=(
                        f"{doc.id!r} governs {joined}, which changed since it was "
                        f"verified{verified_on}; re-read it and run `docir update "
                        f"{doc.id} --verified`"
                    ),
                    doc_ids=(doc.id,),
                )
            )
        return issues

    def _find_drifted_code(
        self, documents: list[Document], code_digests: Mapping[str, str]
    ) -> list[CheckIssue]:
        """Flag code that moved since the document declared it, verified or not.

        The same comparison as :meth:`_find_changed_code` against a different
        baseline, and the difference is the whole reason this exists.
        ``verified_code`` is minted by ``--verified`` and by nothing else, so a
        document nobody has reviewed carries none and that check skips it in
        silence: the glob names the code, the code moves, and the document ages
        without a word. In docir's own corpus every one of the 99 documents
        carrying a ``code:`` glob was unverified, so the check above could fire
        on none of them — a feature reachable only through a step nobody takes
        is a feature that does not run.

        ``code_baseline`` is minted by the write that declares the pattern, so
        it exists from the first moment there is anything to watch. What it
        claims is deliberately weaker: *this is what the tree held when the
        document said it governed this*, which is a fact about the tree and not
        a certificate that anybody read either one. That is what lets the write
        path mint it without laundering a review — the objection that keeps
        ``verified_code`` out of every mechanical write (adr-d9e6d5ccd0b4).

        Reported per pattern, and **only** for patterns this document has never
        been verified against. A pattern carrying both digests is already
        `code-changed`'s to report, with the stronger sentence to say about it;
        naming the same moved file twice is the noise that teaches a reader to
        skim the whole report. The two therefore partition the patterns rather
        than overlapping on them.

        A warning for the reason `code-changed` is one, needing it more: this
        fires on every governed document rather than only the reviewed ones, so
        as an error it would fail the CI of every branch that touches code
        before its docs.

        Absences read as unknown here too. A pattern missing from
        ``code_digests`` did not resolve — `unmatched-code` covers that — and a
        pattern with no recorded baseline predates the field or was written
        where there was no tree to read; neither is reported as unchanged.
        """
        issues: list[CheckIssue] = []
        for doc in documents:
            if doc.archived or not doc.code_baseline:
                continue
            moved = [
                pattern
                for pattern in doc.code
                if pattern not in doc.verified_code
                and (current := code_digests.get(pattern)) is not None
                and (recorded := doc.code_baseline.get(pattern)) is not None
                and current != recorded
            ]
            if not moved:
                continue
            joined = ", ".join(repr(pattern) for pattern in moved)
            issues.append(
                CheckIssue(
                    kind="code-drifted",
                    message=(
                        f"{doc.id!r} governs {joined}, which changed since the document "
                        f"declared it and nobody has verified it since; read it against "
                        f"the code and run `docir update {doc.id} --verified`"
                    ),
                    doc_ids=(doc.id,),
                )
            )
        return issues

    def _find_outdated_verification(self, documents: list[Document]) -> list[CheckIssue]:
        """Flag a standing verification whose text is no longer the text it covered.

        The write path withdraws a verification the moment a CLI edit moves the
        title, description or body (adr-f4e6ade4afd0). This is the same rule for
        every other way the file can move: a hand-edit, a merge that resolves
        into the body, or a teammate on a docir old enough not to revoke. All
        three leave a `verified:` line standing over text nobody read, and
        nothing else in `check` can see it — `stale` is a calendar and this
        document's calendar was reset by the very stamp that is now wrong.

        Compared against the digest recorded at verification time rather than
        against ``updated``, which was the obvious predicate and is unusable: a
        status or a tag moves ``updated`` without touching a word of what was
        reviewed, so `verified < updated` fires on the ordinary life of a
        correctly verified document — issue-40d1792bc9f9's shape, a warning that
        goes off on the product's own workflow.

        Absent is *unknown*, as everywhere else: a verification stamped before
        the digest existed has nothing to differ from and reports nothing, which
        is what keeps this silent on a corpus that predates it.

        A warning, on the same argument as ``code-changed``: the repair is to
        re-read the document and stamp `--verified`, or to withdraw the claim
        with `--clear-verified`. Both are judgements, so `check --fix` cannot
        make either.
        """
        issues: list[CheckIssue] = []
        for doc in documents:
            if doc.archived or doc.verified is None or not doc.verified_content:
                continue
            if doc.verification_digest() == doc.verified_content:
                continue
            issues.append(
                CheckIssue(
                    kind="verification-outdated",
                    message=(
                        f"{doc.id!r} was edited outside the CLI since it was verified on "
                        f"{doc.verified.isoformat()}, so the stamp stands over text nobody "
                        f"read — re-read it and run `docir update {doc.id} --verified`, or "
                        f"withdraw it with `docir update {doc.id} --clear-verified`"
                    ),
                    doc_ids=(doc.id,),
                )
            )
        return issues


def _clock_read(doc: Document) -> str:
    """Which of the three dates :meth:`Document.stale_reference_date` read.

    The `stale` finding names it, because the three call for different actions
    and only one of them is legible from the file: a document overdue since a
    *revocation* carries no `verified:` line at all, so a message that said
    "never verified" would describe it as something nobody ever vouched for.
    """
    if doc.verified is not None:
        return f"verified {doc.verified.isoformat()}"
    if doc.revoked is not None:
        return f"verification revoked {doc.revoked.isoformat()}"
    return f"never verified, created {doc.created.isoformat()}"
