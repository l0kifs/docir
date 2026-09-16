"""authorship digests for code globs

Adds ``document_code.baseline``: what the pattern matched when the document
last declared it, so drift is watched from the moment a glob is written rather
than from a verification that may never come.

The sibling of ``digest`` (0007), and deliberately a second column rather than a
reinterpretation of that one. They answer different questions — "the code moved
since somebody read this" and "the code moved since this document claimed to
describe it" — and a single column would have to pick one, which is how the
first became unreachable: it is written only by ``--verified``, and not one of
the 99 governed documents in docir's own store had ever been verified.

No backfill here either, for the opposite reason to 0007's. The index is a
derived projection, so a value invented in this migration would be erased by the
next ``reindex``; the baseline lives in the frontmatter and arrives in the index
from there. ``docir check --fix`` is what mints a missing one, in the file.

Revision ID: 0013
Revises: 0012
Create Date: 2026-09-16
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0013"
down_revision: str | None = "0012"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("document_code", sa.Column("baseline", sa.String(), nullable=True))


def downgrade() -> None:
    op.drop_column("document_code", "baseline")
