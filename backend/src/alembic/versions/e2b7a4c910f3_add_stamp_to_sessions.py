"""add stamp to sessions

Revision ID: e2b7a4c910f3
Revises: a3f1c9d84e21
Create Date: 2026-09-06 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e2b7a4c910f3'
down_revision: Union[str, Sequence[str], None] = 'a3f1c9d84e21'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """
    Upgrade schema.

    Stores the roast card's stamp tier ("ROASTED"/"MID"/"SOLID", see
    workers/renderer/pipeline/card_data.py:compute_stamp) as a plain
    column on Sessions, set alongside composite_score at the same DONE
    transition (workers/renderer/processor.py). Same reasoning as why
    composite_score itself is a stored column and not computed on read:
    the leaderboard lists many sessions per request, and computing the
    stamp requires the session's scored.json severity summary -- reading
    that per row on every leaderboard page load would mean N blob reads
    per request instead of the single indexed query the leaderboard is
    built around. Nullable because existing DONE sessions predate this
    column and won't be backfilled; the frontend treats a missing stamp
    as a neutral/no-badge state rather than erroring.
    """
    op.add_column('Sessions', sa.Column('stamp', sa.String(length=16), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('Sessions', 'stamp')
