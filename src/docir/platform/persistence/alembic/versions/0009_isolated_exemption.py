"""the reviewed exemption from the ``orphan`` warning

Adds ``documents.isolated``: the reason a document is *meant* to carry no
relations. ``orphan`` skips a document that has one.

Additive with a default, so an index built by an earlier release upgrades in
place. The value itself lives in frontmatter and reaches the index only through
a document read, so an in-place upgrade leaves every row empty — meaning *not
exempt*, which is the correct reading until `docir reindex` has looked at the
files. It is the same absent-means-unknown rule ``0007`` follows: an exemption
is a judgement somebody recorded, and inventing one here would assert exactly
what the check exists to ask about.

Revision ID: 0009
Revises: 0008
Create Date: 2026-09-04
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0009"
down_revision: str | None = "0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "documents",
        sa.Column("isolated", sa.String(), nullable=False, server_default=""),
    )


def downgrade() -> None:
    op.drop_column("documents", "isolated")
