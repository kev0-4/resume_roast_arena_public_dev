"""add leaderboard index to sessions

Revision ID: a3f1c9d84e21
Revises: 9b70e9221369
Create Date: 2026-09-06 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a3f1c9d84e21'
down_revision: Union[str, Sequence[str], None] = '9b70e9221369'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """
    Upgrade schema.

    Partial composite index matching GET /leaderboard's exact query shape
    (backend/src/services/session_service.py:get_leaderboard) -- WHERE
    slug IS NOT NULL AND composite_score IS NOT NULL, ORDER BY
    composite_score DESC, created_at ASC. Without this, that ORDER BY
    forces a full-table sort on every request regardless of how small the
    LIMIT is. With it, Postgres can walk the index in already-sorted
    order and stop as soon as it has `limit` rows -- cost stays roughly
    constant as the table grows, instead of scaling with total row count.

    Partial (WHERE slug IS NOT NULL AND composite_score IS NOT NULL)
    rather than a plain index on the whole table: most Sessions rows
    never reach DONE (in-progress or failed pipelines), so indexing only
    the rows that can ever actually appear on the leaderboard keeps the
    index itself smaller and cheaper to maintain on every write.
    """
    op.create_index(
        'ix_sessions_leaderboard',
        'Sessions',
        [sa.text('composite_score DESC'), sa.text('created_at ASC')],
        unique=False,
        postgresql_where=sa.text('slug IS NOT NULL AND composite_score IS NOT NULL'),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index('ix_sessions_leaderboard', table_name='Sessions')
