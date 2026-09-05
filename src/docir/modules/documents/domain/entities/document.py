"""The :class:`Document` aggregate.

A document is the union of its YAML frontmatter (structured, indexed metadata)
and its markdown body (free-form natural language). The markdown file on disk
is the source of truth; this entity is the in-memory representation the use
cases manipulate before persisting back to the file and the index.
"""

from __future__ import annotations

import hashlib
from collections.abc import Collection, Mapping
from dataclasses import dataclass, field, replace
from datetime import date

from docir.modules.documents.domain.services.chunking import EmbeddableChunk, split_body
from docir.modules.documents.domain.value_objects.relations import RelatedRef
from docir.platform.naming import scan_document_ids


@dataclass
class Document:
    """A single indexed markdown document."""

    id: str
    title: str
    description: str
    type: str
    status: str
    created: date
    updated: date
    tags: tuple[str, ...] = ()
    related: tuple[RelatedRef, ...] = ()
    archived: bool = False
    body: str = ""
    # Filesystem path relative to the docs root; ``None`` before persistence.
    path: str | None = field(default=None)
    # Optional stewardship metadata (staleness). ``owner`` is a free-form name;
    # ``verified`` is the date somebody last re-confirmed the doc is still true.
    owner: str = ""
    verified: date | None = None
    #: The date a standing verification was withdrawn — by an edit to the
    #: content that was verified, or by ``update --clear-verified``. It is what
    #: the review cadence runs from once ``verified`` is gone, so a revocation
    #: puts the document back in the queue one cadence later rather than
    #: immediately (adr-f4e6ade4afd0).
    #:
    #: Stamped only where a verification actually stood. Editing a document that
    #: carries none leaves it untouched, which is what keeps issue-6726eabcf871
    #: closed: writing into an unverified document can still never move its
    #: clock, and the one date that *can* move it costs a `--verified` first.
    revoked: date | None = None
    #: Digest of the text a verification covered — title, description and body —
    #: taken at the moment it was stamped. The evidence half of the *calendar*,
    #: as ``verified_code`` is the evidence half of the code: ``revoked`` records
    #: that a CLI write moved the content, and this catches the same move made
    #: any other way — a hand-edit, a merge, or a build that predates
    #: revocation. Absent means *unknown*, never *unchanged*, so a document
    #: verified before this field existed reports nothing.
    verified_content: str = ""
    #: Repo-relative globs naming the code this document governs
    #: (issue-90aea6d1b891). Held as written, in the author's order: the
    #: patterns are matched against a working tree that is not this module's to
    #: read, so the entity carries them and judges nothing about them.
    code: tuple[str, ...] = ()
    #: Per-pattern digest of what each ``code`` glob matched at the moment the
    #: document was last verified — the evidence half of staleness. ``verified``
    #: alone measures a calendar: a cadence elapses and the document is suspect
    #: whether or not anything happened to the code. This says whether anything
    #: happened.
    #:
    #: Keyed by pattern rather than paired positionally with :attr:`code`, so
    #: reordering the globs cannot silently re-point a digest at a different
    #: pattern. A pattern absent from the map is *unverified*, not *unchanged*:
    #: it was added after the last verification, or matched nothing then, and
    #: `check` reports nothing for it.
    verified_code: Mapping[str, str] = field(default_factory=dict)
    #: Why this document is *meant* to carry no relations — the reviewed
    #: exemption from the ``orphan`` warning (issue-77a09761e1d4).
    #:
    #: A free-form reason rather than a boolean, on the same argument as
    #: :attr:`owner`: the field exists to turn "nobody has wired this yet" into
    #: a recorded judgement, and a bare ``true`` records that somebody silenced
    #: the warning without recording what they concluded. Empty means *not
    #: exempt*, which is the default state of every document.
    isolated: str = ""

    def embedding_text(self) -> str:
        """The text embedded for semantic search: title + description + body.

        The agent-authored ``description`` gives the vector a concise,
        high-signal summary to anchor on, improving retrieval over embedding
        raw body text alone.
        """
        return f"{self.title}\n\n{self.description}\n\n{self.body}".strip()

    def embedding_chunks(self) -> tuple[EmbeddableChunk, ...]:
        """The per-section texts to embed alongside :meth:`embedding_text`.

        The entity owns this rather than the scheduler because the scheduler
        lives in ``indexing``, which may not depend on ``documents`` — the same
        reason ``embedding_text`` is a method here. Each chunk's text is
        prefixed with the title, so a section that never restates its subject
        ("Rotation is a runbook step") can still be matched by a query phrased
        in the document's terms.
        """
        return tuple(
            EmbeddableChunk(chunk.ordinal, chunk.heading, chunk.embedding_text(self.title))
            for chunk in split_body(self.body)
        )

    def mentioned_ids(self, prefixes: Collection[str]) -> tuple[str, ...]:
        """The document ids this body names — the derived half of the graph.

        The entity owns this for the same reason it owns
        :meth:`embedding_chunks`: it is a pure function of the content, and the
        layer that persists it may not import the grammar that recognises an id
        (tach enforces both halves of that sentence).

        A document naming its own id is describing itself, not linking to
        itself, so it is excluded here — where the id is known — rather than
        left for each caller to remember.

        ``prefixes`` comes from the schema. Without it any hyphenated word with
        a hex tail would read as an id, and the point of the derived graph is
        that it is quieter than `related:`, not noisier.
        """
        return tuple(
            target for target in scan_document_ids(self.body, prefixes) if target != self.id
        )

    def content_hash(self) -> str:
        """A stable hash over the content that matters for stale-write checks.

        Covers every field a write could change; used to detect that the file
        was modified out-of-band since the caller last fetched it.
        """
        parts = [
            self.title,
            self.description,
            self.type,
            self.status,
            # Sorted so tag/relation ordering (which differs between the file's
            # insertion order and the index's sorted order) never affects the
            # hash — only genuine content changes do.
            ",".join(sorted(self.tags)),
            ",".join(sorted(f"{ref.kind}:{ref.target}" for ref in self.related)),
            # Sorted for the same reason tags are: the file keeps the author's
            # order and the index returns them sorted, and a document that
            # round-tripped through the index must not read as diverged.
            ",".join(sorted(self.code)),
            str(self.archived),
            self.owner,
            "" if self.verified is None else self.verified.isoformat(),
            self.body.strip("\n"),
        ]
        # Appended only when present, so every document that carries no
        # verification digests hashes exactly as it did before the field
        # existed. Including an empty part unconditionally would move every
        # hash in every store, and the index holds the previous value: the whole
        # corpus would read as edited out-of-band until the next reindex, and
        # `--replace-body` would refuse writes that lose nothing.
        if self.verified_code:
            parts.append(",".join(f"{p}={d}" for p, d in sorted(self.verified_code.items())))
        # Appended under the same rule, and for the same reason: a store whose
        # documents are all unexempt must hash exactly as it did before this
        # field existed, or the whole corpus reads as edited out-of-band until
        # the next reindex.
        if self.isolated:
            parts.append(self.isolated)
        # And again, for the third field added after the hash existed: a corpus
        # where nothing has been revoked must hash exactly as it did before.
        if self.revoked is not None:
            parts.append(self.revoked.isoformat())
        # Appended under the same rule as the three fields above it.
        if self.verified_content:
            parts.append(self.verified_content)
        digest = hashlib.sha256("\x1f".join(parts).encode("utf-8"))
        return digest.hexdigest()

    def verification_digest(self) -> str:
        """Digest of the text a reviewer reads: title, description, body.

        Exactly the three fields whose change withdraws a verification
        (adr-f4e6ade4afd0), so what this records and what the write path revokes
        on cannot come apart. Deliberately **not** :meth:`content_hash`, which
        also covers the type, the status, the tags, the edges and the review
        state itself — a status change would read as "the document you verified
        has been rewritten", which is the one thing this must never say.

        Truncated to 12 hex like the ``code`` digests: it is compared against
        itself, never inverted, and a shorter field keeps the frontmatter
        readable.
        """
        parts = [self.title, self.description, self.body.strip("\n")]
        return hashlib.sha256("\x1f".join(parts).encode("utf-8")).hexdigest()[:12]

    def stale_reference_date(self) -> date:
        """The date staleness is measured from: verification, revocation, creation.

        Never ``updated`` (issue-6726eabcf871). The fallback has to be a date an edit
        cannot move, or the queue clears itself the moment anybody reads it: a
        document nobody has vouched for left the queue because somebody wrote in
        it, and writing down "still unanswered" was the most reliable way to make
        it disappear. The re-check *is* the evidence it is not resolved.

        ``created`` is the one date the write path sets once and never rewrites
        — not a retype, not a tag rename, not `check --fix`. Absent
        ``verified``, it is also the earliest moment docir can honestly claim
        anybody looked at the document, so the cadence runs from there.

        ``revoked`` sits between the two (adr-f4e6ade4afd0). It records the moment a
        verification stopped being true, and a document that reaches it is not
        a document nobody ever vouched for: somebody did, then the content moved
        under the claim. Ageing it from ``created`` would report it overdue the
        instant the edit landed, on a corpus older than its cadence — the
        failure mode adr-fad49eaa4648 measured and rejected — so the cadence
        restarts from the revocation instead.

        It cannot be used to clear the queue by writing, because only a standing
        ``verified`` can be revoked: a document with no verification has nothing
        to withdraw, and an edit leaves its clock exactly where it was.
        """
        return self.verified or self.revoked or self.created

    def related_targets(self) -> tuple[str, ...]:
        """Just the target ids of the outgoing edges (kind-agnostic)."""
        return tuple(ref.target for ref in self.related)

    def with_updates(self, **changes: object) -> Document:
        """Return a copy with the given fields replaced (frontmatter patch)."""
        return replace(self, **changes)  # type: ignore[arg-type]
