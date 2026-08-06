"""code references

Adds ``document_code``: one row per (document, glob) naming the code a document
governs (issue-90aea6d1b891).

A child table rather than a column on ``documents``, following
``document_tags``: the field is a set of patterns and the question it exists to
answer — "which documents govern this path?" — is asked of the patterns.

No backfill and no dirty-marking. The field is new and optional, so every
existing document has an empty set, and nothing about embedding or ranking
reads it; a store that never sets ``code`` is bit-identical either side of this
migration.

Revision ID: 0004
Revises: 0003
Create Date: 2026-08-06
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "document_code",
        sa.Column(
            "doc_id",
            sa.String(),
            sa.ForeignKey("documents.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("pattern", sa.String(), primary_key=True),
    )
    op.create_index("ix_document_code_pattern", "document_code", ["pattern"])


def downgrade() -> None:
    op.drop_index("ix_document_code_pattern", table_name="document_code")
    op.drop_table("document_code")
