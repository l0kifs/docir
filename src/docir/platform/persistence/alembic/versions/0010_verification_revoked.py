"""the date a standing verification was withdrawn

Adds ``documents.revoked``: the date an edit to the verified content — or an
explicit ``update --clear-verified`` — took ``verified`` away. It is what the
review cadence runs from once ``verified`` is gone (adr-f4e6ade4afd0).

Additive and nullable, so an index built by an earlier release upgrades in
place. Every row starts ``NULL``, which is the correct reading: the value lives
in frontmatter and reaches the index only through a document read, and nothing
in a store written before this release has been revoked. Absent means *never
revoked*, not *revoked at an unknown time* — the same absent-means-unknown rule
``0007`` and ``0009`` follow.

Revision ID: 0010
Revises: 0009
Create Date: 2026-09-05
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0010"
down_revision: str | None = "0009"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("documents", sa.Column("revoked", sa.String(), nullable=True))


def downgrade() -> None:
    op.drop_column("documents", "revoked")
