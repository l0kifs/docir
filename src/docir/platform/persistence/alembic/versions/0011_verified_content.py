"""the digest of the text a verification covered

Adds ``documents.verified_content``: the title/description/body digest recorded
when ``--verified`` was stamped, so `check` can report a verified document whose
content moved without the CLI seeing it — a hand-edit, a merge, or an edit by a
build that predates revocation (adr-f4e6ade4afd0).

Additive with a default, so an index built by an earlier release upgrades in
place. Every row starts empty, which is the correct reading: the value lives in
frontmatter and reaches the index only through a document read, and empty means
*unknown*, never *unchanged* — a verification stamped before this field existed
has no recorded text to differ from, and reports nothing. The same
absent-means-unknown rule ``0007``, ``0009`` and ``0010`` follow.

Revision ID: 0011
Revises: 0010
Create Date: 2026-09-05
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0011"
down_revision: str | None = "0010"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "documents",
        sa.Column("verified_content", sa.String(), nullable=False, server_default=""),
    )


def downgrade() -> None:
    op.drop_column("documents", "verified_content")
