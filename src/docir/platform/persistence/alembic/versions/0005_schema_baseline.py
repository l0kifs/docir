"""schema baseline

Adds ``schema_baseline``: one row holding the resolved schema the index was
last rebuilt against, so `docir check` can report that the schema moved
(issue-d891ab5501e6).

Derived state, like every other table here: the payload is a rendering of
``docs-schema.yaml`` merged with the packaged core and profiles, and
``reindex`` rewrites it. Nothing reads it but the drift check.

Single-row by construction (``id`` is a constant primary key) rather than a
history: the question is "did it change since the index was built", which one
prior value answers. A history would need a retention rule and a reader for it,
and nothing has asked either question.

No backfill. An existing store has no baseline until its next ``reindex``, and
absent means *unknown* rather than *unchanged* — the same rule ``similarity``
and ``code_matches`` follow, and the one that keeps an upgrade from reporting
the whole schema as new.

Revision ID: 0005
Revises: 0004
Create Date: 2026-08-07
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "schema_baseline",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("payload", sa.Text(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("schema_baseline")
