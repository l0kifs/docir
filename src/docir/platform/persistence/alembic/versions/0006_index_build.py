"""index build provenance

Adds ``index_build``: one row naming the docir version that last rebuilt the
index, so a command can say the derived state was produced by code that is no
longer installed.

``schema_baseline`` answers the neighbouring question and cannot answer this
one. It compares two *schemas*, so it is silent whenever a release changes how
documents are read rather than what they must contain — chunked embeddings
(adr-927aa43d9635) rewrote every vector in the index without touching a type,
a status or a cadence.

The version does not live in the baseline payload for the same reason: that
payload is diffed line by line and reported to the user, so a version key in it
would render every upgrade as a schema change.

Single-row and written only by ``reindex``, like the baseline — it is the
command that makes derived state agree with its sources, and this is a fact
about the last time that happened.

No backfill: absent means *unknown*, not *current*, so an existing store reports
nothing until its next rebuild.

Revision ID: 0006
Revises: 0005
Create Date: 2026-08-09
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0006"
down_revision: str | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "index_build",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("docir_version", sa.Text(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("index_build")
