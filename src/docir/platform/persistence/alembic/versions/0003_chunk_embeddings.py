"""per-section chunk embeddings

Adds ``chunk_embeddings``: one row per (document, section), each holding the
vector for that section alone.

Why this exists rather than a wider ``embeddings`` row: the embedding model
reads a fixed token window and silently ignores the rest — measured at roughly
1,900 characters of prose for ``BAAI/bge-small-en-v1.5``, and 83 of the 103
documents in docir's own store are longer than that. Their tails were not
ranked badly, they were absent from the semantic index. One vector per section
is what puts them in it (ADR-0014).

Every existing embedding row is marked dirty as part of the upgrade. Without
that, a store whose vectors already match the current ``model_id`` is never
considered stale, so no chunk would ever be computed and the upgrade would be a
no-op on precisely the corpora that need it. The recompute happens on the next
write or ``docir embed --flush``, the same eventual-consistency contract every
other embedding change follows.

Revision ID: 0003
Revises: 0002
Create Date: 2026-08-03
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "chunk_embeddings",
        sa.Column(
            "doc_id",
            sa.String(),
            sa.ForeignKey("documents.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        # Position in the body. Part of the key rather than a surrogate id: a
        # chunk has no identity beyond "the nth slice of this body", and the
        # whole set is replaced together whenever the body changes.
        sa.Column("ordinal", sa.Integer(), primary_key=True),
        sa.Column("heading", sa.String(), nullable=False, server_default=""),
        sa.Column("vector", sa.LargeBinary(), nullable=True),
        sa.Column("model_id", sa.String(), nullable=True),
    )
    # Same recompute trigger a model switch uses: mark everything dirty and let
    # the scheduler refill on the next write or flush.
    op.execute(sa.text("UPDATE embeddings SET dirty = 1"))


def downgrade() -> None:
    op.drop_table("chunk_embeddings")
