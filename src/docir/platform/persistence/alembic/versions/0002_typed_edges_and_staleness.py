"""typed relation edges + staleness metadata

Adds:
* ``relations.kind`` — the typed edge kind (default ``relates_to``, so edges
  indexed before typed relations keep their meaning).
* ``documents.owner`` / ``documents.verified`` — optional stewardship metadata
  the staleness check reads.

All three are additive columns with defaults; existing rows upgrade in place.
The index is a derived projection, but migrating in place (rather than dropping
rows) keeps a running install consistent without a mandatory reindex.

Revision ID: 0002
Revises: 0001
Create Date: 2026-07-23
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "relations",
        sa.Column("kind", sa.String(), nullable=False, server_default="relates_to"),
    )
    op.add_column(
        "documents",
        sa.Column("owner", sa.String(), nullable=False, server_default=""),
    )
    op.add_column("documents", sa.Column("verified", sa.String(), nullable=True))


def downgrade() -> None:
    op.drop_column("documents", "verified")
    op.drop_column("documents", "owner")
    op.drop_column("relations", "kind")
