"""add interview sessions table

Revision ID: b656bb42a9ca
Revises: e2b7a4c910f3
Create Date: 2026-09-12 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = 'b656bb42a9ca'
down_revision: Union[str, Sequence[str], None] = 'e2b7a4c910f3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """
    Upgrade schema.

    New table for the AI mock interview feature -- a signed-in user's
    voice interview tied to one of their already-roasted resumes. Kept
    entirely separate from Sessions (no shared status enum, no slug) since
    an interview is never a public shareable link the way a roast is; its
    only public surface is a separate leaderboard (score + display name).
    """
    op.create_table(
        'InterviewSessions',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('resume_session_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('status', sa.String(), nullable=False),
        sa.Column('job_description', sa.Text(), nullable=False),
        sa.Column('turn_count', sa.Integer(), nullable=False),
        sa.Column('max_turns', sa.Integer(), nullable=False),
        sa.Column('transcript_blob_path', sa.Text(), nullable=True),
        sa.Column('score', sa.Integer(), nullable=True),
        sa.Column('strengths', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('weaknesses', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('next_steps', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('started_at', sa.DateTime(), nullable=True),
        sa.Column('completed_at', sa.DateTime(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.Column('error_code', sa.String(length=50), nullable=True),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(['user_id'], ['Users.id'], ),
        sa.ForeignKeyConstraint(['resume_session_id'], ['Sessions.id'], ),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_InterviewSessions_user_id'), 'InterviewSessions', ['user_id'], unique=False)
    op.create_index(op.f('ix_InterviewSessions_resume_session_id'), 'InterviewSessions', ['resume_session_id'], unique=False)
    op.create_index(op.f('ix_InterviewSessions_status'), 'InterviewSessions', ['status'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f('ix_InterviewSessions_status'), table_name='InterviewSessions')
    op.drop_index(op.f('ix_InterviewSessions_resume_session_id'), table_name='InterviewSessions')
    op.drop_index(op.f('ix_InterviewSessions_user_id'), table_name='InterviewSessions')
    op.drop_table('InterviewSessions')
