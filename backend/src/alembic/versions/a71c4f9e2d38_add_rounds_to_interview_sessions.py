"""add rounds to interview sessions

Adds the planned round structure and per-round results to an interview.

Both columns are nullable JSONB with no backfill: an interview created
before this migration simply has no plan, and the routes treat that as
conversation-only -- which is exactly the interview that shipped in #19.
Nothing in flight breaks, and nothing needs rewriting.

Revision ID: a71c4f9e2d38
Revises: b656bb42a9ca
Create Date: 2026-09-14

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = 'a71c4f9e2d38'
down_revision: Union[str, Sequence[str], None] = 'b656bb42a9ca'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # The validated plan: vertical, rationale, and the ordered rounds.
    op.add_column(
        'InterviewSessions',
        sa.Column('plan', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )
    # One entry per completed exercise round: submission, automated review,
    # time taken, and whether anything was pasted in.
    op.add_column(
        'InterviewSessions',
        sa.Column('round_results', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )
    # Which round the candidate is on. Server-side, so a client cannot skip
    # ahead to a later round or replay an earlier one.
    op.add_column(
        'InterviewSessions',
        sa.Column('current_round', sa.Integer(), nullable=False, server_default='0'),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('InterviewSessions', 'current_round')
    op.drop_column('InterviewSessions', 'round_results')
    op.drop_column('InterviewSessions', 'plan')
