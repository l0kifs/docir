"""verification digests for code globs

Adds ``document_code.digest``: what the pattern matched at the moment a human
last verified the document, so `docir check` can report that the code moved
rather than only that a review cadence elapsed.

A nullable column on the existing table rather than a table of its own. The
digest has no identity apart from the (document, pattern) pair it belongs to,
and keeping the two in one row is what stops them from drifting — a separate
table would need its own delete-with-the-pattern rule to say the same thing.

No backfill. The value is evidence of a human act, so inventing one for a
document nobody has verified would assert exactly the thing the check exists to
establish. NULL is the unknown answer, and `check` reports nothing for it.

Revision ID: 0007
Revises: 0006
Create Date: 2026-08-17
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0007"
down_revision: str | None = "0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("document_code", sa.Column("digest", sa.String(), nullable=True))


def downgrade() -> None:
    op.drop_column("document_code", "digest")
