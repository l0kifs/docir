"""derived mention graph

Adds ``mentions``: one row per (document, id named in its body). The graph the
corpus already had in its prose and nobody could query — `orphan` fired for
every document whose author had linked it by writing its id rather than by
editing `related:`.

Derived state, like the FTS index and the vectors: recomputed from the body on
every save and rebuilt wholesale by `docir reindex`, never written back to
frontmatter. `related:` stays the authored, typed layer.

A table of its own rather than rows in ``relations``. That table is the authored
graph, and three checks plus the delete guard read it: putting derived edges
there would make `docir check` report cycles nobody wrote and block a delete
because somebody quoted an id in a paragraph.

``target`` has no foreign key on purpose — a body routinely names a document
that does not exist yet (an ADR referencing the issue it will produce), and
resolution is a read-time join, so the mention starts resolving when the target
is written rather than when the mentioning document is next saved.

No backfill: the rows come from bodies, and the next `reindex` writes them all.
Until then the table is empty, which reads as "no mentions" — the state every
store was already in.

Revision ID: 0008
Revises: 0007
Create Date: 2026-08-17
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0008"
down_revision: str | None = "0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "mentions",
        sa.Column(
            "source",
            sa.String(),
            sa.ForeignKey("documents.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("target", sa.String(), primary_key=True),
    )
    op.create_index("ix_mentions_target", "mentions", ["target"])


def downgrade() -> None:
    op.drop_index("ix_mentions_target", table_name="mentions")
    op.drop_table("mentions")
