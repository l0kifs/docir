"""initial index schema

Revision ID: 0001
Revises:
Create Date: 2026-07-07
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "documents",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("title", sa.String(), nullable=False),
        sa.Column("description", sa.Text(), nullable=False, server_default=""),
        sa.Column("type", sa.String(), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("created", sa.String(), nullable=False),
        sa.Column("updated", sa.String(), nullable=False),
        sa.Column("archived", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("body", sa.Text(), nullable=False, server_default=""),
        sa.Column("path", sa.String(), nullable=True),
        sa.Column("content_hash", sa.String(), nullable=False, server_default=""),
    )
    op.create_index("ix_documents_type", "documents", ["type"])
    op.create_index("ix_documents_status", "documents", ["status"])

    op.create_table(
        "relations",
        sa.Column(
            "source",
            sa.String(),
            sa.ForeignKey("documents.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("target", sa.String(), primary_key=True),
    )
    op.create_index("ix_relations_target", "relations", ["target"])

    op.create_table(
        "tags",
        sa.Column("key", sa.String(), primary_key=True),
        sa.Column("description", sa.Text(), nullable=False, server_default=""),
    )

    op.create_table(
        "document_tags",
        sa.Column(
            "doc_id",
            sa.String(),
            sa.ForeignKey("documents.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("tag_key", sa.String(), primary_key=True),
    )
    op.create_index("ix_document_tags_tag_key", "document_tags", ["tag_key"])

    op.create_table(
        "embeddings",
        sa.Column(
            "doc_id",
            sa.String(),
            sa.ForeignKey("documents.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("vector", sa.LargeBinary(), nullable=True),
        sa.Column("dirty", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("model_id", sa.String(), nullable=True),
    )

    op.create_table(
        "id_sequences",
        sa.Column("prefix", sa.String(), primary_key=True),
        sa.Column("next_value", sa.Integer(), nullable=False, server_default="1"),
    )

    op.execute(
        "CREATE VIRTUAL TABLE documents_fts USING fts5("
        "doc_id UNINDEXED, title, description, body, "
        "tokenize='porter unicode61')"
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS documents_fts")
    op.drop_table("id_sequences")
    op.drop_table("embeddings")
    op.drop_index("ix_document_tags_tag_key", table_name="document_tags")
    op.drop_table("document_tags")
    op.drop_table("tags")
    op.drop_index("ix_relations_target", table_name="relations")
    op.drop_table("relations")
    op.drop_index("ix_documents_status", table_name="documents")
    op.drop_index("ix_documents_type", table_name="documents")
    op.drop_table("documents")
