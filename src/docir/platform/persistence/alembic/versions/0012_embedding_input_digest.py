"""the digest of the text a vector was computed from

Adds ``embeddings.input_digest``: a hash of everything the model read for a
document — the model id, the document's embedding text, and every chunk triple
it would be split into. The drain compares it before embedding and skips a
document whose inputs are unchanged, which is what stops every release from
recomputing vectors byte-identical to the ones already stored (issue-77dd42e3a03a).

It covers the chunking too, deliberately. A release that changes how a body is
split produces different chunk triples and so a different digest, with no
version constant for anybody to remember to bump — the failure mode a stamp
keyed on a hand-maintained number would have had.

Additive and nullable, so an index built by an earlier release upgrades in
place. Every row starts empty, which is the correct reading and the same
absent-means-unknown rule ``0007``, ``0009``, ``0010`` and ``0011`` follow: a
vector with no recorded input cannot be shown to be current, so the first drain
after the upgrade recomputes it and records one.

Revision ID: 0012
Revises: 0011
Create Date: 2026-09-06
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0012"
down_revision: str | None = "0011"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("embeddings", sa.Column("input_digest", sa.String(), nullable=True))


def downgrade() -> None:
    op.drop_column("embeddings", "input_digest")
